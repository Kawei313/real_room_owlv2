#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import html
import json
from collections import Counter
from pathlib import Path

from common import ROOT


def main() -> None:
    parser = argparse.ArgumentParser(description="Tao bao cao HTML tu cac run OWLv2")
    parser.add_argument("runs", nargs="*", type=Path, help="Thu muc run; mac dinh lay tat ca runs/*")
    parser.add_argument("--output", type=Path, default=ROOT / "report/real_room_owlv2_report.html")
    args = parser.parse_args()
    run_dirs = args.runs or sorted((ROOT / "runs").glob("*"))
    rows = []
    for run_dir in run_dirs:
        config_path, detections_path = run_dir / "config.json", run_dir / "detections.csv"
        if not config_path.exists() or not detections_path.exists(): continue
        cfg = json.loads(config_path.read_text(encoding="utf-8"))
        with detections_path.open(encoding="utf-8", newline="") as handle:
            detections = list(csv.DictReader(handle))
        classes = Counter(row["canonical_class"] for row in detections)
        timing = cfg.get("timing", {})
        rows.append({"id": cfg.get("run_id", run_dir.name), "phase": cfg.get("phase", "?"),
            "frames": cfg.get("processed_frames", 0), "prompts": cfg.get("prompt_count", len(cfg.get("prompts", []))),
            "detections": len(detections), "classes": ", ".join(f"{k}: {v}" for k, v in classes.most_common()),
            "model_ms": timing.get("model_mean_ms"), "p95": timing.get("model_p95_ms"),
            "fps": timing.get("model_fps_from_mean"), "memory": timing.get("peak_allocated_vram_mb", cfg.get("peak_allocated_vram_mb"))})
    def fmt(value): return "—" if value is None else f"{value:.2f}" if isinstance(value, float) else str(value)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(fmt(row[key]))}</td>" for key in
        ("id", "phase", "frames", "prompts", "detections", "model_ms", "p95", "fps", "memory", "classes")) + "</tr>" for row in rows)
    document = f"""<!doctype html><html lang='vi'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'>
<title>Real-room OWLv2 report</title><style>body{{font:15px system-ui;margin:2rem;color:#17202a}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #ccd1d1;padding:.55rem;text-align:left}}th{{background:#eef3f5}}tr:nth-child(even){{background:#fafafa}}.note{{color:#566573}}</style></head>
<body><h1>Real-room OWLv2 test</h1><p class='note'>Báo cáo tự động từ dữ liệu run. Việc đánh giá TP/FP/FN cần annotation/inventory đối chiếu thủ công.</p>
<table><thead><tr><th>Run</th><th>Phase</th><th>Frames</th><th>Prompts</th><th>Detections</th><th>Mean model ms</th><th>P95 ms</th><th>FPS</th><th>Peak MB</th><th>Detections theo class</th></tr></thead><tbody>{body}</tbody></table></body></html>"""
    args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(document, encoding="utf-8")
    print(f"Da tao: {args.output}")


if __name__ == "__main__":
    main()

