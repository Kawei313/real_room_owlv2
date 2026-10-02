from __future__ import annotations

import csv
import json
import platform
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]


def read_json(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str | Path, data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def read_prompts(path: str | Path) -> list[str]:
    prompts = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            prompts.append(line)
    if not prompts:
        raise ValueError(f"Khong co prompt hop le trong {path}")
    if len(prompts) != len(set(prompts)):
        raise ValueError(f"Prompt bi trung trong {path}")
    return prompts


def read_synonyms(path: str | Path | None) -> dict[str, str]:
    if not path:
        return {}
    target = Path(path)
    if not target.exists():
        return {}
    with target.open(encoding="utf-8", newline="") as handle:
        return {row["prompt"].strip(): row["canonical_class"].strip() for row in csv.DictReader(handle)}


def make_run_id(prefix: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9_-]+", "-", prefix).strip("-")
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{clean}"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def command_output(command: list[str]) -> str | None:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=8, check=False)
        text = (result.stdout + result.stderr).strip()
        return text or None
    except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError):
        return None


def software_info() -> dict[str, Any]:
    result: dict[str, Any] = {
        "python": sys.version.split()[0],
        "platform": platform.platform(),
    }
    for name in ("torch", "torchvision", "transformers", "cv2", "pyrealsense2"):
        try:
            module = __import__(name)
            result[name] = getattr(module, "__version__", "installed-version-unknown")
        except ImportError:
            result[name] = None
    return result


DETECTION_FIELDS = [
    "run_id", "phase", "frame_id", "timestamp_ms", "class_id", "canonical_class",
    "prompt", "confidence", "x1", "y1", "x2", "y2", "frame_width", "frame_height",
    "model_ms", "end_to_end_ms",
]
FRAME_FIELDS = [
    "run_id", "frame_id", "timestamp_ms", "capture_ok", "processed", "dropped",
    "queue_size", "model_ms", "end_to_end_ms", "camera_fps", "inference_fps",
    "allocated_vram_mb",
]
EVENT_FIELDS = ["run_id", "timestamp_utc", "event", "details"]


def open_csv(path: Path, fields: list[str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("w", encoding="utf-8", newline="")
    writer = csv.DictWriter(handle, fieldnames=fields)
    writer.writeheader()
    return handle, writer


def percentile(values: Iterable[float], p: float) -> float | None:
    ordered = sorted(values)
    if not ordered:
        return None
    index = (len(ordered) - 1) * p
    lo, hi = int(index), min(int(index) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (index - lo)

