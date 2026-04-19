"""
app/models/schemas.py
----------------------
Pydantic data models for API request / response payloads.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


# ────────────────────────────────────────────────────────────────────────────
# Task Status
# ────────────────────────────────────────────────────────────────────────────

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"


# ────────────────────────────────────────────────────────────────────────────
# Upload
# ────────────────────────────────────────────────────────────────────────────

class UploadResponse(BaseModel):
    """Returned after a successful video upload."""
    video_id: str = Field(..., description="Unique ID for the uploaded video")
    filename: str
    size_bytes: int
    duration_seconds: Optional[float] = None
    fps: Optional[float] = None
    total_frames: Optional[int] = None


# ────────────────────────────────────────────────────────────────────────────
# Detection Task
# ────────────────────────────────────────────────────────────────────────────

class DetectRequest(BaseModel):
    """Request body to start a detection task."""
    video_id: str = Field(..., description="ID returned from /api/upload")
    prompt: str = Field(
        ...,
        description=(
            "Natural language description of the object to detect. "
            "E.g. '帮我检测视频中的菜园'"
        ),
    )
    detection_interval: Optional[int] = Field(
        default=None,
        ge=1,
        description="Run full detection every N frames; track in between. "
                    "Defaults to server-side setting.",
    )
    box_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    text_threshold: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class DetectResponse(BaseModel):
    """Returned when a detection task is successfully queued."""
    task_id: str
    video_id: str
    prompt: str
    status: TaskStatus


# ────────────────────────────────────────────────────────────────────────────
# Per-Frame Result
# ────────────────────────────────────────────────────────────────────────────

class BoundingBox(BaseModel):
    """XYXY bounding box coordinates (absolute pixels)."""
    x1: float
    y1: float
    x2: float
    y2: float


class Detection(BaseModel):
    """Single object detection on a frame."""
    track_id: Optional[int] = None        # ByteTrack assigned ID
    label: str                             # User's prompt label
    score: float = Field(..., ge=0.0, le=1.0)
    bbox: BoundingBox


class FrameResult(BaseModel):
    """All detection results for a single video frame."""
    frame_id: int                          # 0-based frame index
    timestamp: str                         # HH:MM:SS.mmm
    timestamp_seconds: float
    detections: List[Detection]
    image_filename: str                    # Saved result image filename
    # Base64-encoded JPEG for streaming (set when streaming, empty when saved)
    image_b64: str = ""


# ────────────────────────────────────────────────────────────────────────────
# Task State
# ────────────────────────────────────────────────────────────────────────────

class TaskState(BaseModel):
    """Full task state returned by GET /api/task/{task_id}."""
    task_id: str
    video_id: str
    prompt: str
    status: TaskStatus
    progress: float = Field(default=0.0, ge=0.0, le=1.0, description="0.0 – 1.0")
    total_frames: int = 0
    processed_frames: int = 0
    results: List[FrameResult] = []
    error: Optional[str] = None
    zip_ready: bool = False


# ────────────────────────────────────────────────────────────────────────────
# SSE / WebSocket streaming message
# ────────────────────────────────────────────────────────────────────────────

class StreamEvent(BaseModel):
    """
    Streamed to the client after each frame is processed.
    event_type: "frame" | "progress" | "done" | "error"
    """
    event_type: str
    task_id: str
    frame_result: Optional[FrameResult] = None
    progress: float = 0.0
    total_frames: int = 0
    processed_frames: int = 0
    error: Optional[str] = None
