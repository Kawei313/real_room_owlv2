#!/usr/bin/env python3
"""Export a ROS 2 sensor_msgs image topic from a rosbag2 SQLite bag to MP4."""
from __future__ import annotations

import argparse
from pathlib import Path


SUPPORTED_TYPES = {"sensor_msgs/msg/Image", "sensor_msgs/msg/CompressedImage"}


def select_topic(topic_types: dict[str, str], requested: str) -> tuple[str, str]:
    if requested != "auto":
        if requested not in topic_types:
            available = "\n".join(f"  {name} [{kind}]" for name, kind in sorted(topic_types.items()))
            raise ValueError(f"Khong tim thay topic {requested}. Cac topic hien co:\n{available}")
        message_type = topic_types[requested]
        if message_type not in SUPPORTED_TYPES:
            raise ValueError(f"Topic {requested} co type khong duoc ho tro: {message_type}")
        return requested, message_type

    candidates = [(name, kind) for name, kind in topic_types.items() if kind in SUPPORTED_TYPES]
    if not candidates:
        raise ValueError("Bag khong co sensor_msgs/msg/Image hoac sensor_msgs/msg/CompressedImage")
    color = [item for item in candidates if "color" in item[0].lower() and "depth" not in item[0].lower()]
    preferred = [item for item in color if "image_raw" in item[0].lower()]
    return (preferred or color or candidates)[0]


def main() -> None:
    parser = argparse.ArgumentParser(description="Chuyen topic anh mau trong ROS 2 bag .db3 sang MP4")
    parser.add_argument("--bag", type=Path, required=True, help="Thu muc bag chua metadata.yaml va file .db3")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--topic", default="auto", help="Ten topic anh; mac dinh tu dong chon color image")
    parser.add_argument("--fps", type=float, default=30.0, help="FPS cua MP4 dau ra")
    parser.add_argument("--codec", default="mp4v", help="FourCC OpenCV, mac dinh mp4v")
    parser.add_argument("--max-frames", type=int, default=0, help="0 = xuat tat ca")
    args = parser.parse_args()

    metadata = args.bag / "metadata.yaml"
    if not args.bag.is_dir():
        raise SystemExit(f"--bag phai la thu muc ROS 2 bag: {args.bag}")
    if not metadata.exists():
        raise SystemExit(
            f"Thieu {metadata}. Chay: ros2 bag reindex {args.bag}\n"
            "sau do thu lai lenh chuyen doi."
        )
    try:
        import cv2
        import numpy as np
        import rosbag2_py
        from cv_bridge import CvBridge
        from rclpy.serialization import deserialize_message
        from rosidl_runtime_py.utilities import get_message
    except ImportError as exc:
        raise SystemExit(
            "Thieu ROS 2 Python/OpenCV dependencies. Hay source /opt/ros/<distro>/setup.bash "
            "va cai ros-<distro>-cv-bridge, ros-<distro>-rosbag2-py."
        ) from exc

    reader = rosbag2_py.SequentialReader()
    reader.open(
        rosbag2_py.StorageOptions(uri=str(args.bag.resolve()), storage_id="sqlite3"),
        rosbag2_py.ConverterOptions(input_serialization_format="", output_serialization_format=""),
    )
    topic_types = {item.name: item.type for item in reader.get_all_topics_and_types()}
    try:
        topic, message_type = select_topic(topic_types, args.topic)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    message_class = get_message(message_type)
    bridge = CvBridge()
    writer = None
    written = 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    print(f"Topic: {topic} [{message_type}]")
    try:
        while reader.has_next() and (args.max_frames <= 0 or written < args.max_frames):
            current_topic, raw, _timestamp_ns = reader.read_next()
            if current_topic != topic:
                continue
            message = deserialize_message(raw, message_class)
            if message_type == "sensor_msgs/msg/CompressedImage":
                frame = cv2.imdecode(np.frombuffer(message.data, dtype=np.uint8), cv2.IMREAD_COLOR)
            else:
                frame = bridge.imgmsg_to_cv2(message, desired_encoding="bgr8")
            if frame is None:
                continue
            if writer is None:
                height, width = frame.shape[:2]
                writer = cv2.VideoWriter(
                    str(args.output), cv2.VideoWriter_fourcc(*args.codec), args.fps, (width, height)
                )
                if not writer.isOpened():
                    raise RuntimeError(f"Khong tao duoc video: {args.output}")
                print(f"Output: {args.output} ({width}x{height} @ {args.fps:g} FPS)")
            writer.write(frame)
            written += 1
            if written % 300 == 0:
                print(f"Da ghi {written} frame", flush=True)
    finally:
        if writer is not None:
            writer.release()
    if written == 0:
        raise SystemExit("Khong doc duoc frame nao tu topic da chon")
    print(f"Hoan tat: {written} frame -> {args.output}")


if __name__ == "__main__":
    main()
