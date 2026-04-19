/**
 * src/components/TaskCard.jsx
 * ----------------------------
 * One row / card per uploaded video in the multi-task grid.
 *
 * Shows:
 *   - filename + size + status badge
 *   - progress bar
 *   - collapsible ResultViewer (latest + history)
 *   - per-task actions (remove / retry / download)
 */

import React, { useState } from 'react'
import {
  Film, ChevronDown, ChevronUp, Trash2, RotateCcw, Download, AlertCircle, CheckCircle2, Clock,
} from 'lucide-react'
import ProgressBar from './ProgressBar'
import ResultViewer from './ResultViewer'
import { getDownloadUrl } from '../services/api'

const STATUS_META = {
  queued:    { label: '等待中',   className: 'bg-ink-100 text-ink-600',     icon: Clock },
  uploading: { label: '上传中',   className: 'bg-brand-50 text-brand-600',  icon: Clock },
  pending:   { label: '排队中',   className: 'bg-brand-50 text-brand-600',  icon: Clock },
  running:   { label: '检测中',   className: 'bg-brand-100 text-brand-700', icon: Clock },
  finished:  { label: '已完成',   className: 'bg-emerald-50 text-emerald-600', icon: CheckCircle2 },
  failed:    { label: '失败',     className: 'bg-red-50 text-red-600',      icon: AlertCircle },
}

function formatSize(bytes) {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1e6) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1e9) return `${(bytes / 1e6).toFixed(1)} MB`
  return `${(bytes / 1e9).toFixed(2)} GB`
}

export default function TaskCard({ task, onRemove, onRetry }) {
  const [open, setOpen] = useState(false)
  const meta = STATUS_META[task.taskStatus] ?? STATUS_META.queued
  const StatusIcon = meta.icon

  const canRemove = !['uploading', 'pending', 'running'].includes(task.taskStatus)
  const canRetry = ['failed'].includes(task.taskStatus)
  const canDownload = task.zipReady && task.taskId
  const hasContent = task.latestFrame || (task.allFrames && task.allFrames.length > 0)

  return (
    <div className="card p-4 flex flex-col gap-3">
      {/* Header row */}
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-xl bg-brand-50 text-brand-500 flex-shrink-0">
          <Film size={18} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <p className="font-semibold text-ink-800 truncate" title={task.fileName}>
              {task.fileName}
            </p>
            <span
              className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full font-medium ${meta.className}`}
            >
              <StatusIcon size={11} />
              {meta.label}
            </span>
          </div>
          <p className="text-ink-500 text-xs mt-0.5 flex items-center gap-3">
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
          {hasContent && (
            <button
              type="button"
              onClick={() => setOpen((v) => !v)}
              title={open ? '收起' : '展开结果'}
              className="p-2 rounded-lg text-ink-500 hover:bg-ink-100"
            >
              {open ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
            </button>
          )}
        </div>
      </div>

      {/* Progress */}
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

      {/* Error */}
      {task.error && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-red-700 text-xs">
          ⚠ {task.error}
        </div>
      )}

      {/* Expanded viewer */}
      {open && hasContent && (
        <div className="pt-2 border-t border-ink-100">
          <ResultViewer
            latestFrame={task.latestFrame}
            allFrames={task.allFrames}
            taskStatus={task.taskStatus}
          />
        </div>
      )}
    </div>
  )
}
