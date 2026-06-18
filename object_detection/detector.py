"""Detector module — supports both standard YOLOv8 and YOLOWorld open-vocabulary models."""

from typing import Any, Optional
import numpy as np

try:
    from ultralytics import YOLO
except ImportError as e:
    raise ImportError("ultralytics package is required. Run: pip install ultralytics") from e


def compute_iou(box1: list[int], box2: list[int]) -> float:
    """Computes Intersection over Union (IoU) between two bounding boxes."""
    xi1 = max(box1[0], box2[0])
    yi1 = max(box1[1], box2[1])
    xi2 = min(box1[2], box2[2])
    yi2 = min(box1[3], box2[3])
    inter_area = max(0, xi2 - xi1) * max(0, yi2 - yi1)
    
    box1_area = (box1[2] - box1[0]) * (box1[3] - box1[1])
    box2_area = (box2[2] - box2[0]) * (box2[3] - box2[1])
    union_area = box1_area + box2_area - inter_area
    
    if union_area == 0:
        return 0.0
    return inter_area / union_area


class Detector:
    """Wraps YOLOv8 / YOLOWorld for clean inference.

    When USE_WORLD_MODEL=True the detector loads yolov8s-worldv2 and calls
    set_classes() so it can recognise hands, pens, fingers, faces — anything
    in WORLD_CLASSES — in addition to the standard 80 COCO categories.
    """

    def __init__(self, model_path: str, conf_threshold: float = 0.15,
                 device: str = "cpu", imgsz: int = 640) -> None:
        if not (0.0 <= conf_threshold <= 1.0):
            raise ValueError("Confidence threshold must be between 0.0 and 1.0.")

        self.conf_threshold: float = conf_threshold
        self.device: str = device
        self.imgsz: int = imgsz
        self.nms_iou: float = 0.45
        self.augment: bool = False
        self.class_ids: Optional[list[int]] = None
        self._is_world: bool = "world" in model_path.lower()

        # Load class-specific confidences and priorities from config
        try:
            from config import CLASS_CONF_THRESHOLDS, CLASS_PRIORITIES
            self.class_conf_thresholds = CLASS_CONF_THRESHOLDS
            self.class_priorities = CLASS_PRIORITIES
        except ImportError:
            self.class_conf_thresholds = {}
            self.class_priorities = {}

        # Optimize PyTorch thread configurations dynamically
        try:
            import torch
            import os
            # Avoid using virtual hyperthreads; use estimated physical cores (logical/2)
            cores = os.cpu_count()
            threads = max(2, min(cores // 2 if cores else 4, 6))
            torch.set_num_threads(threads)
            torch.set_num_interop_threads(1)
        except Exception:
            pass

        try:
            print(f"[detector] Loading model: {model_path}")
            self.model: YOLO = YOLO(model_path)
            if self._is_world:
                from config import WORLD_CLASSES
                self.model.set_classes(WORLD_CLASSES)
                print(f"[detector] YOLOWorld ready — {len(WORLD_CLASSES)} classes enabled.")
        except Exception as e:
            raise RuntimeError(
                f"Failed to load model from '{model_path}'. "
                f"Ensure the file exists or internet is available. Details: {e}"
            ) from e

    def update_world_classes(self, classes: list[str]) -> None:
        """Dynamically rewrites the custom vocabulary for YOLO-World."""
        if self._is_world:
            try:
                self.model.set_classes(classes)
                print(f"[detector] YOLOWorld vocabulary updated: {classes}")
            except Exception as e:
                print(f"[detector] Failed to update YOLOWorld vocabulary: {e}")

    # ── Inference ─────────────────────────────────────────────────────────────
    def detect(self, frame: np.ndarray, track: bool = False, imgsz: Optional[int] = None) -> list[dict[str, Any]]:
        """Runs detection on a single BGR frame.

        Returns a list of dicts with keys:
            class_id, class_name, confidence, bbox [x1,y1,x2,y2], track_id
        """
        detections: list[dict[str, Any]] = []

        # Determine minimum confidence threshold to pass to YOLO to capture all candidate boxes
        min_conf = self.conf_threshold
        if self.class_conf_thresholds:
            min_conf = min(min_conf, min(self.class_conf_thresholds.values()))

        run_kwargs = dict(
            conf=min_conf,
            device=self.device,
            verbose=False,
            imgsz=imgsz if imgsz is not None else self.imgsz,
            iou=self.nms_iou,  # Dynamically adjustable NMS IoU
            augment=self.augment,  # Dynamic TTA (Test-Time Augmentation) accuracy booster
            agnostic_nms=False,  # per-class NMS allows multiple overlapping categories
            max_det=300,    # detect up to 300 objects per frame
        )

        try:
            import torch
            context = torch.inference_mode()
        except (ImportError, AttributeError):
            import contextlib
            context = contextlib.nullcontext()

        with context:
            if track:
                results = self.model.track(
                    frame,
                    persist=True,
                    tracker="bytetrack.yaml",
                    **run_kwargs,
                )
            else:
                results = self.model(frame, **run_kwargs)

        if not results:
            return detections

        result = results[0]
        if result.boxes is None:
            return detections

        low_conf_persons = []

        for i, box in enumerate(result.boxes):
            class_id   = int(box.cls[0].item())
            confidence = float(box.conf[0].item())

            if self.class_ids is not None and class_id not in self.class_ids:
                continue

            xyxy = box.xyxy[0].tolist()
            bbox = [int(xyxy[0]), int(xyxy[1]), int(xyxy[2]), int(xyxy[3])]
            class_name = self.model.names.get(class_id, "unknown")
            track_id   = int(box.id[0].item()) if box.id is not None else None

            # Save low-confidence person candidate boxes to override false animal detections later
            if class_name == "person" and confidence >= 0.15:
                low_conf_persons.append({
                    "class_id": class_id,
                    "class_name": class_name,
                    "confidence": confidence,
                    "bbox": bbox,
                    "track_id": track_id
                })

            # Apply class-specific confidence threshold override
            required_conf = self.class_conf_thresholds.get(class_name, self.conf_threshold)
            if confidence < required_conf:
                continue

            polygon_pts = None
            if result.masks is not None:
                try:
                    poly = result.masks.xy[i]
                    if poly is not None and len(poly) > 0:
                        polygon_pts = poly.astype(np.int32).tolist()
                except Exception:
                    pass

            detections.append({
                "class_id":   class_id,
                "class_name": class_name,
                "confidence": confidence,
                "bbox":       bbox,
                "track_id":   track_id,
                "polygon":    polygon_pts,
            })

        # Apply low-confidence person override rule to resolve animal false positives
        frame_h, frame_w = frame.shape[:2]
        frame_area = frame_w * frame_h
        for d in detections:
            if d["class_name"] in ["cat", "dog", "bird"]:
                # Size heuristic: if the "animal" box is >15% of frame, it's likely a person
                bw = d["bbox"][2] - d["bbox"][0]
                bh = d["bbox"][3] - d["bbox"][1]
                box_area = bw * bh
                is_large_box = (box_area / frame_area) > 0.15

                overridden = False
                for pb in low_conf_persons:
                    if compute_iou(d["bbox"], pb["bbox"]) > 0.25:
                        # Correct classification to person
                        d["class_id"] = pb["class_id"]
                        d["class_name"] = "person"
                        d["confidence"] = max(d["confidence"], pb["confidence"])
                        if pb["track_id"] is not None:
                            d["track_id"] = pb["track_id"]
                        overridden = True
                        break

                # Large box fallback: override even without a matching person candidate
                if not overridden and is_large_box:
                    d["class_name"] = "person"
                    d["class_id"] = 0  # COCO person class ID

        # Post-NMS Deduplication: suppress box overlaps of different classes on the same physical object
        # Sort by (confidence * priority) so that high-priority classes (e.g. person) resolve overlap conflicts first
        detections.sort(
            key=lambda x: x["confidence"] * self.class_priorities.get(x["class_name"], 1),
            reverse=True
        )
        keep = []
        for d in detections:
            overlap = False
            for kept in keep:
                # Use a strict IoU threshold of 0.45 to deduplicate overlapping classes on the same physical object
                if compute_iou(d["bbox"], kept["bbox"]) > 0.45:
                    overlap = True
                    break
            if not overlap:
                keep.append(d)

        return keep

    # ── Config updates ────────────────────────────────────────────────────────
    def set_conf(self, threshold: float) -> None:
        if not (0.0 <= threshold <= 1.0):
            raise ValueError("Confidence threshold must be between 0.0 and 1.0.")
        self.conf_threshold = threshold

    def set_iou(self, iou: float) -> None:
        if not (0.0 <= iou <= 1.0):
            raise ValueError("IoU threshold must be between 0.0 and 1.0.")
        self.nms_iou = iou

    def set_augment(self, augment: bool) -> None:
        self.augment = augment

    def filter_classes(self, class_ids: Optional[list[int]]) -> None:
        self.class_ids = class_ids if class_ids else None
