/**
 * src/components/ResultViewer.jsx
 * ---------------------------------
 * Light-theme "live frame + history grid" viewer for a single task.
 */

import React, { useRef, useEffect, useState } from 'react'
import { Clock, Target, Hash } from 'lucide-react'
import { getFrameUrl } from '../services/api'

// ── Single frame card ─────────────────────────────────────────────────────
function FrameThumbnail({ frame, onClick, active }) {
  const detCount = frame.detections?.length ?? 0
  const imgSrc = frame.taskId && frame.image_filename
    ? getFrameUrl(frame.taskId, frame.image_filename)
    : frame.image_b64
      ? `data:image/jpeg;base64,${frame.image_b64}`
      : null
  return (
    <button
      onClick={() => onClick(frame)}
      type="button"
      className={[
        'frame-card-enter group relative rounded-lg overflow-hidden border transition-colors duration-150 focus:outline-none bg-white',
        active ? 'border-brand-500 ring-2 ring-brand-200' : 'border-ink-200 hover:border-brand-400',
      ].join(' ')}
    >
      <img
        src={imgSrc}
        alt={`Frame ${frame.frame_id}`}
        className="w-full h-20 object-cover"
        loading="lazy"
      />
      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent px-2 py-1">
        <p className="text-white text-[11px] font-mono truncate">{frame.timestamp}</p>
        {detCount > 0 && (
          <p className="text-brand-200 text-[11px]">{detCount} 个目标</p>
        )}
      </div>
    </button>
  )
}

function DetectionBadge({ det }) {
  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-brand-50 border border-brand-100 text-sm">
      <Target size={12} className="text-brand-500 flex-shrink-0" />
      <span className="text-ink-800 truncate">{det.label}</span>
      <span className="text-ink-500 ml-auto text-xs">{(det.score * 100).toFixed(0)}%</span>
      {det.track_id != null && (
        <span className="text-brand-600 text-xs font-mono">#{det.track_id}</span>
      )}
    </div>
  )
}

export default function ResultViewer({ latestFrame, allFrames, taskStatus }) {
  const [selectedFrame, setSelectedFrame] = useState(null)
  const gridRef = useRef(null)

  useEffect(() => {
    if (gridRef.current && taskStatus === 'running') {
      gridRef.current.scrollTop = gridRef.current.scrollHeight
    }
  }, [allFrames?.length, taskStatus])

  const displayFrame = selectedFrame || latestFrame

  if (!displayFrame && (!allFrames || allFrames.length === 0)) {
    return (
      <div className="flex items-center justify-center h-40 text-ink-400 border-2 border-dashed border-ink-200 rounded-xl bg-ink-50/60">
        <p className="text-sm">暂无检测结果</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {displayFrame && (
        <div className="rounded-xl overflow-hidden border border-ink-200 bg-white">
          <div className="flex items-center justify-between px-4 py-2 bg-ink-50 border-b border-ink-200">
            <div className="flex items-center gap-3 text-xs">
              <div className="flex items-center gap-1.5 text-brand-600">
                <Clock size={12} />
                <span className="font-mono">{displayFrame.timestamp}</span>
              </div>
              <div className="flex items-center gap-1.5 text-ink-500">
                <Hash size={12} />
                <span>帧 {displayFrame.frame_id}</span>
              </div>
              <div className="flex items-center gap-1.5 text-ink-500">
                <Target size={12} />
                <span>{displayFrame.detections?.length ?? 0} 个目标</span>
              </div>
            </div>
            {selectedFrame && (
              <button
                type="button"
                onClick={() => setSelectedFrame(null)}
                className="text-xs text-brand-600 hover:text-brand-500"
              >
                返回实时预览
              </button>
            )}
            {taskStatus === 'running' && !selectedFrame && (
              <span className="flex items-center gap-1.5 text-xs text-emerald-600">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 soft-pulse" />
                实时检测中
              </span>
            )}
          </div>

          <img
            src={`data:image/jpeg;base64,${displayFrame.image_b64}`}
            alt={`Detection frame ${displayFrame.frame_id}`}
            className="w-full object-contain max-h-[420px] bg-ink-900/90"
          />

          {displayFrame.detections?.length > 0 && (
            <div className="px-4 py-3 flex flex-wrap gap-2 bg-white">
              {displayFrame.detections.map((det, i) => (
                <DetectionBadge key={i} det={det} />
              ))}
            </div>
          )}
        </div>
      )}

      {allFrames && allFrames.length > 1 && (
        <div>
          <h4 className="text-ink-500 text-xs mb-2">
            历史帧 · {allFrames.length} 帧
          </h4>
          <div
            ref={gridRef}
            className="grid grid-cols-4 sm:grid-cols-6 md:grid-cols-8 gap-2 max-h-44 overflow-y-auto pr-1"
          >
            {allFrames.map((frame) => (
              <FrameThumbnail
                key={frame.frame_id}
                frame={frame}
                active={selectedFrame?.frame_id === frame.frame_id}
                onClick={(f) =>
                  setSelectedFrame(
                    f.frame_id === selectedFrame?.frame_id ? null : f
                  )
                }
              />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
