#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2

from common import ROOT, make_run_id, utc_now, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Ghi video RGB goc tu Intel RealSense")
    parser.add_argument("--name", choices=["room_val", "room_test"], required=True)
    parser.add_argument("--duration", type=float, default=60, help="So giay ghi; 0 de dung bang Ctrl+C")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--warmup", type=float, default=3)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or ROOT / "videos" / f"{args.name}_raw.mp4"
    if output.exists():
        raise SystemExit(f"Khong ghi de video da ton tai: {output}. Hay doi --output hoac sao luu file cu.")
    try:
        import pyrealsense2 as rs
    except ImportError as exc:
        raise SystemExit("Thieu pyrealsense2. Hay cai librealsense Python bindings.") from exc

    pipeline, cfg = rs.pipeline(), rs.config()
    cfg.enable_stream(rs.stream.color, args.width, args.height, rs.format.bgr8, args.fps)
    profile = pipeline.start(cfg)
    output.parent.mkdir(parents=True, exist_ok=True)
    writer = cv2.VideoWriter(str(output), cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (args.width, args.height))
    if not writer.isOpened():
        pipeline.stop()
        raise SystemExit(f"Khong mo duoc VideoWriter: {output}")
    sensor_profile = profile.get_stream(rs.stream.color).as_video_stream_profile()
    intr = sensor_profile.get_intrinsics()
    device = profile.get_device()
    metadata = {
        "run_id": make_run_id(f"record_{args.name}"), "started_at_utc": utc_now(),
        "output": str(output), "width": args.width, "height": args.height, "fps": args.fps,
        "camera": {
            "model": device.get_info(rs.camera_info.name),
            "serial": device.get_info(rs.camera_info.serial_number),
            "firmware": device.get_info(rs.camera_info.firmware_version),
            "usb_type": device.get_info(rs.camera_info.usb_type_descriptor) if device.supports(rs.camera_info.usb_type_descriptor) else None,
            "intrinsics": {"fx": intr.fx, "fy": intr.fy, "ppx": intr.ppx, "ppy": intr.ppy,
                           "model": str(intr.model), "coeffs": list(intr.coeffs)},
        },
        "frames": 0,
    }
    try:
        warmup_until = time.monotonic() + args.warmup
        while time.monotonic() < warmup_until:
            pipeline.wait_for_frames()
        started = time.monotonic()
        while args.duration <= 0 or time.monotonic() - started < args.duration:
            frame = pipeline.wait_for_frames().get_color_frame()
            if not frame:
                continue
            import numpy as np
            image = np.asanyarray(frame.get_data())
            writer.write(image)
            metadata["frames"] += 1
            if args.preview:
                cv2.imshow("RealSense recording - q to stop", image)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break
    except KeyboardInterrupt:
        pass
    finally:
        writer.release()
        pipeline.stop()
        cv2.destroyAllWindows()
    metadata["ended_at_utc"] = utc_now()
    metadata["duration_seconds"] = round(metadata["frames"] / args.fps, 3)
    write_json(output.with_suffix(".json"), metadata)
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

