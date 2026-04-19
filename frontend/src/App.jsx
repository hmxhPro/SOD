/**
 * src/App.jsx
 * ------------
 * Root application component.
 *
 * Sections (top to bottom):
 *   1. Header              - logo + status chip
 *   2. Hero                - marketing-style title + subtitle
 *   3. Feature cards       - "智能检测" / "实时追踪" entry cards
 *   4. Detection workspace - multi-video upload + prompt + task grid
 *   5. Platform modules    - 4-up feature tiles
 *   6. Tech-stack section  - stack summary
 *   7. Footer
 */

import React, { useMemo, useState } from 'react'
import {
  Play, RotateCcw, Settings, Trash2, Sparkles, Activity, CircleDot,
  Target, Film, Zap, LayoutGrid, Database, Cpu, Gauge, Orbit, PackageSearch,
} from 'lucide-react'

import VideoUploader from './components/VideoUploader'
import PromptInput from './components/PromptInput'
import TaskCard from './components/TaskCard'
import { useDetectionTasks } from './hooks/useDetectionTasks'

export default function App() {
  const [prompt, setPrompt] = useState('')
  const [detInterval, setDetInterval] = useState(5)
  const [showAdvanced, setShowAdvanced] = useState(false)

  const {
    tasks, addFiles, removeTask, clearAll, resetOne, startAll, startOne,
  } = useDetectionTasks()

  const counts = useMemo(() => {
    const c = { queued: 0, uploading: 0, running: 0, finished: 0, failed: 0, pending: 0 }
    for (const t of tasks) c[t.taskStatus] = (c[t.taskStatus] || 0) + 1
    return c
  }, [tasks])

  const hasWork = tasks.length > 0
  const anyActive = ['uploading', 'pending', 'running'].some((s) => (counts[s] || 0) > 0)
  const queuedOrFailed = (counts.queued || 0) + (counts.failed || 0)
  const canStart = hasWork && prompt.trim().length > 0 && queuedOrFailed > 0 && !anyActive

  const handleStartAll = async () => {
    if (!canStart) return
    await startAll(prompt.trim(), detInterval)
  }

  const handleRetry = (id) => {
    if (!prompt.trim()) {
      alert('请先填写检测目标描述')
      return
    }
    resetOne(id)
    // Give state a tick before restarting
    setTimeout(() => startOne(id, prompt.trim(), detInterval), 30)
  }

  return (
    <div className="min-h-screen flex flex-col text-ink-800 bg-gradient-to-b from-white via-ink-50 to-white">
      {/* ─── Header ─────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-30 backdrop-blur bg-white/80 border-b border-ink-200/70">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <a href="#" className="flex items-center gap-2.5">
            <span className="flex items-center justify-center w-9 h-9 rounded-xl bg-brand-500 text-white font-bold shadow-brand">
              V
            </span>
            <span className="font-semibold text-ink-900 tracking-tight">
              视频目标检测 <span className="text-brand-500">Agent</span>
            </span>
          </a>

          <div className="flex items-center gap-4">
            <span className="hidden md:inline-flex items-center gap-2 text-xs text-emerald-600 bg-emerald-50 border border-emerald-100 px-3 py-1 rounded-full">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 soft-pulse" />
              平台运行正常
            </span>
            <a
              href="/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="text-ink-500 hover:text-brand-600 text-sm transition-colors"
            >
              API 文档 →
            </a>
          </div>
        </div>
      </header>

      {/* ─── Hero ───────────────────────────────────────────────────────── */}
      <section className="relative">
        <div className="absolute inset-0 bg-hero-glow pointer-events-none" />
        <div className="relative max-w-5xl mx-auto px-6 py-20 text-center">
          <span className="inline-flex items-center gap-2 chip mb-6">
            <Sparkles size={12} className="text-brand-500" />
            2026 智慧视觉 · 自然语言驱动的视频检测
          </span>
          <h1 className="text-4xl md:text-6xl font-bold tracking-tight leading-tight">
            从一段视频到洞察，
            <br />
            <span className="text-gradient-brand">每一帧都被看见</span>
          </h1>
          <p className="mt-6 text-ink-500 text-base md:text-lg max-w-2xl mx-auto">
            集<span className="text-ink-800 font-medium">视频上传、开放词汇检测、多目标跟踪、实时结果流</span>于一体的视觉智能平台。基于 FastAPI + Grounding DINO + ByteTrack + React 全栈架构打造。
          </p>

          {/* CTA cards */}
          <div className="mt-10 grid md:grid-cols-2 gap-5 text-left">
            <a href="#workspace" className="card p-5 hover:shadow-soft transition-shadow group">
              <div className="flex items-start gap-3">
                <span className="p-2.5 rounded-xl bg-brand-500 text-white">
                  <Target size={18} />
                </span>
                <div className="flex-1">
                  <h3 className="font-semibold text-ink-900">开始批量检测</h3>
                  <p className="text-ink-500 text-sm mt-1">
                    上传多个视频，用一句话描述你想检测的目标，实时查看结果。
                  </p>
                  <p className="mt-3 text-brand-600 text-sm flex items-center gap-1">
                    进入工作台 <span className="group-hover:translate-x-0.5 transition-transform">→</span>
                  </p>
                </div>
              </div>
            </a>
            <a href="#modules" className="card p-5 hover:shadow-soft transition-shadow group">
              <div className="flex items-start gap-3">
                <span className="p-2.5 rounded-xl bg-ink-900 text-white">
                  <LayoutGrid size={18} />
                </span>
                <div className="flex-1">
                  <h3 className="font-semibold text-ink-900">核心能力</h3>
                  <p className="text-ink-500 text-sm mt-1">
                    开放词汇检测、持久跟踪、实时流式结果、ZIP 结果归档。
                  </p>
                  <p className="mt-3 text-ink-800 text-sm flex items-center gap-1">
                    查看模块 <span className="group-hover:translate-x-0.5 transition-transform">→</span>
                  </p>
                </div>
              </div>
            </a>
          </div>
        </div>
      </section>

      {/* ─── Workspace ─────────────────────────────────────────────────── */}
      <section id="workspace" className="max-w-7xl mx-auto w-full px-6 py-14">
        <div className="mb-8 text-center">
          <h2 className="text-2xl md:text-3xl font-bold text-ink-900">检测工作台</h2>
          <p className="mt-2 text-ink-500 text-sm">
            批量上传视频 · 自然语言描述目标 · 独立任务并发处理
          </p>
        </div>

        <div className="grid lg:grid-cols-[22rem_1fr] gap-6">
          {/* ── Left: config ──────────────────────────────────────── */}
          <aside className="flex flex-col gap-5">
            <div className="card p-5 flex flex-col gap-5">
              <div className="flex items-center justify-between">
                <h3 className="font-semibold text-ink-900 flex items-center gap-2">
                  <span className="p-1.5 rounded-lg bg-brand-50 text-brand-500">
                    <Film size={14} />
                  </span>
                  上传视频
                </h3>
                {hasWork && (
                  <button
                    type="button"
                    onClick={clearAll}
                    disabled={anyActive}
                    className={[
                      'text-xs flex items-center gap-1',
                      anyActive
                        ? 'text-ink-300 cursor-not-allowed'
                        : 'text-ink-500 hover:text-red-500',
                    ].join(' ')}
                  >
                    <Trash2 size={12} />
                    清空全部
                  </button>
                )}
              </div>

              <VideoUploader
                onFilesSelected={addFiles}
                disabled={false}
                hasTasks={hasWork}
              />

              <PromptInput
                value={prompt}
                onChange={setPrompt}
                disabled={anyActive}
              />

              {/* Advanced toggle */}
              <button
                type="button"
                onClick={() => setShowAdvanced((v) => !v)}
                className="flex items-center gap-2 text-ink-500 hover:text-ink-800 text-sm transition-colors"
              >
                <Settings size={14} />
                高级设置
                <span className="ml-auto">{showAdvanced ? '▲' : '▼'}</span>
              </button>

              {showAdvanced && (
                <div className="flex flex-col gap-3 pl-3 border-l-2 border-brand-100">
                  <label className="flex flex-col gap-1">
                    <span className="text-ink-700 text-sm">
                      检测间隔（每 N 帧全量检测）
                    </span>
                    <div className="flex items-center gap-3">
                      <input
                        type="range"
                        min={1}
                        max={30}
                        value={detInterval}
                        onChange={(e) => setDetInterval(Number(e.target.value))}
                        disabled={anyActive}
                        className="flex-1 accent-brand-500"
                      />
                      <span className="text-brand-600 font-mono w-8 text-center">
                        {detInterval}
                      </span>
                    </div>
                    <span className="text-ink-400 text-xs">
                      值越大速度越快，精度略降。推荐 3 ~ 10
                    </span>
                  </label>
                </div>
              )}

              <button
                type="button"
                onClick={handleStartAll}
                disabled={!canStart}
                className={[
                  'w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl font-semibold transition-all duration-200',
                  canStart
                    ? 'bg-brand-500 text-white hover:bg-brand-600 shadow-brand'
                    : 'bg-ink-100 text-ink-400 cursor-not-allowed',
                ].join(' ')}
              >
                {anyActive ? <Activity size={16} className="animate-pulse" /> : <Play size={16} />}
                {anyActive
                  ? `处理中…（${counts.running + counts.uploading + counts.pending} 个任务）`
                  : queuedOrFailed > 0
                  ? `开始检测（${queuedOrFailed} 个视频）`
                  : hasWork
                  ? '全部已处理'
                  : '开始检测'}
              </button>
            </div>

            {/* Stats card */}
            {hasWork && (
              <div className="card p-4 text-sm">
                <h4 className="text-ink-500 font-medium mb-3 text-xs uppercase tracking-wider">
                  任务统计
                </h4>
                <div className="grid grid-cols-2 gap-y-2 gap-x-4">
                  <StatRow label="视频总数" value={tasks.length} />
                  <StatRow label="等待中" value={counts.queued || 0} tone="ink" />
                  <StatRow label="进行中" value={(counts.uploading || 0) + (counts.pending || 0) + (counts.running || 0)} tone="brand" />
                  <StatRow label="已完成" value={counts.finished || 0} tone="emerald" />
                  {counts.failed > 0 && (
                    <StatRow label="失败" value={counts.failed} tone="red" />
                  )}
                </div>
              </div>
            )}
          </aside>

          {/* ── Right: task grid ──────────────────────────────────── */}
          <section className="min-w-0">
            {!hasWork ? (
              <div className="card p-12 flex flex-col items-center justify-center text-center gap-3 h-full">
                <span className="p-4 rounded-2xl bg-brand-50 text-brand-500">
                  <PackageSearch size={32} />
                </span>
                <h3 className="text-lg font-semibold text-ink-800">还没有上传视频</h3>
                <p className="text-ink-500 text-sm max-w-sm">
                  在左侧上传区拖拽或选择视频，再填写检测目标，即可开始批量处理。
                </p>
                <div className="mt-2 flex flex-wrap justify-center gap-2 text-xs">
                  <span className="chip"><CircleDot size={10} className="text-brand-500" /> 多视频并发</span>
                  <span className="chip"><CircleDot size={10} className="text-brand-500" /> 不限文件大小</span>
                  <span className="chip"><CircleDot size={10} className="text-brand-500" /> 实时结果流</span>
                </div>
              </div>
            ) : (
              <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                {tasks.map((t) => (
                  <TaskCard
                    key={t.id}
                    task={t}
                    onRemove={removeTask}
                    onRetry={handleRetry}
                  />
                ))}
              </div>
            )}
          </section>
        </div>
      </section>

      {/* ─── Platform modules ──────────────────────────────────────────── */}
      <section id="modules" className="max-w-7xl mx-auto w-full px-6 py-16">
        <div className="text-center mb-10">
          <h2 className="text-2xl md:text-3xl font-bold text-ink-900">平台核心模块</h2>
          <p className="mt-2 text-ink-500 text-sm">
            覆盖视频智能分析全流程的一体化解决方案
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <ModuleCard
            icon={<Target size={18} />}
            title="开放词汇检测"
            desc="Grounding DINO 驱动的自然语言检测"
            iconBg="bg-emerald-50 text-emerald-600"
          />
          <ModuleCard
            icon={<Orbit size={18} />}
            title="多目标跟踪"
            desc="ByteTrack 分配持久 track_id"
            iconBg="bg-brand-50 text-brand-600"
          />
          <ModuleCard
            icon={<Activity size={18} />}
            title="实时结果流"
            desc="SSE 推送，逐帧渲染无需刷新"
            iconBg="bg-sky-50 text-sky-600"
          />
          <ModuleCard
            icon={<Gauge size={18} />}
            title="结果归档"
            desc="一键打包 ZIP，含标注图与 JSON/CSV"
            iconBg="bg-violet-50 text-violet-600"
          />
        </div>
      </section>

      {/* ─── Tech Stack ────────────────────────────────────────────────── */}
      <section className="max-w-7xl mx-auto w-full px-6 pb-20">
        <div className="grid lg:grid-cols-[1fr_1.6fr] gap-8 items-center">
          <div>
            <span className="text-brand-500 text-sm font-semibold">技术架构</span>
            <h2 className="mt-2 text-2xl md:text-3xl font-bold text-ink-900">
              全栈工程化实践
            </h2>
            <p className="mt-3 text-ink-500 text-sm">
              采用现代化前后端分离架构，实时推送 + GPU 推理 + 可扩展调度，支持多任务并发处理。
            </p>
          </div>
          <div className="grid sm:grid-cols-2 gap-3">
            <StackItem label="前端" value="React 18 + Vite + Tailwind" icon={<Cpu size={14} />} />
            <StackItem label="后端" value="FastAPI + asyncio + SSE" icon={<Zap size={14} />} />
            <StackItem label="检测" value="Grounding DINO / Florence-2" icon={<Target size={14} />} />
            <StackItem label="跟踪" value="ByteTrack" icon={<Orbit size={14} />} />
            <StackItem label="存储" value="本地 uploads + ZIP 归档" icon={<Database size={14} />} />
            <StackItem label="部署" value="Linux + NVIDIA CUDA" icon={<Gauge size={14} />} />
          </div>
        </div>
      </section>

      {/* ─── Footer ────────────────────────────────────────────────────── */}
      <footer className="border-t border-ink-200/70 py-6">
        <div className="max-w-7xl mx-auto px-6 flex flex-col sm:flex-row items-center justify-between gap-2 text-xs text-ink-500">
          <span>© 2026 Video Detection Agent · Grounding DINO + ByteTrack</span>
          <span className="flex items-center gap-1">
            BUILT WITH <span className="text-red-500">♥</span> ON FASTAPI + REACT
          </span>
        </div>
      </footer>
    </div>
  )
}

// ─── Small presentational helpers ────────────────────────────────────────
function StatRow({ label, value, tone }) {
  const toneMap = {
    brand:   'text-brand-600',
    emerald: 'text-emerald-600',
    red:     'text-red-500',
    ink:     'text-ink-800',
  }
  return (
    <>
      <span className="text-ink-500">{label}</span>
      <span className={`font-mono text-right ${toneMap[tone] || 'text-ink-800'}`}>{value}</span>
    </>
  )
}

function ModuleCard({ icon, title, desc, iconBg }) {
  return (
    <div className="card p-5 hover:shadow-soft transition-shadow">
      <span className={`inline-flex p-2.5 rounded-xl ${iconBg}`}>{icon}</span>
      <h3 className="mt-3 font-semibold text-ink-900">{title}</h3>
      <p className="mt-1 text-ink-500 text-xs">{desc}</p>
    </div>
  )
}

function StackItem({ label, value, icon }) {
  return (
    <div className="card px-4 py-3">
      <div className="flex items-center gap-2 text-ink-500 text-[11px] uppercase tracking-wider">
        {icon}
        {label}
      </div>
      <div className="mt-1 font-semibold text-ink-900 text-sm">{value}</div>
    </div>
  )
}
