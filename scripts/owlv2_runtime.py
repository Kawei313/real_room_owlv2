from __future__ import annotations

from contextlib import nullcontext
from dataclasses import dataclass
from time import perf_counter
from typing import Any

import cv2
import numpy as np


@dataclass
class Detection:
    class_id: int
    prompt: str
    canonical_class: str
    confidence: float
    box: tuple[float, float, float, float]


class Owlv2Runtime:
    def __init__(self, config: dict[str, Any], prompts: list[str], synonyms: dict[str, str]):
        try:
            import torch
            from transformers import Owlv2ForObjectDetection, Owlv2Processor
        except ImportError as exc:
            raise RuntimeError("Thieu torch/transformers. Xem README.md de cai moi truong.") from exc

        requested = config.get("device", "cuda")
        if requested == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("Cau hinh yeu cau CUDA nhung torch.cuda.is_available() = False")
        self.torch = torch
        self.device = torch.device(requested)
        self.prompts = prompts
        self.synonyms = synonyms
        self.threshold = float(config["threshold"])
        self.nms_iou = float(config["nms_iou"])
        self.max_detections = int(config["max_detections"])
        self.fp16 = config.get("precision", "fp16") == "fp16" and self.device.type == "cuda"
        self.processor = Owlv2Processor.from_pretrained(config["model_id"])
        dtype = torch.float16 if self.fp16 else torch.float32
        self.model = Owlv2ForObjectDetection.from_pretrained(config["model_id"], torch_dtype=dtype)
        self.model.to(self.device).eval()

    def _sync(self) -> None:
        if self.device.type == "cuda":
            self.torch.cuda.synchronize(self.device)

    def infer(self, frame_bgr: np.ndarray) -> tuple[list[Detection], float, tuple[int, ...]]:
        torch = self.torch
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        inputs = self.processor(text=[self.prompts], images=rgb, return_tensors="pt")
        inputs = {key: value.to(self.device) for key, value in inputs.items()}
        self._sync()
        started = perf_counter()
        autocast = torch.autocast(device_type="cuda", dtype=torch.float16) if self.fp16 else nullcontext()
        with torch.inference_mode(), autocast:
            outputs = self.model(**inputs)
        target_sizes = torch.tensor([frame_bgr.shape[:2]], device=self.device)
        result = self.processor.post_process_object_detection(
            outputs=outputs, target_sizes=target_sizes, threshold=self.threshold
        )[0]
        self._sync()
        model_ms = (perf_counter() - started) * 1000.0

        boxes = result["boxes"].detach().float().cpu()
        scores = result["scores"].detach().float().cpu()
        labels = result["labels"].detach().long().cpu()
        keep = self._class_aware_nms(boxes, scores, labels)
        detections = []
        for index in keep[: self.max_detections]:
            class_id = int(labels[index])
            prompt = self.prompts[class_id]
            detections.append(Detection(
                class_id=class_id,
                prompt=prompt,
                canonical_class=self.synonyms.get(prompt, prompt),
                confidence=float(scores[index]),
                box=tuple(float(v) for v in boxes[index].tolist()),
            ))
        tensor_shape = tuple(inputs["pixel_values"].shape)
        return detections, model_ms, tensor_shape

    def _class_aware_nms(self, boxes, scores, labels) -> list[int]:
        if len(boxes) == 0:
            return []
        try:
            from torchvision.ops import batched_nms
            keep = batched_nms(boxes, scores, labels, self.nms_iou)
            return keep.tolist()
        except (ImportError, RuntimeError):
            return scores.argsort(descending=True).tolist()

    def warmup(self, width: int, height: int, count: int) -> None:
        dummy = np.zeros((height, width, 3), dtype=np.uint8)
        for _ in range(count):
            self.infer(dummy)
        if self.device.type == "cuda":
            self.torch.cuda.reset_peak_memory_stats(self.device)

    def memory_mb(self) -> float:
        if self.device.type != "cuda":
            return 0.0
        return self.torch.cuda.memory_allocated(self.device) / (1024 ** 2)

    def peak_memory_mb(self) -> float:
        if self.device.type != "cuda":
            return 0.0
        return self.torch.cuda.max_memory_allocated(self.device) / (1024 ** 2)


def draw_detections(frame: np.ndarray, detections: list[Detection], status: str = "") -> np.ndarray:
    canvas = frame.copy()
    for detection in detections:
        x1, y1, x2, y2 = (int(v) for v in detection.box)
        cv2.rectangle(canvas, (x1, y1), (x2, y2), (20, 220, 20), 2)
        label = f"{detection.canonical_class} {detection.confidence:.2f}"
        cv2.putText(canvas, label, (x1, max(20, y1 - 7)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (20, 220, 20), 2)
    if status:
        cv2.putText(canvas, status, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 230, 255), 2)
    return canvas
