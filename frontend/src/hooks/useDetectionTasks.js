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
import { uploadVideo, startDetection, getStreamUrl } from '../services/api'

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
    taskStatus: 'queued',   // queued | uploading | pending | running | finished | failed

    uploadProgress: 0,
    progress: 0,
    processedFrames: 0,
    totalFrames: 0,

    videoInfo: null,
    latestFrame: null,
    allFrames: [],

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
            const { image_b64: _drop, ...meta } = data.frame_result ?? {}
            return {
              ...t,
              taskStatus: 'running',
              progress: data.progress ?? t.progress,
              processedFrames: data.processed_frames ?? t.processedFrames,
              totalFrames: data.total_frames ?? t.totalFrames,
              latestFrame: data.frame_result,
              allFrames: data.frame_result
                ? [...t.allFrames, { ...meta, taskId: t.taskId }]
                : t.allFrames,
            }
          })
        )
        break
      case 'done':
        closeStream(id)
        patchTask(id, (t) => ({
          taskStatus: 'finished',
          progress: 1.0,
          processedFrames: data.processed_frames ?? t.processedFrames,
          zipReady: true,
        }))
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
      es.onerror = () => {
        es.close()
        streamsRef.current.delete(id)
        setTasks((prev) =>
          prev.map((t) =>
            t.id === id && t.taskStatus !== 'finished'
              ? { ...t, taskStatus: 'failed', error: '流连接已断开' }
              : t
          )
        )
      }
    } catch (err) {
      patchTask(id, { taskStatus: 'failed', error: err.message || String(err) })
    }
  }, [tasks, patchTask, handleStreamEvent])

  // ── Public: start every queued task in parallel ────────────────────────
  const startAll = useCallback(async (prompt, detectionInterval) => {
    const ids = tasks
      .filter((t) => t.taskStatus === 'queued' || t.taskStatus === 'failed')
      .map((t) => t.id)
    await Promise.all(ids.map((id) => runTask(id, prompt, detectionInterval)))
  }, [tasks, runTask])

  const startOne = useCallback((id, prompt, detectionInterval) => {
    return runTask(id, prompt, detectionInterval)
  }, [runTask])

  return {
    tasks,
    addFiles,
    removeTask,
    clearAll,
    resetOne,
    startAll,
    startOne,
  }
}
