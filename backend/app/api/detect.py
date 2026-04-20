"""
app/api/detect.py
-----------------
POST /api/detect  – Start a detection task (async).
GET  /api/task/{task_id}  – Query task status and results.
GET  /api/stream/{task_id}  – SSE stream of frame results.
GET  /api/download/{task_id}  – Download results ZIP.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse, StreamingResponse

from app.core.config import settings
from app.core.logging import logger
from app.models.schemas import (
    DetectRequest,
    DetectResponse,
    StreamEvent,
    TaskState,
    TaskStatus,
)
from app.services.pipeline import run_detection_pipeline
from app.services.task_manager import task_manager

router = APIRouter()

# Keep strong references to background tasks so they aren't GC'd mid-run
_background_tasks: set = set()


# ────────────────────────────────────────────────────────────────────────────
# POST /api/detect
# ────────────────────────────────────────────────────────────────────────────

@router.post(
    "/detect",
    response_model=DetectResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Start a video detection task",
)
async def start_detection(body: DetectRequest) -> DetectResponse:
    """
    Queue a detection task for the specified video_id and prompt.

    Processing runs asynchronously in the background.
    Use `GET /api/stream/{task_id}` for real-time results via SSE,
    or poll `GET /api/task/{task_id}` for status.
    """
    # ── Validate video_id  ─────────────────────────────────────────────────
    video_files = list(settings.UPLOAD_DIR.glob(f"{body.video_id}.*"))
    if not video_files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video '{body.video_id}' not found. "
                   f"Please upload first via POST /api/upload.",
        )
    video_path = video_files[0]

    # ── Validate prompt ────────────────────────────────────────────────────
    prompt = body.prompt.strip()
    if not prompt:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Prompt must not be empty.",
        )

    # ── Create task ────────────────────────────────────────────────────────
    task_state = task_manager.create_task(body)

    # ── Launch background coroutine ────────────────────────────────────────
    task = asyncio.create_task(
        run_detection_pipeline(
            task_id=task_state.task_id,
            video_path=video_path,
            prompt=prompt,
            task_manager=task_manager,
            detection_interval=body.detection_interval,
            box_threshold=body.box_threshold,
            text_threshold=body.text_threshold,
        )
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    logger.info(
        f"Detection task queued: {task_state.task_id} | "
        f"video={body.video_id} | prompt='{prompt}'"
    )

    return DetectResponse(
        task_id=task_state.task_id,
        video_id=body.video_id,
        prompt=prompt,
        status=TaskStatus.PENDING,
    )


# ────────────────────────────────────────────────────────────────────────────
# GET /api/task/{task_id}
# ────────────────────────────────────────────────────────────────────────────

@router.get(
    "/task/{task_id}",
    response_model=TaskState,
    summary="Get task status and accumulated results",
)
async def get_task(task_id: str) -> TaskState:
    """
    Return the current state of a detection task.

    - `status`: pending | running | finished | failed
    - `progress`: 0.0 – 1.0
    - `results`: list of frame results accumulated so far
    - `zip_ready`: true when the download ZIP is available
    """
    state = task_manager.get_task(task_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found.",
        )
    return state


# ────────────────────────────────────────────────────────────────────────────
# GET /api/stream/{task_id}  – Server-Sent Events
# ────────────────────────────────────────────────────────────────────────────

@router.get(
    "/stream/{task_id}",
    summary="Stream detection results frame by frame via SSE",
    response_class=StreamingResponse,
)
async def stream_task(task_id: str):
    """
    Server-Sent Events (SSE) endpoint.

    Events:
      - `frame`   – one frame processed; includes base64-encoded result image
      - `done`    – processing complete
      - `error`   – processing failed

    Each SSE message has the format:
        data: <JSON StreamEvent>\\n\\n
    """
    state = task_manager.get_task(task_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found.",
        )

    async def event_generator():
        # Heartbeat keeps SSE connections alive through any silent period
        # (ZIP packaging for long videos can take minutes). 15 s is well
        # below typical browser / proxy idle timeouts.
        HEARTBEAT_SECONDS = 15.0
        queue = task_manager._queues.get(task_id)
        try:
            while True:
                if queue is None:
                    # Queue was already cleaned up — fall through and stop.
                    break
                try:
                    event_type, payload = await asyncio.wait_for(
                        queue.get(), timeout=HEARTBEAT_SECONDS
                    )
                except asyncio.TimeoutError:
                    # SSE comment line — ignored by EventSource but keeps
                    # the TCP connection from being closed by proxies.
                    yield ": keepalive\n\n"
                    continue

                if event_type == "frame":
                    evt = StreamEvent(
                        event_type="frame",
                        task_id=task_id,
                        frame_result=payload,
                        progress=state.progress,
                        total_frames=state.total_frames,
                        processed_frames=state.processed_frames,
                    )
                elif event_type == "packaging":
                    evt = StreamEvent(
                        event_type="packaging",
                        task_id=task_id,
                        progress=1.0,
                        total_frames=state.total_frames,
                        processed_frames=state.processed_frames,
                    )
                elif event_type in ("paused", "resumed", "cancelled"):
                    evt = StreamEvent(
                        event_type=event_type,
                        task_id=task_id,
                        progress=state.progress,
                        total_frames=state.total_frames,
                        processed_frames=state.processed_frames,
                    )
                elif event_type == "done":
                    evt = StreamEvent(
                        event_type="done",
                        task_id=task_id,
                        progress=1.0,
                        total_frames=state.total_frames,
                        processed_frames=state.processed_frames,
                    )
                elif event_type == "error":
                    evt = StreamEvent(
                        event_type="error",
                        task_id=task_id,
                        error=str(payload),
                    )
                else:
                    continue

                yield f"data: {evt.model_dump_json()}\n\n"

                if event_type in ("done", "error"):
                    break
        finally:
            task_manager.cleanup_queue(task_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",     # Disable nginx buffering
            "Connection": "keep-alive",
        },
    )


# ────────────────────────────────────────────────────────────────────────────
# GET /api/download/{task_id}
# ────────────────────────────────────────────────────────────────────────────

@router.get(
    "/frame/{task_id}/{filename}",
    summary="Serve a single annotated frame image",
    response_class=FileResponse,
)
async def get_frame(task_id: str, filename: str):
    """Return a single annotated frame JPEG by filename."""
    # Prevent path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid filename.")
    img_path = settings.RESULTS_DIR / task_id / filename
    if not img_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Frame not found.")
    return FileResponse(path=str(img_path), media_type="image/jpeg")


@router.get(
    "/download/{task_id}",
    summary="Download the detection results ZIP archive",
    response_class=FileResponse,
)
async def download_results(task_id: str):
    """
    Download a ZIP file containing all annotated frames,
    results.json, and results.csv for the specified task.

    Only available once the task status is `finished`.
    """
    state = task_manager.get_task(task_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found.",
        )

    if state.status != TaskStatus.FINISHED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task is not finished yet (status={state.status}). "
                   "Wait for 'finished' before downloading.",
        )

    zip_path = settings.RESULTS_DIR / task_id / "results.zip"
    if not zip_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ZIP file not found. The task may have failed during packaging.",
        )

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=f"detection_results_{task_id[:8]}.zip",
    )


# ────────────────────────────────────────────────────────────────────────────
# POST /api/task/{task_id}/cancel | pause | resume
# ────────────────────────────────────────────────────────────────────────────

_ACTIVE_STATUSES = {
    TaskStatus.PENDING,
    TaskStatus.RUNNING,
    TaskStatus.PAUSED,
}


def _require_active_task(task_id: str) -> TaskState:
    state = task_manager.get_task(task_id)
    if state is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found.",
        )
    if state.status not in _ACTIVE_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Task is not active (status={state.status}).",
        )
    return state


@router.post(
    "/task/{task_id}/cancel",
    summary="Request cancellation of a running detection task",
)
async def cancel_task(task_id: str) -> dict:
    _require_active_task(task_id)
    ok = task_manager.request_cancel(task_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cancel control unavailable for this task.",
        )
    return {"task_id": task_id, "action": "cancel", "status": "accepted"}


@router.post(
    "/task/{task_id}/pause",
    summary="Pause a running detection task",
)
async def pause_task(task_id: str) -> dict:
    state = _require_active_task(task_id)
    if state.status == TaskStatus.PAUSED:
        return {"task_id": task_id, "action": "pause", "status": "already_paused"}
    if state.status != TaskStatus.RUNNING:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only running tasks can be paused.",
        )
    ok = task_manager.request_pause(task_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Pause control unavailable for this task.",
        )
    task_manager.set_paused(task_id)
    await task_manager.push_paused(task_id)
    return {"task_id": task_id, "action": "pause", "status": "accepted"}


@router.post(
    "/task/{task_id}/resume",
    summary="Resume a paused detection task",
)
async def resume_task(task_id: str) -> dict:
    state = _require_active_task(task_id)
    if state.status == TaskStatus.RUNNING:
        return {"task_id": task_id, "action": "resume", "status": "already_running"}
    if state.status != TaskStatus.PAUSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only paused tasks can be resumed.",
        )
    ok = task_manager.request_resume(task_id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Resume control unavailable for this task.",
        )
    task_manager.set_resumed(task_id)
    await task_manager.push_resumed(task_id)
    return {"task_id": task_id, "action": "resume", "status": "accepted"}
