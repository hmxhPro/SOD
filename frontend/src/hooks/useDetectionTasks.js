/**
 * src/hooks/useDetectionTasks.js
 * -------------------------------
 * Manage MULTIPLE concurrent detection workflows in one state tree.
 *
 * Each "task" represents one video and goes through phases:
 *   queued → uploading → pending → running → finished | failed
 *
 * The hook exposes:
 *   - tasks: TaskItem[]
 *   - addFiles(files): push new queued tasks
 *   - removeTask(id)
 *   - clearAll()
 *   - startAll(prompt, detectionInterval): fire upload+detect+stream for every queued task
 *   - startOne(id, prompt, detectionInterval)
 */

import { useState, useRef, useCallback } from 'react'
import {
  uploadVideo, startDetection, getStreamUrl, getTask,
  cancelDetection, pauseDetection, resumeDetection,
} from '../services/api'

let _nextId = 1
const makeId = () => `t_${Date.now()}_${_nextId++}`

function newTask(file) {
  return {
    id: makeId(),
    file,
    fileName: file.name,
    fileSize: file.size,

    videoId: null,
    taskId: null,
    taskStatus: 'queued',   // queued | uploading | pending | running | paused | packaging | finished | failed | cancelled

    uploadProgress: 0,
    progress: 0,
    processedFrames: 0,
    totalFrames: 0,

    videoInfo: null,
    latestFrame: null,
    allFrames: [],
    detectedFrameCount: 0,

    error: null,
    zipReady: false,
  }
}

export function useDetectionTasks() {
  const [tasks, setTasks] = useState([])
  const streamsRef = useRef(new Map()) // id -> EventSource

  const patchTask = useCallback((id, patch) => {
    setTasks((prev) =>
      prev.map((t) =>
        t.id === id
          ? (typeof patch === 'function' ? { ...t, ...patch(t) } : { ...t, ...patch })
          : t
      )
    )
  }, [])

  const closeStream = useCallback((id) => {
    const es = streamsRef.current.get(id)
    if (es) {
      es.close()
      streamsRef.current.delete(id)
    }
  }, [])

  // ── Public: add newly selected files as queued tasks ────────────────────
  const addFiles = useCallback((files) => {
    const list = Array.from(files || []).filter(Boolean)
    if (!list.length) return
    setTasks((prev) => [...prev, ...list.map(newTask)])
  }, [])

  const removeTask = useCallback((id) => {
    closeStream(id)
    setTasks((prev) => prev.filter((t) => t.id !== id))
  }, [closeStream])

  const clearAll = useCallback(() => {
    tasks.forEach((t) => closeStream(t.id))
    setTasks([])
  }, [tasks, closeStream])

  const resetOne = useCallback((id) => {
    closeStream(id)
    setTasks((prev) =>
      prev.map((t) =>
        t.id === id
          ? { ...t, ...newTask(t.file), id: t.id } // keep same id
          : t
      )
    )
  }, [closeStream])

  // ── SSE event handler ──────────────────────────────────────────────────
  const handleStreamEvent = useCallback((id, data) => {
    switch (data.event_type) {
      case 'frame':
        setTasks((prev) =>
          prev.map((t) => {
            if (t.id !== id) return t
            const fr = data.frame_result
            const { image_b64: _drop, ...meta } = fr ?? {}
            const hasDetection = (fr?.detections?.length ?? 0) > 0
            // If we're paused, a late frame should still update the preview
            // and counters but must NOT kick us back to "running".
            const nextStatus = t.taskStatus === 'paused' ? 'paused' : 'running'
            return {
              ...t,
              taskStatus: nextStatus,
              progress: data.progress ?? t.progress,
              processedFrames: data.processed_frames ?? t.processedFrames,
              totalFrames: data.total_frames ?? t.totalFrames,
              latestFrame: fr ?? t.latestFrame,
              allFrames: hasDetection
                ? [...t.allFrames, { ...meta, taskId: t.taskId }]
                : t.allFrames,
              detectedFrameCount: hasDetection
                ? (t.detectedFrameCount || 0) + 1
                : (t.detectedFrameCount || 0),
            }
          })
        )
        break
      case 'paused':
        patchTask(id, { taskStatus: 'paused' })
        break
      case 'resumed':
        patchTask(id, { taskStatus: 'running' })
        break
      case 'cancelled':
        patchTask(id, (t) => ({
          taskStatus: 'cancelled',
          processedFrames: data.processed_frames ?? t.processedFrames,
          totalFrames: data.total_frames ?? t.totalFrames,
        }))
        break
      case 'packaging':
        patchTask(id, (t) => ({
          taskStatus: 'packaging',
          progress: 1.0,
          processedFrames: data.processed_frames ?? t.processedFrames,
          totalFrames: data.total_frames ?? t.totalFrames,
        }))
        break
      case 'done':
        closeStream(id)
        patchTask(id, (t) => {
          // If we already transitioned to 'cancelled', don't override.
          if (t.taskStatus === 'cancelled') return {}
          return {
            taskStatus: 'finished',
            progress: 1.0,
            processedFrames: data.processed_frames ?? t.processedFrames,
            zipReady: true,
          }
        })
        break
      case 'error':
        closeStream(id)
        patchTask(id, {
          taskStatus: 'failed',
          error: data.error || 'Unknown server error.',
        })
        break
      default:
        break
    }
  }, [closeStream, patchTask])

  // ── Reconcile with server when SSE drops mid-task ──────────────────────
  // Polls /api/task/{taskId} until the server reports a terminal state,
  // so a mid-stream disconnect (e.g. during slow ZIP packaging) does NOT
  // get misreported as "failed" on the client.
  const reconcileWithServer = useCallback(async (id) => {
    const findTask = () => {
      let found = null
      setTasks((prev) => { found = prev.find((t) => t.id === id) ?? null; return prev })
      return found
    }
    const t0 = findTask()
    const taskId = t0?.taskId
    if (!taskId) {
      patchTask(id, { taskStatus: 'failed', error: '流连接已断开' })
      return
    }

    const POLL_INTERVAL_MS = 4000
    const MAX_ATTEMPTS = 90  // ~6 min total grace period
    for (let i = 0; i < MAX_ATTEMPTS; i++) {
      try {
        const state = await getTask(taskId)
        if (state.status === 'finished') {
          patchTask(id, {
            taskStatus: 'finished',
            progress: 1.0,
            processedFrames: state.processed_frames,
            totalFrames: state.total_frames,
            zipReady: !!state.zip_ready,
          })
          return
        }
        if (state.status === 'failed') {
          patchTask(id, {
            taskStatus: 'failed',
            error: state.error || '任务在服务器端失败',
          })
          return
        }
        if (state.status === 'cancelled') {
          patchTask(id, {
            taskStatus: 'cancelled',
            processedFrames: state.processed_frames,
            totalFrames: state.total_frames,
          })
          return
        }
        if (state.status === 'paused') {
          patchTask(id, {
            taskStatus: 'paused',
            progress: state.progress,
            processedFrames: state.processed_frames,
            totalFrames: state.total_frames,
            error: null,
          })
          // Keep polling — user might resume or cancel later.
        } else {
          // Still running / packaging.
          const nextStatus =
            state.status === 'packaging' ||
            state.processed_frames >= state.total_frames
              ? 'packaging'
              : 'running'
          patchTask(id, {
            taskStatus: nextStatus,
            progress: state.progress,
            processedFrames: state.processed_frames,
            totalFrames: state.total_frames,
            error: null,
          })
        }
      } catch (err) {
        // Network blip — keep retrying within grace period.
        console.warn('reconcile poll failed, retrying:', err?.message)
      }
      await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS))
    }
    patchTask(id, { taskStatus: 'failed', error: '与服务器失联，已超过等待时长' })
  }, [patchTask])

  // ── Run a single task through the full workflow ────────────────────────
  const runTask = useCallback(async (id, prompt, detectionInterval) => {
    const current = tasks.find((t) => t.id === id)
    if (!current || !current.file) return

    patchTask(id, { taskStatus: 'uploading', uploadProgress: 0, error: null })

    try {
      // 1. Upload
      const videoInfo = await uploadVideo(current.file, (pct) => {
        patchTask(id, { uploadProgress: pct })
      })
      patchTask(id, { videoInfo, videoId: videoInfo.video_id, uploadProgress: 100 })

      // 2. Start detection
      patchTask(id, { taskStatus: 'pending' })
      const task = await startDetection({
        video_id: videoInfo.video_id,
        prompt,
        detection_interval: detectionInterval || undefined,
      })
      patchTask(id, { taskId: task.task_id, taskStatus: 'pending' })

      // 3. SSE
      const es = new EventSource(getStreamUrl(task.task_id))
      streamsRef.current.set(id, es)

      es.onmessage = (evt) => {
        try {
          handleStreamEvent(id, JSON.parse(evt.data))
        } catch (e) {
          console.error('SSE parse failed:', e)
        }
      }
      es.onerror = async () => {
        es.close()
        streamsRef.current.delete(id)
        // SSE can drop during long ZIP packaging even with heartbeats
        // (proxies, WiFi, sleep). Before declaring failure, ask the
        // server for the authoritative task state.
        await reconcileWithServer(id)
      }
    } catch (err) {
      patchTask(id, { taskStatus: 'failed', error: err.message || String(err) })
    }
  }, [tasks, patchTask, handleStreamEvent, reconcileWithServer])

  // ── Public: start every queued task in parallel ────────────────────────
  const startAll = useCallback(async (prompt, detectionInterval) => {
    const toStart = tasks.filter((t) =>
      ['queued', 'failed', 'cancelled'].includes(t.taskStatus)
    )
    for (const t of toStart) {
      if (t.taskStatus !== 'queued') {
        closeStream(t.id)
        setTasks((prev) =>
          prev.map((x) =>
            x.id === t.id ? { ...x, ...newTask(x.file), id: x.id } : x
          )
        )
      }
    }
    const ids = toStart.map((t) => t.id)
    await Promise.all(ids.map((id) => runTask(id, prompt, detectionInterval)))
  }, [tasks, runTask, closeStream])

  const startOne = useCallback((id, prompt, detectionInterval) => {
    return runTask(id, prompt, detectionInterval)
  }, [runTask])

  // ── Control actions: cancel / pause / resume ──────────────────────────
  const _getBackendTaskId = (id) => {
    // Read the current (possibly-stale) snapshot without adding tasks to deps.
    let taskId = null
    setTasks((prev) => {
      const t = prev.find((x) => x.id === id)
      taskId = t?.taskId ?? null
      return prev
    })
    return taskId
  }

  const cancel = useCallback(async (id) => {
    const backendId = _getBackendTaskId(id)
    if (!backendId) {
      // Task never reached the server — just drop it locally.
      patchTask(id, { taskStatus: 'cancelled' })
      return
    }
    try {
      await cancelDetection(backendId)
      // Optimistic UI; the 'cancelled' SSE event will confirm.
      patchTask(id, (t) =>
        ['finished', 'failed', 'cancelled'].includes(t.taskStatus)
          ? {}
          : { taskStatus: 'cancelled' }
      )
    } catch (err) {
      patchTask(id, { error: err.message || String(err) })
    }
  }, [patchTask])

  const pause = useCallback(async (id) => {
    const backendId = _getBackendTaskId(id)
    if (!backendId) return
    try {
      await pauseDetection(backendId)
      patchTask(id, (t) =>
        t.taskStatus === 'running' ? { taskStatus: 'paused' } : {}
      )
    } catch (err) {
      patchTask(id, { error: err.message || String(err) })
    }
  }, [patchTask])

  const resume = useCallback(async (id) => {
    const backendId = _getBackendTaskId(id)
    if (!backendId) return
    try {
      await resumeDetection(backendId)
      patchTask(id, (t) =>
        t.taskStatus === 'paused' ? { taskStatus: 'running' } : {}
      )
    } catch (err) {
      patchTask(id, { error: err.message || String(err) })
    }
  }, [patchTask])

  return {
    tasks,
    addFiles,
    removeTask,
    clearAll,
    resetOne,
    startAll,
    startOne,
    cancel,
    pause,
    resume,
  }
}
