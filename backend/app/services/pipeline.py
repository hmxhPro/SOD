"""
app/services/pipeline.py
-------------------------
The main video processing pipeline.

Pipeline flow per task:
  1. Open video with OpenCV
  2. For every frame:
       a) If it's a "detection frame"  →  run detector + tracker.update()
       b) Otherwise (tracking-only frame) →  tracker.update(last_detections)
  3. Draw visualized result on the frame
  4. Save annotated frame as JPEG
  5. Push FrameResult (with base64 thumbnail) to the task queue → SSE
  6. After all frames: package results into a ZIP

Detection vs Tracking:
  - Detection runs every DETECTION_INTERVAL frames (configurable).
  - Between detection frames, we pass the LAST set of detections to ByteTrack,
    which propagates them with a Kalman filter — MUCH cheaper than GPU inference.
  - This gives ~5x throughput improvement at default interval=5.
"""

from __future__ import annotations

import asyncio
import json
import os
import zipfile
from pathlib import Path
from typing import List, Optional

import cv2
import numpy as np

from app.core.config import settings
from app.core.logging import logger
from app.models.schemas import BoundingBox, Detection, FrameResult, TaskState
from app.services.detector import RawDetection, get_detector
from app.services.task_manager import TaskManager
from app.services.tracker import TrackedObject, create_tracker
from app.services.visualizer import draw_detections, frame_to_base64
from app.utils.video_utils import format_timestamp, get_video_info


# ────────────────────────────────────────────────────────────────────────────
# Main pipeline coroutine
# ────────────────────────────────────────────────────────────────────────────

async def run_detection_pipeline(
    task_id: str,
    video_path: Path,
    prompt: str,
    task_manager: TaskManager,
    detection_interval: Optional[int] = None,
    box_threshold: Optional[float] = None,
    text_threshold: Optional[float] = None,
) -> None:
    """
    Async coroutine that processes a video file and streams results.

    Designed to be run inside a background asyncio task via
    `asyncio.create_task(...)`.

    Heavy work (GPU inference) is offloaded to a thread pool via
    `asyncio.to_thread(...)` so it does NOT block the event loop.
    """
    # ── Config ────────────────────────────────────────────────────────────
    det_interval = detection_interval or settings.DETECTION_INTERVAL
    box_thr = box_threshold or settings.BOX_THRESHOLD
    txt_thr = text_threshold or settings.TEXT_THRESHOLD

    # ── Output directory for this task ────────────────────────────────────
    task_results_dir = settings.RESULTS_DIR / task_id
    task_results_dir.mkdir(parents=True, exist_ok=True)

    # ── Video info ────────────────────────────────────────────────────────
    try:
        info = get_video_info(video_path)
    except Exception as exc:
        logger.error(f"[{task_id}] Failed to read video: {exc}")
        task_manager.set_failed(task_id, str(exc))
        await task_manager.push_error(task_id, str(exc))
        return

    task_manager.set_running(task_id, info["total_frames"])
    logger.info(
        f"[{task_id}] Processing video: {video_path.name} | "
        f"frames={info['total_frames']} fps={info['fps']:.2f}"
    )

    # ── Acquire GPU semaphore (limits concurrent GPU tasks) ───────────────
    loop = asyncio.get_running_loop()
    async with task_manager.semaphore:
        try:
            await asyncio.to_thread(
                _sync_pipeline,
                task_id=task_id,
                video_path=video_path,
                prompt=prompt,
                task_results_dir=task_results_dir,
                task_manager=task_manager,
                loop=loop,
                fps=info["fps"],
                total_frames=info["total_frames"],
                det_interval=det_interval,
                box_thr=box_thr,
                txt_thr=txt_thr,
            )
        except Exception as exc:
            logger.exception(f"[{task_id}] Pipeline error: {exc}")
            task_manager.set_failed(task_id, str(exc))
            await task_manager.push_error(task_id, str(exc))
            task_manager.cleanup_flags(task_id)
            return

    # ── Cancel path: skip ZIP, emit cancelled, close stream ──────────────
    if task_manager.is_cancelled(task_id):
        task_manager.set_cancelled(task_id)
        await task_manager.push_cancelled(task_id)
        await task_manager.push_done(task_id)
        task_manager.cleanup_flags(task_id)
        logger.info(f"[{task_id}] Pipeline cancelled.")
        return

    # ── Package ZIP ───────────────────────────────────────────────────────
    # Notify clients first — ZIP packaging can take minutes for long videos
    # and we don't want the SSE stream to look dead.
    await task_manager.push_packaging(task_id)
    try:
        await asyncio.to_thread(
            _package_zip,
            task_id=task_id,
            task_results_dir=task_results_dir,
            task_state=task_manager.get_task(task_id),
        )
        task_manager.set_finished(task_id)
    except Exception as exc:
        logger.error(f"[{task_id}] ZIP creation failed: {exc}")
        task_manager.set_failed(task_id, f"ZIP error: {exc}")

    await task_manager.push_done(task_id)
    task_manager.cleanup_flags(task_id)
    logger.info(f"[{task_id}] Pipeline complete.")


# ────────────────────────────────────────────────────────────────────────────
# Synchronous heavy-lifting (runs in thread pool)
# ────────────────────────────────────────────────────────────────────────────

def _sync_pipeline(
    task_id: str,
    video_path: Path,
    prompt: str,
    task_results_dir: Path,
    task_manager: TaskManager,
    loop: asyncio.AbstractEventLoop,
    fps: float,
    total_frames: int,
    det_interval: int,
    box_thr: float,
    txt_thr: float,
) -> None:
    """
    Synchronous video processing loop.

    Runs in a thread pool executor to avoid blocking asyncio event loop.
    Pushes frame results into task_manager via asyncio.run_coroutine_threadsafe.
    """
    detector = get_detector()
    tracker = create_tracker(fps=fps)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video file: {video_path}")

    frame_idx = 0
    last_raw_detections: List[RawDetection] = []
    all_frame_results: List[FrameResult] = []

    try:
        while True:
            # ── Pause / cancel control ─────────────────────────────────
            # Block here while the task is paused; returns immediately
            # if a cancel has been requested.
            task_manager.wait_if_paused(task_id)
            if task_manager.is_cancelled(task_id):
                logger.info(f"[{task_id}] Cancelled at frame {frame_idx}.")
                break

            ret, frame = cap.read()
            if not ret:
                break

            # ── Timestamp ─────────────────────────────────────────────────
            ts_seconds = frame_idx / fps
            ts_str = format_timestamp(ts_seconds)

            # ── Detection or tracking-only ────────────────────────────────
            is_detection_frame = (frame_idx % det_interval == 0)

            if is_detection_frame:
                # Full GPU detection
                raw_detections = detector.predict(
                    image=frame,
                    prompt=prompt,
                    box_threshold=box_thr,
                    text_threshold=txt_thr,
                )
                last_raw_detections = raw_detections
            else:
                # Reuse last detections (tracker handles propagation)
                raw_detections = last_raw_detections

            # ── ByteTrack update ──────────────────────────────────────────
            h, w = frame.shape[:2]
            tracked_objects = tracker.update(raw_detections, image_shape=(h, w))

            # ── Build Detection schema objects ────────────────────────────
            schema_detections = [
                Detection(
                    track_id=obj.track_id,
                    label=obj.label,
                    score=round(obj.score, 4),
                    bbox=BoundingBox(
                        x1=obj.x1, y1=obj.y1,
                        x2=obj.x2, y2=obj.y2,
                    ),
                )
                for obj in tracked_objects
            ]

            # ── Draw visualization ────────────────────────────────────────
            annotated = draw_detections(
                frame=frame,
                tracked_objects=tracked_objects,
                timestamp=ts_str,
                show_confidence=True,
            )

            # ── Save annotated frame ──────────────────────────────────────
            img_filename = _make_frame_filename(frame_idx, ts_str)
            img_path = task_results_dir / img_filename
            cv2.imwrite(str(img_path), annotated, [cv2.IMWRITE_JPEG_QUALITY, 90])

            # ── Encode thumbnail for streaming (lower quality = faster) ───
            img_b64 = frame_to_base64(annotated, quality=70)

            # ── Build FrameResult ─────────────────────────────────────────
            frame_result = FrameResult(
                frame_id=frame_idx,
                timestamp=ts_str,
                timestamp_seconds=round(ts_seconds, 3),
                detections=schema_detections,
                image_filename=img_filename,
                image_b64=img_b64,
            )

            # ── Push to task queue (thread-safe) ──────────────────────────
            task_manager.add_frame_result(task_id, frame_result)
            asyncio.run_coroutine_threadsafe(
                task_manager.push_frame(task_id, frame_result),
                loop,
            )

            frame_idx += 1

    finally:
        cap.release()

    logger.info(f"[{task_id}] Processed {frame_idx} frames.")


# ────────────────────────────────────────────────────────────────────────────
# ZIP packaging
# ────────────────────────────────────────────────────────────────────────────

def _package_zip(
    task_id: str,
    task_results_dir: Path,
    task_state,
) -> None:
    """
    Create a ZIP archive containing:
      - All annotated frame JPEGs
      - results.json  (full detection metadata)
      - results.csv   (CSV summary)
    """
    zip_path = task_results_dir / "results.zip"

    # ── Build JSON / CSV data ─────────────────────────────────────────────
    records = []
    for fr in task_state.results:
        for det in fr.detections:
            records.append(
                {
                    "frame_id": fr.frame_id,
                    "timestamp": fr.timestamp,
                    "timestamp_seconds": fr.timestamp_seconds,
                    "track_id": det.track_id,
                    "detected_label": det.label,
                    "score": det.score,
                    "bbox_x1": det.bbox.x1,
                    "bbox_y1": det.bbox.y1,
                    "bbox_x2": det.bbox.x2,
                    "bbox_y2": det.bbox.y2,
                }
            )

    # Write JSON
    json_path = task_results_dir / "results.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    # Write CSV
    csv_path = task_results_dir / "results.csv"
    with open(csv_path, "w", encoding="utf-8") as f:
        if records:
            header = ",".join(records[0].keys())
            f.write(header + "\n")
            for row in records:
                f.write(",".join(str(v) for v in row.values()) + "\n")

    # ── Pack ZIP ──────────────────────────────────────────────────────────
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Images
        for img_file in sorted(task_results_dir.glob("frame_*.jpg")):
            zf.write(img_file, img_file.name)
        # Metadata
        zf.write(json_path, "results.json")
        zf.write(csv_path, "results.csv")

    logger.info(f"[{task_id}] ZIP created: {zip_path}")


# ────────────────────────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────────────────────────

def _make_frame_filename(frame_id: int, timestamp: str) -> str:
    """
    Build a filename like: frame_000125_00-00-05-000.jpg
    """
    ts_safe = timestamp.replace(":", "-").replace(".", "-")
    return f"frame_{frame_id:06d}_{ts_safe}.jpg"
