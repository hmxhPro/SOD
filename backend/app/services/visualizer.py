"""
app/services/visualizer.py
---------------------------
Draw detection bounding boxes and labels onto frames.

Labels are rendered via PIL so that Chinese / CJK characters show up
correctly (OpenCV's putText only supports ASCII).

Style goals (matching example_pro.png):
  - High-contrast colored border
  - Semi-transparent filled label background above the box
  - Label text: user's prompt keyword + (optional) confidence score
  - Timestamp overlaid in the bottom-left corner
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import List, Tuple, Optional

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from app.core.logging import logger
from app.services.tracker import TrackedObject


# ────────────────────────────────────────────────────────────────────────────
# Color palette
# ────────────────────────────────────────────────────────────────────────────

# BGR for OpenCV (box drawing)
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


def _get_color_bgr(track_id: int) -> Tuple[int, int, int]:
    return _PALETTE_BGR[track_id % len(_PALETTE_BGR)]


def _bgr_to_rgb(bgr: Tuple[int, int, int]) -> Tuple[int, int, int]:
    return (bgr[2], bgr[1], bgr[0])


# ────────────────────────────────────────────────────────────────────────────
# Font loading (CJK-capable)
# ────────────────────────────────────────────────────────────────────────────

_CJK_FONT_CANDIDATES = [
    # Linux (Ubuntu / Debian typical)
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
    # macOS
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    # Windows
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
]


def _find_cjk_font_path() -> Optional[Path]:
    for p in _CJK_FONT_CANDIDATES:
        if Path(p).exists():
            return Path(p)
    return None


_FONT_PATH: Optional[Path] = _find_cjk_font_path()
_FONT_CACHE: dict[int, ImageFont.FreeTypeFont] = {}


def _get_font(size: int) -> ImageFont.ImageFont:
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]
    if _FONT_PATH is not None:
        try:
            font = ImageFont.truetype(str(_FONT_PATH), size=size)
            _FONT_CACHE[size] = font
            return font
        except Exception as exc:
            logger.warning(f"Failed to load CJK font {_FONT_PATH}: {exc}")
    # Fallback (no CJK support but non-fatal)
    fallback = ImageFont.load_default()
    _FONT_CACHE[size] = fallback
    return fallback


if _FONT_PATH is None:
    logger.warning(
        "No CJK font found on this system — detection labels with Chinese "
        "characters may render as ???. Install e.g. fonts-noto-cjk."
    )
else:
    logger.info(f"Using CJK font for detection labels: {_FONT_PATH}")


# ────────────────────────────────────────────────────────────────────────────
# Public API
# ────────────────────────────────────────────────────────────────────────────

def draw_detections(
    frame: np.ndarray,
    tracked_objects: List[TrackedObject],
    timestamp: str,
    show_confidence: bool = True,
    box_thickness: int = 3,
    label_font_size: int = 22,
    timestamp_font_size: int = 20,
) -> np.ndarray:
    """
    Draw bounding boxes, labels, and timestamp onto a BGR frame.

    :param frame:               BGR image from OpenCV.
    :param tracked_objects:     TrackedObject list.
    :param timestamp:           Formatted timestamp string.
    :param show_confidence:     Append confidence score to label.
    :param box_thickness:       Pixel thickness of the bounding box.
    :param label_font_size:     PIL font size for detection labels.
    :param timestamp_font_size: PIL font size for the timestamp overlay.
    :returns: Annotated BGR frame (copy, original unmodified).
    """
    # ── Step 1: draw boxes + translucent label backgrounds with cv2 ──────
    annotated = frame.copy()
    h_frame, w_frame = annotated.shape[:2]

    label_font = _get_font(label_font_size)

    # We need one PIL pass for text drawing at the end. Collect text jobs
    # first so we only convert BGR⇄RGB once.
    text_jobs: list[tuple[str, tuple[int, int], tuple[int, int, int]]] = []

    for obj in tracked_objects:
        x1, y1, x2, y2 = (
            int(obj.x1), int(obj.y1),
            int(obj.x2), int(obj.y2),
        )
        color_bgr = _get_color_bgr(obj.track_id)

        # Bounding box
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color_bgr, box_thickness)

        # Label text
        if show_confidence:
            label_text = f"{obj.label} {obj.score:.2f}"
        else:
            label_text = obj.label

        # Measure via PIL (CJK-safe)
        bbox = label_font.getbbox(label_text) if hasattr(label_font, "getbbox") else (0, 0, *label_font.getsize(label_text))
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        padding = 6

        label_y1 = max(y1 - text_h - 2 * padding, 0)
        label_y2 = y1 if label_y1 > 0 else y1 + text_h + 2 * padding
        label_x2 = min(x1 + text_w + 2 * padding, w_frame)

        # Semi-transparent filled rect for label background
        overlay = annotated.copy()
        cv2.rectangle(
            overlay,
            (x1, label_y1),
            (label_x2, label_y2),
            color_bgr,
            thickness=-1,
        )
        cv2.addWeighted(overlay, 0.7, annotated, 0.3, 0, annotated)

        # Defer text draw; PIL pass does it in RGB space
        text_jobs.append(
            (label_text, (x1 + padding, label_y1 + padding - 2), (255, 255, 255))
        )

    # Timestamp job (white text, black shadow)
    ts_text = f"⏱ {timestamp}"
    ts_font = _get_font(timestamp_font_size)
    ts_bbox = ts_font.getbbox(ts_text) if hasattr(ts_font, "getbbox") else (0, 0, *ts_font.getsize(ts_text))
    ts_h = ts_bbox[3] - ts_bbox[1]
    ts_x = 12
    ts_y = h_frame - ts_h - 16

    # ── Step 2: do all text drawing via PIL in one pass ──────────────────
    rgb = cv2.cvtColor(annotated, cv2.COLOR_BGR2RGB)
    pil_img = Image.fromarray(rgb)
    draw = ImageDraw.Draw(pil_img)

    # Label text
    for text, xy, color_rgb in text_jobs:
        draw.text(xy, text, font=label_font, fill=color_rgb)

    # Timestamp with a 1-px shadow
    draw.text((ts_x + 1, ts_y + 1), ts_text, font=ts_font, fill=(0, 0, 0))
    draw.text((ts_x, ts_y), ts_text, font=ts_font, fill=(255, 255, 255))

    annotated = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
    return annotated


def frame_to_base64(frame: np.ndarray, quality: int = 85) -> str:
    """Encode a BGR frame as a base64 JPEG string for SSE streaming."""
    encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
    success, buffer = cv2.imencode(".jpg", frame, encode_params)
    if not success:
        raise RuntimeError("Failed to encode frame as JPEG.")
    return base64.b64encode(buffer).decode("utf-8")
