/**
 * src/components/PromptInput.jsx
 * -------------------------------
 * Text area + example chips for natural-language target description.
 * Light-theme, orange-accent design.
 */

import React from 'react'
import { Search } from 'lucide-react'

const EXAMPLES = [
  '帮我检测视频中的菜园',
  '帮我检测岸边的钓鱼台',
  '帮我检测靠近水边的种菜区域',
  '检测视频中的人物',
  '检测视频中的车辆',
]

export default function PromptInput({ value, onChange, disabled }) {
  return (
    <div className="flex flex-col gap-3">
      <label className="text-ink-800 font-semibold flex items-center gap-2">
        <span className="p-1.5 rounded-lg bg-brand-50 text-brand-500">
          <Search size={14} />
        </span>
        检测目标描述
      </label>

      <textarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        rows={2}
        placeholder="用自然语言描述你想检测的目标，例如：帮我检测视频中的菜园"
        className={[
          'w-full rounded-xl px-4 py-3 text-ink-800 placeholder-ink-400',
          'bg-white border border-ink-200',
          'focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100',
          'resize-none transition-colors duration-200',
          disabled ? 'opacity-60 cursor-not-allowed' : '',
        ].join(' ')}
      />

      {/* Example prompts */}
      <div className="flex flex-wrap gap-2">
        <span className="text-ink-500 text-xs self-center">示例：</span>
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            onClick={() => !disabled && onChange(ex)}
            disabled={disabled}
            type="button"
            className={[
              'text-xs px-3 py-1 rounded-full border border-ink-200 bg-white',
              'text-ink-600 hover:text-brand-600 hover:border-brand-300 hover:bg-brand-50',
              'transition-colors duration-150',
              disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer',
            ].join(' ')}
          >
            {ex}
          </button>
        ))}
      </div>
    </div>
  )
}
