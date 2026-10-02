#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import shutil
import statistics
from pathlib import Path
from time import perf_counter

import cv2

from common import (DETECTION_FIELDS, FRAME_FIELDS, ROOT, make_run_id, open_csv,
                    percentile, read_json, read_prompts, read_synonyms, software_info,
                    utc_now, write_json)
from owlv2_runtime import Owlv2Runtime, draw_detections


def main() -> None:
    parser = argparse.ArgumentParser(description="Chay OWLv2 tren video da ghi")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--phase", choices=["val_v1", "val_v2", "test"], required=True)
    parser.add_argument("--prompts", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "configs/default.json")
    parser.add_argument("--synonyms", type=Path, default=ROOT / "prompts/synonym_mapping.csv")
    parser.add_argument("--run-id")
    parser.add_argument("--max-frames", type=int, default=0)
    parser.add_argument("--no-overlay", action="store_true")
    args = parser.parse_args()
    if not args.video.exists():
        raise SystemExit(f"Khong tim thay video: {args.video}")

    config, prompts = read_json(args.config), read_prompts(args.prompts)
    synonyms = read_synonyms(args.synonyms)
    run_id = args.run_id or make_run_id(args.phase)
    run_dir = ROOT / "runs" / run_id
    if run_dir.exists():
        raise SystemExit(f"Run da ton tai, khong ghi de: {run_dir}")
    run_dir.mkdir(parents=True)
    shutil.copy2(args.video, run_dir / "original.mp4")
    shutil.copy2(args.prompts, run_dir / args.prompts.name)
    runtime = Owlv2Runtime(config, prompts, synonyms)
    capture = cv2.VideoCapture(str(args.video))
    if not capture.isOpened():
        raise SystemExit(f"Khong mo duoc video: {args.video}")
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    camera_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
    overlay = None
    if not args.no_overlay:
        overlay = cv2.VideoWriter(str(run_dir / "overlay.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), camera_fps, (width, height))
    runtime.warmup(width, height, int(config.get("warmup_runs", 10)))
    detection_handle, detection_writer = open_csv(run_dir / "detections.csv", DETECTION_FIELDS)
    frame_handle, frame_writer = open_csv(run_dir / "frame_metrics.csv", FRAME_FIELDS)
    model_times, e2e_times, tensor_shape = [], [], None
    frame_id = 0
    try:
        while args.max_frames <= 0 or frame_id < args.max_frames:
            loop_started = perf_counter()
            ok, frame = capture.read()
            if not ok:
                break
            timestamp_ms = capture.get(cv2.CAP_PROP_POS_MSEC)
            detections, model_ms, tensor_shape = runtime.infer(frame)
            e2e_ms = (perf_counter() - loop_started) * 1000
            model_times.append(model_ms); e2e_times.append(e2e_ms)
            for det in detections:
                x1, y1, x2, y2 = det.box
                detection_writer.writerow(dict(zip(DETECTION_FIELDS, [
                    run_id, args.phase, frame_id, round(timestamp_ms, 3), det.class_id,
                    det.canonical_class, det.prompt, round(det.confidence, 6), round(x1, 2),
                    round(y1, 2), round(x2, 2), round(y2, 2), width, height,
                    round(model_ms, 3), round(e2e_ms, 3)])))
            inference_fps = 1000 / model_ms if model_ms else 0
            frame_writer.writerow(dict(zip(FRAME_FIELDS, [run_id, frame_id, round(timestamp_ms, 3),
                True, True, 0, 0, round(model_ms, 3), round(e2e_ms, 3), round(camera_fps, 3),
                round(inference_fps, 3), round(runtime.memory_mb(), 2)])))
            if overlay:
                overlay.write(draw_detections(frame, detections, f"model {model_ms:.1f} ms | {inference_fps:.1f} FPS"))
            frame_id += 1
            if frame_id % 25 == 0:
                print(f"Da xu ly {frame_id}/{total or '?'} frame", flush=True)
    finally:
        capture.release()
        if overlay: overlay.release()
        detection_handle.close(); frame_handle.close()
    if not model_times:
        raise SystemExit("Video khong co frame doc duoc")
    summary = {
        "run_id": run_id, "phase": args.phase, "created_at_utc": utc_now(),
        "source_video": str(args.video.resolve()), "model_id": config["model_id"],
        "prompt_file": str(args.prompts.resolve()), "prompt_count": len(prompts),
        "prompts": prompts, "config": config, "software": software_info(),
        "frame_width": width, "frame_height": height, "camera_fps": camera_fps,
        "input_tensor_shape": tensor_shape, "processed_frames": frame_id,
        "timing": {
            "model_mean_ms": statistics.mean(model_times), "model_median_ms": statistics.median(model_times),
            "model_p95_ms": percentile(model_times, .95), "model_std_ms": statistics.pstdev(model_times),
            "e2e_mean_ms": statistics.mean(e2e_times), "e2e_median_ms": statistics.median(e2e_times),
            "e2e_p95_ms": percentile(e2e_times, .95), "e2e_std_ms": statistics.pstdev(e2e_times),
            "model_fps_from_mean": 1000 / statistics.mean(model_times),
            "peak_allocated_vram_mb": runtime.peak_memory_mb(),
        },
    }
    write_json(run_dir / "config.json", summary)
    print(f"Hoan tat: {run_dir}")


if __name__ == "__main__":
    main()
