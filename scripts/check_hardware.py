#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from common import ROOT, command_output, software_info, utc_now, write_json


def realsense_info() -> dict:
    try:
        import pyrealsense2 as rs
    except ImportError:
        return {"available": False, "error": "pyrealsense2 not installed"}
    devices = []
    try:
        for device in rs.context().query_devices():
            data = {}
            for key, label in (
                (rs.camera_info.name, "model"),
                (rs.camera_info.serial_number, "serial"),
                (rs.camera_info.firmware_version, "firmware"),
                (rs.camera_info.usb_type_descriptor, "usb_type"),
            ):
                data[label] = device.get_info(key) if device.supports(key) else None
            devices.append(data)
        return {"available": True, "devices": devices}
    except Exception as exc:  # SDK/device errors must still be recorded.
        return {"available": False, "error": str(exc), "devices": devices}


def torch_info() -> dict:
    try:
        import torch
    except ImportError:
        return {"installed": False, "cuda_available": False}
    available = torch.cuda.is_available()
    return {
        "installed": True,
        "version": torch.__version__,
        "cuda_available": available,
        "torch_cuda": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0) if available else None,
        "device_total_memory_mb": round(torch.cuda.get_device_properties(0).total_memory / 1024**2, 1) if available else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Kiem tra Jetson, CUDA va Intel RealSense")
    parser.add_argument("--output", type=Path, default=ROOT / "hardware.json")
    args = parser.parse_args()
    report = {
        "captured_at_utc": utc_now(),
        "software": software_info(),
        "torch": torch_info(),
        "realsense": realsense_info(),
        "jetson": {
            "l4t": command_output(["cat", "/etc/nv_tegra_release"]),
            "nvpmodel": command_output(["nvpmodel", "-q"]),
            "tegrastats_sample": command_output(["tegrastats", "--interval", "1000", "--count", "1"]),
        },
        "usb": command_output(["lsusb"]),
        "realsense_cli": command_output(["rs-enumerate-devices", "-s"]),
    }
    write_json(args.output, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if not report["torch"]["cuda_available"]:
        print("\nCANH BAO: PyTorch chua nhan CUDA.")
    devices = report["realsense"].get("devices", [])
    if not devices:
        print("CANH BAO: Chua tim thay RealSense.")
    elif not all(str(d.get("usb_type", "")).startswith("3") for d in devices):
        print("CANH BAO: Camera co the khong chay o USB 3.x.")


if __name__ == "__main__":
    main()

