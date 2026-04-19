"""
app/services/task_manager.py
-----------------------------
In-process task registry and async queue management.

For production scaling, replace the asyncio.Queue with Celery + Redis.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Dict, Optional

from app.models.schemas import DetectRequest, FrameResult, TaskState, TaskStatus
from app.core.logging import logger


class TaskManager:
    """
    Manages detection task lifecycle:
    - Creates tasks, tracks their state.
    - Routes completed frames to per-task async queues consumed by SSE streams.
    - Supports up to MAX_CONCURRENT_TASKS parallel GPU jobs via a semaphore.
    """

    def __init__(self, max_concurrent: int = 2) -> None:
        self._tasks: Dict[str, TaskState] = {}
        # Per-task queues for streaming (task_id -> asyncio.Queue)
        self._queues: Dict[str, asyncio.Queue] = {}
        self._max_concurrent = max_concurrent
        self._semaphore: Optional[asyncio.Semaphore] = None

    # ── Public API ──────────────────────────────────────────────────────────

    def create_task(self, request: DetectRequest) -> TaskState:
        """Register a new task and return its initial state."""
        task_id = str(uuid.uuid4())
        state = TaskState(
            task_id=task_id,
            video_id=request.video_id,
            prompt=request.prompt,
            status=TaskStatus.PENDING,
        )
        self._tasks[task_id] = state
        self._queues[task_id] = asyncio.Queue()
        logger.info(f"Task created: {task_id} | prompt='{request.prompt}'")
        return state

    def get_task(self, task_id: str) -> Optional[TaskState]:
        return self._tasks.get(task_id)

    def list_tasks(self) -> list[TaskState]:
        return list(self._tasks.values())

    # ── Frame streaming ──────────────────────────────────────────────────────

    async def push_frame(self, task_id: str, frame: FrameResult) -> None:
        """Called by the worker after each frame is processed."""
        if task_id in self._queues:
            await self._queues[task_id].put(("frame", frame))

    async def push_done(self, task_id: str) -> None:
        """Signal that the task is fully complete."""
        if task_id in self._queues:
            await self._queues[task_id].put(("done", None))

    async def push_error(self, task_id: str, error: str) -> None:
        """Signal a processing error."""
        if task_id in self._queues:
            await self._queues[task_id].put(("error", error))

    async def consume_stream(self, task_id: str):
        """
        Async generator that yields (event_type, payload) tuples.
        Used by the SSE endpoint.
        """
        queue = self._queues.get(task_id)
        if queue is None:
            return
        while True:
            event_type, payload = await queue.get()
            yield event_type, payload
            if event_type in ("done", "error"):
                break

    # ── State helpers ────────────────────────────────────────────────────────

    def set_running(self, task_id: str, total_frames: int) -> None:
        state = self._tasks[task_id]
        state.status = TaskStatus.RUNNING
        state.total_frames = total_frames
        logger.info(f"Task {task_id} started | total_frames={total_frames}")

    def add_frame_result(self, task_id: str, frame: FrameResult) -> None:
        state = self._tasks[task_id]
        state.results.append(frame)
        state.processed_frames += 1
        state.progress = state.processed_frames / max(state.total_frames, 1)

    def set_finished(self, task_id: str) -> None:
        state = self._tasks[task_id]
        state.status = TaskStatus.FINISHED
        state.progress = 1.0
        state.zip_ready = True
        logger.info(f"Task {task_id} finished | frames={state.processed_frames}")

    def set_failed(self, task_id: str, error: str) -> None:
        state = self._tasks[task_id]
        state.status = TaskStatus.FAILED
        state.error = error
        logger.error(f"Task {task_id} failed: {error}")

    @property
    def semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._max_concurrent)
        return self._semaphore

    def cleanup_queue(self, task_id: str) -> None:
        """Remove the stream queue after the consumer disconnects."""
        self._queues.pop(task_id, None)


# Global singleton (replaced in tests via dependency injection)
task_manager = TaskManager()
