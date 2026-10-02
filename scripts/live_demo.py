#!/usr/bin/env python3
from __future__ import annotations

import argparse
import queue
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import cv2
import numpy as np

from common import (DETECTION_FIELDS, EVENT_FIELDS, FRAME_FIELDS, ROOT, make_run_id,
                    open_csv, read_json, read_prompts, read_synonyms, software_info,
                    utc_now, write_json)
from owlv2_runtime import Owlv2Runtime, draw_detections


@dataclass
class CapturedFrame:
    frame_id: int
    camera_timestamp_ms: float
    captured_at: float
    image: np.ndarray


def main() -> None:
    parser = argparse.ArgumentParser(description="OWLv2 live voi queue latest-frame")
    parser.add_argument("--prompts", type=Path, default=ROOT / "prompts/prompts_v1.txt")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/default.json")
    parser.add_argument("--synonyms", type=Path, default=ROOT / "prompts/synonym_mapping.csv")
    parser.add_argument("--duration", type=float, default=0, help="0 = chay den khi bam q/Ctrl+C")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--save-raw", action="store_true")
    args = parser.parse_args()
    try:
        import pyrealsense2 as rs
    except ImportError as exc:
        raise SystemExit("Thieu pyrealsense2. Hay cai librealsense Python bindings.") from exc
    config, prompts = read_json(args.config), read_prompts(args.prompts)
    camera_cfg = config["camera"]
    runtime = Owlv2Runtime(config, prompts, read_synonyms(args.synonyms))
    run_id = make_run_id("live")
    run_dir = ROOT / "runs" / run_id
    run_dir.mkdir(parents=True)
    shutil.copy2(args.prompts, run_dir / args.prompts.name)
    frame_queue: queue.Queue[CapturedFrame] = queue.Queue(maxsize=2)
    stop = threading.Event()
    state = {"captured": 0, "dropped": 0, "capture_error": None}
    pipeline, rs_config = rs.pipeline(), rs.config()
    rs_config.enable_stream(rs.stream.color, camera_cfg["width"], camera_cfg["height"], rs.format.bgr8, camera_cfg["fps"])
    profile = pipeline.start(rs_config)
    device = profile.get_device()
    raw_writer = cv2.VideoWriter(str(run_dir / "original.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), camera_cfg["fps"], (camera_cfg["width"], camera_cfg["height"])) if args.save_raw else None
    overlay_writer = cv2.VideoWriter(str(run_dir / "overlay.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), camera_cfg["fps"], (camera_cfg["width"], camera_cfg["height"]))

    def capture_loop() -> None:
        try:
            while not stop.is_set():
                color = pipeline.wait_for_frames(2000).get_color_frame()
                if not color: continue
                image = np.asanyarray(color.get_data()).copy()
                item = CapturedFrame(state["captured"], color.get_timestamp(), perf_counter(), image)
                state["captured"] += 1
                if raw_writer: raw_writer.write(image)
                if frame_queue.full():
                    try: frame_queue.get_nowait(); state["dropped"] += 1
                    except queue.Empty: pass
                frame_queue.put_nowait(item)
        except Exception as exc:
            state["capture_error"] = str(exc); stop.set()

    try:
        time.sleep(float(camera_cfg.get("warmup_seconds", 3)))
        runtime.warmup(camera_cfg["width"], camera_cfg["height"], int(config.get("warmup_runs", 10)))
        detection_handle, detection_writer = open_csv(run_dir / "detections.csv", DETECTION_FIELDS)
        frame_handle, frame_writer = open_csv(run_dir / "frame_metrics.csv", FRAME_FIELDS)
        event_handle, event_writer = open_csv(run_dir / "events.csv", EVENT_FIELDS)
        event_writer.writerow({"run_id": run_id, "timestamp_utc": utc_now(), "event": "start", "details": f"{len(prompts)} prompts"})
        thread = threading.Thread(target=capture_loop, name="realsense-capture", daemon=True); thread.start()
        started, processed = time.monotonic(), 0
        while not stop.is_set() and (args.duration <= 0 or time.monotonic() - started < args.duration):
            try: item = frame_queue.get(timeout=1)
            except queue.Empty: continue
            detections, model_ms, tensor_shape = runtime.infer(item.image)
            e2e_ms = (perf_counter() - item.captured_at) * 1000
            fps = 1000 / model_ms if model_ms else 0
            for det in detections:
                x1, y1, x2, y2 = det.box
                detection_writer.writerow(dict(zip(DETECTION_FIELDS, [run_id, "live", item.frame_id,
                    round(item.camera_timestamp_ms, 3), det.class_id, det.canonical_class, det.prompt,
                    round(det.confidence, 6), round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2),
                    camera_cfg["width"], camera_cfg["height"], round(model_ms, 3), round(e2e_ms, 3)])))
            frame_writer.writerow(dict(zip(FRAME_FIELDS, [run_id, item.frame_id, round(item.camera_timestamp_ms, 3),
                True, True, state["dropped"], frame_queue.qsize(), round(model_ms, 3), round(e2e_ms, 3),
                camera_cfg["fps"], round(fps, 3), round(runtime.memory_mb(), 2)])))
            canvas = draw_detections(item.image, detections, f"model {model_ms:.1f} ms | dropped {state['dropped']}")
            overlay_writer.write(canvas); processed += 1
            if not args.headless:
                cv2.imshow("OWLv2 live - q to stop", canvas)
                if cv2.waitKey(1) & 0xFF == ord("q"): stop.set()
    except KeyboardInterrupt:
        stop.set()
    finally:
        stop.set()
        if "thread" in locals(): thread.join(timeout=3)
        pipeline.stop()
        if raw_writer: raw_writer.release()
        overlay_writer.release(); cv2.destroyAllWindows()
        for name in ("detection_handle", "frame_handle", "event_handle"):
            if name in locals(): locals()[name].close()
    summary = {"run_id": run_id, "phase": "live", "created_at_utc": utc_now(), "config": config,
        "prompts": prompts, "software": software_info(), "captured_frames": state["captured"],
        "processed_frames": processed, "dropped_frames": state["dropped"], "capture_error": state["capture_error"],
        "input_tensor_shape": tensor_shape if "tensor_shape" in locals() else None,
        "peak_allocated_vram_mb": runtime.peak_memory_mb(),
        "camera": {"model": device.get_info(rs.camera_info.name), "serial": device.get_info(rs.camera_info.serial_number),
                   "firmware": device.get_info(rs.camera_info.firmware_version)}}
    write_json(run_dir / "config.json", summary)
    print(f"Hoan tat: {run_dir}")


if __name__ == "__main__":
    main()
