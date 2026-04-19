/**
 * src/components/ProgressBar.jsx
 * --------------------------------
 * Light-theme progress indicator used for each task row.
 */

import React from 'react'
import { Loader2 } from 'lucide-react'

export default function ProgressBar({
  taskStatus,
  progress,
  processedFrames,
  totalFrames,
  uploadProgress,
  compact = false,
}) {
  const isUploading = taskStatus === 'uploading'
  const isRunning = taskStatus === 'running' || taskStatus === 'pending'
  const isFinished = taskStatus === 'finished'
  const isFailed = taskStatus === 'failed'

  if (taskStatus === 'idle' || taskStatus === 'queued') return null

  const pct = isUploading
    ? uploadProgress
    : Math.round((progress ?? 0) * 100)

  const label = isUploading
    ? `上传中 ${pct}%`
    : taskStatus === 'pending'
    ? '任务排队中…'
    : isRunning
    ? `检测中 ${processedFrames} / ${totalFrames || '?'} 帧`
    : isFinished
    ? `完成 · 共 ${processedFrames} 帧`
    : isFailed
    ? '任务失败'
    : ''

  const barColor = isFailed
    ? 'bg-red-500'
    : isFinished
    ? 'bg-emerald-500'
    : 'bg-brand-500 progress-glow'

  const pctColor = isFailed
    ? 'text-red-500'
    : isFinished
    ? 'text-emerald-600'
    : 'text-brand-600'

  return (
    <div className="flex flex-col gap-1.5">
      <div className={`flex items-center justify-between ${compact ? 'text-xs' : 'text-sm'}`}>
        <div className="flex items-center gap-2 text-ink-700">
          {(isUploading || isRunning) && (
            <Loader2 size={13} className="animate-spin text-brand-500" />
          )}
          <span>{label}</span>
        </div>
        <span className={`font-mono ${pctColor}`}>{pct}%</span>
      </div>

      <div className="h-1.5 bg-ink-100 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
    </div>
  )
}
