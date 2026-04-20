"""
app/services/task_manager.py
-----------------------------
In-process task registry and async queue management.

For production scaling, replace the asyncio.Queue with Celery + Redis.
"""

from __future__ import annotations

import asyncio
import threading
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
    - Exposes cancel / pause / resume controls per task.
    """

    def __init__(self, max_concurrent: int = 2) -> None:
        self._tasks: Dict[str, TaskState] = {}
        # Per-task queues for streaming (task_id -> asyncio.Queue)
        self._queues: Dict[str, asyncio.Queue] = {}
        # Per-task control flags used by the synchronous pipeline loop.
        # cancel: set → loop exits after the current frame
        # pause:  clear → loop pauses; set again → loop resumes
        self._cancel_flags: Dict[str, threading.Event] = {}
        self._pause_flags: Dict[str, threading.Event] = {}
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
        # Initialize control flags — "pause" starts "set" (i.e. not paused).
        self._cancel_flags[task_id] = threading.Event()
        pause = threading.Event()
        pause.set()
        self._pause_flags[task_id] = pause
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

    async def push_packaging(self, task_id: str) -> None:
        """Signal that frame processing finished and ZIP packaging started."""
        if task_id in self._queues:
            await self._queues[task_id].put(("packaging", None))

    async def push_paused(self, task_id: str) -> None:
        if task_id in self._queues:
            await self._queues[task_id].put(("paused", None))

    async def push_resumed(self, task_id: str) -> None:
        if task_id in self._queues:
            await self._queues[task_id].put(("resumed", None))

    async def push_cancelled(self, task_id: str) -> None:
        if task_id in self._queues:
            await self._queues[task_id].put(("cancelled", None))

    async def push_done(self, task_id: str) -> None:
        """Signal that the task is fully complete."""
        if task_id in self._queues:
            await self._queues[task_id].put(("done", None))

    async def push_error(self, task_id: str, error: str) -> None:
        """Signal a processing error."""
        if task_id in self._queues:
            await self._queues[task_id].put(("error", error))

    # ── Control (cancel / pause / resume) ───────────────────────────────────

    def request_cancel(self, task_id: str) -> bool:
        """Signal the pipeline to stop after the current frame."""
        flag = self._cancel_flags.get(task_id)
        if flag is None:
            return False
        flag.set()
        # Ensure a paused worker wakes up so it can see the cancel flag.
        pause = self._pause_flags.get(task_id)
        if pause is not None:
            pause.set()
        logger.info(f"Task {task_id} cancel requested.")
        return True

    def request_pause(self, task_id: str) -> bool:
        """Block the pipeline loop until request_resume is called."""
        flag = self._pause_flags.get(task_id)
        if flag is None:
            return False
        flag.clear()
        logger.info(f"Task {task_id} pause requested.")
        return True

    def request_resume(self, task_id: str) -> bool:
        flag = self._pause_flags.get(task_id)
        if flag is None:
            return False
        flag.set()
        logger.info(f"Task {task_id} resume requested.")
        return True

    def is_cancelled(self, task_id: str) -> bool:
        flag = self._cancel_flags.get(task_id)
        return bool(flag and flag.is_set())

    def wait_if_paused(self, task_id: str, poll_interval: float = 0.1) -> None:
        """
        Block (in the pipeline worker thread) while the task is paused.
        Returns immediately if the task is cancelled.
        """
        pause = self._pause_flags.get(task_id)
        cancel = self._cancel_flags.get(task_id)
        if pause is None:
            return
        # If the event is set, we are NOT paused — fall through.
        while not pause.wait(timeout=poll_interval):
            if cancel is not None and cancel.is_set():
                return

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

    def set_paused(self, task_id: str) -> None:
        state = self._tasks.get(task_id)
        if state is not None and state.status == TaskStatus.RUNNING:
            state.status = TaskStatus.PAUSED
            logger.info(f"Task {task_id} paused | frames={state.processed_frames}")

    def set_resumed(self, task_id: str) -> None:
        state = self._tasks.get(task_id)
        if state is not None and state.status == TaskStatus.PAUSED:
            state.status = TaskStatus.RUNNING
            logger.info(f"Task {task_id} resumed | frames={state.processed_frames}")

    def set_cancelled(self, task_id: str) -> None:
        state = self._tasks.get(task_id)
        if state is None:
            return
        state.status = TaskStatus.CANCELLED
        logger.info(f"Task {task_id} cancelled | frames={state.processed_frames}")

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

    def cleanup_flags(self, task_id: str) -> None:
        """Remove control flags once a task reaches a terminal state."""
        self._cancel_flags.pop(task_id, None)
        self._pause_flags.pop(task_id, None)


# Global singleton (replaced in tests via dependency injection)
task_manager = TaskManager()
