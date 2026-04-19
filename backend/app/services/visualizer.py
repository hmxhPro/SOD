"""
app/services/visualizer.py
---------------------------
Draw detection bounding boxes and labels onto frames.

Style goals (matching example_pro.png):
  - High-contrast colored border (yellow-gold by default)
  - Semi-transparent filled label background above the box
  - Label text: user's prompt keyword + (optional) confidence score
  - Timestamp overlaid in the bottom-left corner
"""

from __future__ import annotations

import base64
import io
from typing import List, Tuple

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.services.tracker import TrackedObject


# ────────────────────────────────────────────────────────────────────────────
# Color palette (BGR for OpenCV, RGB for PIL)
# We use a rotating palette so different track IDs get distinct colors.
# ────────────────────────────────────────────────────────────────────────────

_PALETTE_BGR = [
    (0, 200, 255),   # amber / yellow-gold
    (0, 100, 255),   # orange
    (0, 255, 128),   # green-yellow
    (255, 80, 0),    # blue
    (180, 0, 255),   # magenta
    (0, 210, 0),     # lime
    (255, 255, 0),   # cyan
    (0, 0, 255),     # red
]


def _get_color(track_id: int) -> Tuple[int, int, int]:
    """Return a BGR color for a given track_id."""
    return _PALETTE_BGR[track_id % len(_PALETTE_BGR)]


def draw_detections(
    frame: np.ndarray,
    tracked_objects: List[TrackedObject],
    timestamp: str,
    show_confidence: bool = True,
    box_thickness: int = 3,
    font_scale: float = 0.7,
) -> np.ndarray:
    """
    Draw bounding boxes, labels, and timestamp onto a BGR frame.

    :param frame:           BGR image from OpenCV.
    :param tracked_objects: List of TrackedObject from tracker.
    :param timestamp:       Formatted timestamp string, e.g. "00:00:05.000".
    :param show_confidence: Whether to append confidence score to label.
    :param box_thickness:   Pixel thickness for the bounding box border.
    :param font_scale:      Scale factor for OpenCV font.
    :returns: Annotated BGR frame (copy, original unmodified).
    """
    annotated = frame.copy()

    for obj in tracked_objects:
        x1, y1, x2, y2 = (
            int(obj.x1), int(obj.y1),
            int(obj.x2), int(obj.y2),
        )
        color = _get_color(obj.track_id)

        # ── Draw bounding box ─────────────────────────────────────────────
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, box_thickness)

        # ── Build label text ──────────────────────────────────────────────
        if show_confidence:
            label_text = f"{obj.label} {obj.score:.2f}"
        else:
            label_text = obj.label

        # ── Measure text ──────────────────────────────────────────────────
        font = cv2.FONT_HERSHEY_DUPLEX
        (text_w, text_h), baseline = cv2.getTextSize(
            label_text, font, font_scale, 1
        )
        padding = 6

        # Label background rectangle above the box
        label_y1 = max(y1 - text_h - 2 * padding, 0)
        label_y2 = y1
        label_x2 = min(x1 + text_w + 2 * padding, annotated.shape[1])

        # Semi-transparent fill
        overlay = annotated.copy()
        cv2.rectangle(overlay, (x1, label_y1), (label_x2, label_y2), color, -1)
        cv2.addWeighted(overlay, 0.7, annotated, 0.3, 0, annotated)

        # White label text
        cv2.putText(
            annotated,
            label_text,
            (x1 + padding, label_y2 - padding // 2),
            font,
            font_scale,
            (255, 255, 255),
            1,
            cv2.LINE_AA,
        )

    # ── Timestamp overlay (bottom-left) ───────────────────────────────────
    ts_text = f"⏱ {timestamp}"
    ts_font_scale = 0.65
    ts_thickness = 1
    (ts_w, ts_h), ts_base = cv2.getTextSize(
        ts_text, cv2.FONT_HERSHEY_SIMPLEX, ts_font_scale, ts_thickness
    )
    h_frame = annotated.shape[0]
    ts_x = 12
    ts_y = h_frame - 12

    # Shadow for readability
    cv2.putText(
        annotated, ts_text,
        (ts_x + 1, ts_y + 1),
        cv2.FONT_HERSHEY_SIMPLEX, ts_font_scale, (0, 0, 0), ts_thickness + 1, cv2.LINE_AA,
    )
    cv2.putText(
        annotated, ts_text,
        (ts_x, ts_y),
        cv2.FONT_HERSHEY_SIMPLEX, ts_font_scale, (255, 255, 255), ts_thickness, cv2.LINE_AA,
    )

    return annotated


def frame_to_base64(frame: np.ndarray, quality: int = 85) -> str:
    """
    Encode a BGR frame as a base64 JPEG string for SSE streaming.

    :param frame:   BGR numpy array.
    :param quality: JPEG compression quality (0–100).
    :returns:       Base64-encoded JPEG string.
    """
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
    success, buffer = cv2.imencode(".jpg", frame, encode_params)
    if not success:
        raise RuntimeError("Failed to encode frame as JPEG.")
    return base64.b64encode(buffer).decode("utf-8")
