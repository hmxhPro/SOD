"""
app/api/upload.py
-----------------
POST /api/upload  – Accept a video file and return its metadata.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import aiofiles
from fastapi import APIRouter, HTTPException, UploadFile, File, status

from app.core.config import settings
from app.core.logging import logger
from app.models.schemas import UploadResponse
from app.utils.video_utils import get_video_info

router = APIRouter()

ALLOWED_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".webm", ".flv"}


@router.post(
    "/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a video file for detection",
)
async def upload_video(
    file: UploadFile = File(..., description="Video file (mp4, avi, mov, etc.)")
) -> UploadResponse:
    """
    Accept a video upload and persist it to the upload directory.

    Returns a `video_id` that must be passed to POST /api/detect.
    """
    # ── Validate file extension ────────────────────────────────────────────
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{suffix}'. "
                   f"Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    video_id = str(uuid.uuid4())
    dest_path = settings.UPLOAD_DIR / f"{video_id}{suffix}"

    # ── Stream to disk (no size limit) ────────────────────────────────────
    total_bytes = 0
    try:
        async with aiofiles.open(dest_path, "wb") as out_file:
            while chunk := await file.read(4 * 1024 * 1024):  # 4 MB chunks
                total_bytes += len(chunk)
                await out_file.write(chunk)
    except HTTPException:
        dest_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        dest_path.unlink(missing_ok=True)
        logger.error(f"Upload failed for {file.filename}: {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save uploaded file.",
        ) from exc

    # ── Read video metadata ───────────────────────────────────────────────
    try:
        info = get_video_info(dest_path)
    except Exception as exc:
        dest_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"File saved but could not be read as a valid video: {exc}",
        ) from exc

    logger.info(
        f"Video uploaded: {video_id} | {file.filename} | "
        f"{total_bytes / 1e6:.1f} MB | {info['total_frames']} frames"
    )

    return UploadResponse(
        video_id=video_id,
        filename=file.filename or "",
        size_bytes=total_bytes,
        duration_seconds=info["duration_seconds"],
        fps=info["fps"],
        total_frames=info["total_frames"],
    )
