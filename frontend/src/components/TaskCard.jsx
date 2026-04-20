/**
 * src/components/TaskCard.jsx
 * ----------------------------
 * One card per uploaded video in the multi-task workspace.
 *
 * Sections:
 *   - Header:   filename, size, video meta, status badge, actions
 *   - Progress: upload / detection progress bar + error
 *   - Live:     real-time detection viewer (auto-shown once frames arrive)
 *   - Modal:    full-screen FramePreview on thumbnail click
 */

import React, { useState, useMemo } from 'react'
import {
  Film, Trash2, RotateCcw, Download, AlertCircle, CheckCircle2, Clock,
  Pause, Play, X, Ban,
} from 'lucide-react'
import ProgressBar from './ProgressBar'
import ResultViewer from './ResultViewer'
import FramePreview from './FramePreview'
import { getDownloadUrl } from '../services/api'

const STATUS_META = {
  queued:    { label: '等待中',   className: 'bg-ink-100 text-ink-600',        icon: Clock },
  uploading: { label: '上传中',   className: 'bg-brand-50 text-brand-600',     icon: Clock },
  pending:   { label: '排队中',   className: 'bg-brand-50 text-brand-600',     icon: Clock },
  running:   { label: '检测中',   className: 'bg-brand-100 text-brand-700',    icon: Clock },
  paused:    { label: '已暂停',   className: 'bg-amber-50 text-amber-700',     icon: Pause },
  packaging: { label: '打包中',   className: 'bg-brand-100 text-brand-700',    icon: Clock },
  finished:  { label: '已完成',   className: 'bg-emerald-50 text-emerald-600', icon: CheckCircle2 },
  failed:    { label: '失败',     className: 'bg-red-50 text-red-600',         icon: AlertCircle },
  cancelled: { label: '已取消',   className: 'bg-ink-100 text-ink-600',        icon: Ban },
}

function formatSize(bytes) {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1e6) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1e9) return `${(bytes / 1e6).toFixed(1)} MB`
  return `${(bytes / 1e9).toFixed(2)} GB`
}

export default function TaskCard({ task, onRemove, onRetry, onCancel, onPause, onResume }) {
  const meta = STATUS_META[task.taskStatus] ?? STATUS_META.queued
  const StatusIcon = meta.icon

  const canRemove = !['uploading', 'pending', 'running', 'paused', 'packaging'].includes(task.taskStatus)
  const canRetry = ['failed', 'cancelled'].includes(task.taskStatus)
  const canDownload = task.zipReady && task.taskId
  const canPause = task.taskStatus === 'running'
  const canResume = task.taskStatus === 'paused'
  const canCancel = ['pending', 'running', 'paused'].includes(task.taskStatus)
  const hasFrames = !!task.latestFrame || task.allFrames.length > 0
  const showViewer =
    ['running', 'paused', 'packaging', 'finished', 'cancelled'].includes(task.taskStatus) || hasFrames

  // Preview modal state — index into the "previewList"
  const [previewIdx, setPreviewIdx] = useState(null)

  // previewList: detected history + optionally the current live frame at the end
  const previewList = useMemo(() => {
    const out = [...task.allFrames]
    if (task.latestFrame) {
      // Only append the live frame if it isn't already the last one in history
      const last = out[out.length - 1]
      if (!last || last.frame_id !== task.latestFrame.frame_id) {
        out.push({ ...task.latestFrame, taskId: task.taskId })
      }
    }
    return out
  }, [task.allFrames, task.latestFrame, task.taskId])

  const openPreviewAt = (idx) => setPreviewIdx(idx)
  const openLive = () => {
    const i = previewList.findIndex(
      (f) => f.frame_id === task.latestFrame?.frame_id
    )
    setPreviewIdx(i >= 0 ? i : previewList.length - 1)
  }
  const closePreview = () => setPreviewIdx(null)

  return (
    <div className="card p-4 flex flex-col gap-3">
      {/* ── Header ────────────────────────────────────────────────────── */}
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-xl bg-brand-50 text-brand-500 flex-shrink-0">
          <Film size={18} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="font-semibold text-ink-800 truncate" title={task.fileName}>
              {task.fileName}
            </p>
            <span
              className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full font-medium ${meta.className}`}
            >
              <StatusIcon size={11} />
              {meta.label}
            </span>
            {task.detectedFrameCount > 0 && (
              <span className="inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 font-medium">
                {task.detectedFrameCount} 帧检测到目标
              </span>
            )}
          </div>
          <p className="text-ink-500 text-xs mt-0.5 flex items-center gap-2 flex-wrap">
            <span>{formatSize(task.fileSize)}</span>
            {task.videoInfo?.total_frames != null && (
              <span>· {task.videoInfo.total_frames} 帧</span>
            )}
            {task.videoInfo?.duration_seconds != null && (
              <span>· {task.videoInfo.duration_seconds.toFixed(1)} s</span>
            )}
            {task.videoInfo?.fps != null && (
              <span>· {task.videoInfo.fps.toFixed(1)} fps</span>
            )}
          </p>
        </div>

        <div className="flex items-center gap-1">
          {canPause && (
            <button
              type="button"
              onClick={() => onPause(task.id)}
              title="暂停检测"
              className="p-2 rounded-lg text-amber-600 hover:bg-amber-50"
            >
              <Pause size={15} />
            </button>
          )}
          {canResume && (
            <button
              type="button"
              onClick={() => onResume(task.id)}
              title="继续检测"
              className="p-2 rounded-lg text-emerald-600 hover:bg-emerald-50"
            >
              <Play size={15} />
            </button>
          )}
          {canCancel && (
            <button
              type="button"
              onClick={() => {
                if (window.confirm('确定要取消该检测任务吗？已处理的帧将保留，但不会生成 ZIP。')) {
                  onCancel(task.id)
                }
              }}
              title="取消检测"
              className="p-2 rounded-lg text-ink-500 hover:text-red-500 hover:bg-red-50"
            >
              <X size={15} />
            </button>
          )}
          {canDownload && (
            <a
              href={getDownloadUrl(task.taskId)}
              download
              title="下载 ZIP"
              className="p-2 rounded-lg text-emerald-600 hover:bg-emerald-50"
            >
              <Download size={15} />
            </a>
          )}
          {canRetry && (
            <button
              type="button"
              onClick={() => onRetry(task.id)}
              title="重试"
              className="p-2 rounded-lg text-ink-500 hover:bg-ink-100"
            >
              <RotateCcw size={15} />
            </button>
          )}
          {canRemove && (
            <button
              type="button"
              onClick={() => onRemove(task.id)}
              title="移除"
              className="p-2 rounded-lg text-ink-400 hover:text-red-500 hover:bg-red-50"
            >
              <Trash2 size={15} />
            </button>
          )}
        </div>
      </div>

      {/* ── Progress ─────────────────────────────────────────────────── */}
      {task.taskStatus !== 'queued' && (
        <ProgressBar
          taskStatus={task.taskStatus}
          progress={task.progress}
          processedFrames={task.processedFrames}
          totalFrames={task.totalFrames}
          uploadProgress={task.uploadProgress}
          compact
        />
      )}

      {/* ── Error ────────────────────────────────────────────────────── */}
      {task.error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-red-700 text-xs">
          ⚠ {task.error}
        </div>
      )}

      {/* ── Real-time viewer (always visible once frames start) ──────── */}
      {showViewer && (
        <div className="pt-2 border-t border-ink-100">
          <ResultViewer
            latestFrame={task.latestFrame}
            allFrames={task.allFrames}
            taskStatus={task.taskStatus}
            onOpenPreview={openPreviewAt}
            onOpenLiveFrame={openLive}
          />
        </div>
      )}

      {/* ── Modal preview ────────────────────────────────────────────── */}
      {previewIdx != null && previewList.length > 0 && (
        <FramePreview
          frames={previewList}
          index={Math.min(previewIdx, previewList.length - 1)}
          onChangeIndex={setPreviewIdx}
          onClose={closePreview}
        />
      )}
    </div>
  )
}
