"""Utility module for visual overlays, resizing, and performance metrics."""

from collections import deque
import time
from typing import Any, Optional
import cv2
import numpy as np

from config import (
    BOX_THICKNESS,
    CLASS_COLORS,
    FONT,
    FONT_SCALE,
    FONT_THICKNESS,
    NAMED_CLASS_COLORS,
    OVERLAY_ALPHA,
    OVERLAY_BG_COLOR,
    TEXT_COLOR,
)


class FPSCounter:
    """Measures processing performance using a rolling average over the last N frames."""

    def __init__(self, window_size: int = 30) -> None:
        self.window_size: int = window_size
        self.timestamps: deque[float] = deque(maxlen=window_size)

    def update(self) -> None:
        self.timestamps.append(time.perf_counter())

    def get_fps(self) -> float:
        if len(self.timestamps) < 2:
            return 0.0
        duration = self.timestamps[-1] - self.timestamps[0]
        if duration <= 0:
            return 0.0
        return (len(self.timestamps) - 1) / duration


def resize_frame(frame: np.ndarray, width: Optional[int]) -> np.ndarray:
    """Resizes a BGR frame while keeping its original aspect ratio."""
    if width is None or width <= 0:
        return frame
    h, w = frame.shape[:2]
    if w == width:
        return frame
    aspect_ratio = h / w
    height = int(width * aspect_ratio)
    return cv2.resize(frame, (width, height), interpolation=cv2.INTER_LINEAR)


def draw_boxes(
    frame: np.ndarray,
    detections: list[dict[str, Any]],
    tracker: Optional[Any] = None,
    line_pos: float = 0.5,
    line_dir: str = "horizontal",
    draw_line: bool = False
) -> np.ndarray:
    """Draws bold, high-visibility bounding boxes with solid labels.

    Args:
        frame: The BGR image frame (numpy array) to draw on.
        detections: List of detection dictionaries from the Detector.
        tracker: Optional TrackTracker instance to retrieve trails and counts.
        line_pos: Relative position of counting line (0.0 to 1.0).
        line_dir: Direction of the line ('horizontal' or 'vertical').
        draw_line: Whether to draw the counting line and crossing tallies overlay.

    Returns:
        A copy of the frame with bounding boxes and text labels drawn.
    """
    annotated_frame = frame.copy()
    h, w = frame.shape[:2]

    # 1. Draw counting line if requested
    if draw_line:
        if line_dir == "horizontal":
            line_coord = int(line_pos * h)
            cv2.line(annotated_frame, (0, line_coord), (w, line_coord), (0, 255, 180), 2)
            cv2.putText(annotated_frame, "Counting Line", (10, line_coord - 6),
                        FONT, 0.45, (0, 255, 180), 1, lineType=cv2.LINE_AA)
        else:
            line_coord = int(line_pos * w)
            cv2.line(annotated_frame, (line_coord, 0), (line_coord, h), (0, 255, 180), 2)
            cv2.putText(annotated_frame, "Counting Line", (line_coord + 6, 20),
                        FONT, 0.45, (0, 255, 180), 1, lineType=cv2.LINE_AA)

    # 2. Draw historical trails if tracker is provided
    if tracker is not None:
        for track_id, points in tracker.tracks.items():
            if len(points) < 2:
                continue
            color = (0, 229, 255)
            for det in detections:
                if det.get("track_id") == track_id:
                    color = CLASS_COLORS[det["class_id"] % len(CLASS_COLORS)]
                    break
            for i in range(1, len(points)):
                thickness = int(np.sqrt(BOX_THICKNESS * float(i + 1)))
                cv2.line(annotated_frame, points[i - 1], points[i], color, thickness)

    # 3. Draw each detection — solid box + filled label pill
    for detection in detections:
        bbox        = detection["bbox"]
        class_id    = detection["class_id"]
        class_name  = detection["class_name"]
        confidence  = detection["confidence"]
        track_id    = detection.get("track_id")

        x1, y1, x2, y2 = bbox

        # Pick color: use named override if available, else generic palette
        color = NAMED_CLASS_COLORS.get(class_name, CLASS_COLORS[class_id % len(CLASS_COLORS)])

        # ── a) Draw segmentation polygon if available, else solid box ─────
        polygon = detection.get("polygon")
        if polygon is not None and len(polygon) > 0:
            pts = np.array(polygon, np.int32).reshape((-1, 1, 2))
            overlay = annotated_frame.copy()
            cv2.fillPoly(overlay, [pts], color)
            cv2.addWeighted(overlay, 0.22, annotated_frame, 0.78, 0, annotated_frame)
            cv2.polylines(annotated_frame, [pts], True, color, 2, lineType=cv2.LINE_AA)
        else:
            # Solid bold bounding box
            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, BOX_THICKNESS, lineType=cv2.LINE_AA)

        # ── b) Build label text ───────────────────────────────────────────
        if track_id is not None:
            label = f"#{track_id} {class_name} {confidence:.0%}"
        else:
            label = f"{class_name} {confidence:.0%}"

        # Scale font relative to frame width for readability
        font_scale = max(0.5, min(0.7, w / 900))
        thickness = 1 if w < 800 else 2

        (text_w, text_h), baseline = cv2.getTextSize(label, FONT, font_scale, thickness)

        # ── c) Solid color label background ───────────────────────────────
        pad_x, pad_y = 8, 5
        lbl_x1 = x1
        lbl_y1 = max(0, y1 - text_h - pad_y * 2 - 2)
        lbl_x2 = x1 + text_w + pad_x * 2
        lbl_y2 = y1

        # Fallback: draw label inside box if it goes off screen
        if lbl_y1 < 1:
            lbl_y1 = y1
            lbl_y2 = y1 + text_h + pad_y * 2 + 2

        # Solid colored label background
        cv2.rectangle(annotated_frame, (lbl_x1, lbl_y1), (lbl_x2, lbl_y2), color, cv2.FILLED)

        # White text on colored background
        cv2.putText(
            annotated_frame, label,
            (lbl_x1 + pad_x, lbl_y2 - baseline - pad_y),
            FONT, font_scale, (255, 255, 255), thickness, lineType=cv2.LINE_AA,
        )

    # 4. Draw counts summary overlay if tracker has data
    if tracker is not None and len(tracker.counts) > 0 and draw_line:
        summary_lines = ["Line Crossings:"]
        for cls, d in tracker.counts.items():
            summary_lines.append(f" {cls}: {d['in']} In | {d['out']} Out")

        max_lw, total_lh = 0, 0
        line_metrics = []
        for line in summary_lines:
            (lw, lh), lb = cv2.getTextSize(line, FONT, 0.45, 1)
            max_lw = max(max_lw, lw)
            line_metrics.append((lh, lb))
            total_lh += lh + lb + 4

        px1, py1 = 10, h - total_lh - 20
        px2, py2 = 10 + max_lw + 16, h - 10

        ov2 = annotated_frame.copy()
        cv2.rectangle(ov2, (px1, py1), (px2, py2), OVERLAY_BG_COLOR, cv2.FILLED)
        cv2.addWeighted(ov2, OVERLAY_ALPHA, annotated_frame, 1 - OVERLAY_ALPHA, 0, annotated_frame)

        curr_y = py1 + 15
        for line, (lh, lb) in zip(summary_lines, line_metrics):
            cv2.putText(annotated_frame, line, (px1 + 5, curr_y),
                        FONT, 0.45, TEXT_COLOR, 1, lineType=cv2.LINE_AA)
            curr_y += lh + lb + 4

    return annotated_frame


def draw_fps(frame: np.ndarray, fps: float) -> np.ndarray:
    """Draws the running frame rate in the top-right corner."""
    annotated_frame = frame.copy()
    fps_text = f"FPS {fps:.1f}"

    (tw, th), baseline = cv2.getTextSize(fps_text, FONT, 0.50, 1)
    frame_w = annotated_frame.shape[1]
    pad = 6
    x1 = frame_w - tw - pad * 2 - 8
    y1 = 8
    x2 = frame_w - 8
    y2 = 8 + th + pad * 2 + baseline

    overlay = annotated_frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), OVERLAY_BG_COLOR, cv2.FILLED)
    cv2.addWeighted(overlay, OVERLAY_ALPHA, annotated_frame, 1 - OVERLAY_ALPHA, 0, annotated_frame)

    cv2.putText(
        annotated_frame, fps_text,
        (x1 + pad, y2 - baseline - pad // 2),
        FONT, 0.50, TEXT_COLOR, 1, lineType=cv2.LINE_AA,
    )
    return annotated_frame


def draw_info(frame: np.ndarray, model_name: str, conf_threshold: float) -> np.ndarray:
    """Draws model info in the top-left corner."""
    annotated_frame = frame.copy()
    info_text = f"Conf {conf_threshold:.2f}"

    (tw, th), baseline = cv2.getTextSize(info_text, FONT, 0.50, 1)
    pad = 6
    x1, y1 = 8, 8
    x2, y2 = 8 + tw + pad * 2, 8 + th + pad * 2 + baseline

    overlay = annotated_frame.copy()
    cv2.rectangle(overlay, (x1, y1), (x2, y2), OVERLAY_BG_COLOR, cv2.FILLED)
    cv2.addWeighted(overlay, OVERLAY_ALPHA, annotated_frame, 1 - OVERLAY_ALPHA, 0, annotated_frame)

    cv2.putText(
        annotated_frame, info_text,
        (x1 + pad, y2 - baseline - pad // 2),
        FONT, 0.50, TEXT_COLOR, 1, lineType=cv2.LINE_AA,
    )
    return annotated_frame


def draw_active_tallies(frame: np.ndarray, detections: list[dict[str, Any]]) -> np.ndarray:
    """Draws a neat on-screen tally box of currently visible object counts."""
    if not detections:
        return frame
        
    counts: dict[str, int] = {}
    for d in detections:
        name = d["class_name"]
        counts[name] = counts.get(name, 0) + 1
        
    annotated_frame = frame.copy()
    h, w = frame.shape[:2]
    
    tally_lines = ["Visible Objects:"]
    for name, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
        tally_lines.append(f" {name}: {count}")
        
    max_lw, total_lh = 0, 0
    line_metrics = []
    for line in tally_lines:
        (lw, lh), lb = cv2.getTextSize(line, FONT, 0.45, 1)
        max_lw = max(max_lw, lw)
        line_metrics.append((lh, lb))
        total_lh += lh + lb + 4
        
    px1, py1 = 8, 45
    px2, py2 = 8 + max_lw + 16, 45 + total_lh + 10
    
    if py2 > h:
        return frame
        
    overlay = annotated_frame.copy()
    cv2.rectangle(overlay, (px1, py1), (px2, py2), OVERLAY_BG_COLOR, cv2.FILLED)
    cv2.addWeighted(overlay, OVERLAY_ALPHA, annotated_frame, 1 - OVERLAY_ALPHA, 0, annotated_frame)
    
    curr_y = py1 + 15
    for i, (line, (lh, lb)) in enumerate(zip(tally_lines, line_metrics)):
        color = TEXT_COLOR
        if i == 0:
            color = (0, 240, 255)
        cv2.putText(annotated_frame, line, (px1 + 8, curr_y),
                    FONT, 0.45, color, 1, lineType=cv2.LINE_AA)
        curr_y += lh + lb + 4
        
    return annotated_frame


class TrackTracker:
    """Manages centroid history and line-crossing counts for tracked objects."""

    def __init__(self, max_age: int = 30) -> None:
        self.tracks: dict[int, deque[tuple[int, int]]] = {}
        self.track_ages: dict[int, int] = {}
        self.crossed_ids: set[int] = set()
        self.counts: dict[str, dict[str, int]] = {}
        self.max_age: int = max_age

    def update(
        self,
        detections: list[dict[str, Any]],
        line_pos: float,
        line_dir: str,
        width: int,
        height: int
    ) -> None:
        if line_dir == "horizontal":
            line_coord = int(line_pos * height)
        else:
            line_coord = int(line_pos * width)

        active_ids = set()

        for detection in detections:
            track_id = detection.get("track_id")
            if track_id is None:
                continue

            active_ids.add(track_id)
            self.track_ages[track_id] = 0

            bbox = detection["bbox"]
            cx = int((bbox[0] + bbox[2]) / 2)
            cy = int((bbox[1] + bbox[3]) / 2)

            if track_id not in self.tracks:
                self.tracks[track_id] = deque(maxlen=20)

            if len(self.tracks[track_id]) > 0:
                prev_cx, prev_cy = self.tracks[track_id][-1]
                crossed = False
                direction = "in"

                if line_dir == "horizontal":
                    if (prev_cy - line_coord) * (cy - line_coord) < 0:
                        crossed = True
                        direction = "in" if cy > prev_cy else "out"
                else:
                    if (prev_cx - line_coord) * (cx - line_coord) < 0:
                        crossed = True
                        direction = "in" if cx > prev_cx else "out"

                if crossed and track_id not in self.crossed_ids:
                    self.crossed_ids.add(track_id)
                    class_name = detection["class_name"]
                    if class_name not in self.counts:
                        self.counts[class_name] = {"in": 0, "out": 0}
                    self.counts[class_name][direction] += 1

            self.tracks[track_id].append((cx, cy))

        lost_ids = []
        for track_id in list(self.tracks.keys()):
            if track_id not in active_ids:
                self.track_ages[track_id] = self.track_ages.get(track_id, 0) + 1
                if self.track_ages[track_id] > self.max_age:
                    lost_ids.append(track_id)

        for track_id in lost_ids:
            self.tracks.pop(track_id, None)
            self.track_ages.pop(track_id, None)
            self.crossed_ids.discard(track_id)

    def reset_counts(self) -> None:
        self.counts.clear()
        self.crossed_ids.clear()
