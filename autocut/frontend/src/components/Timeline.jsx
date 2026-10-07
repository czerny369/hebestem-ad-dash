import { useMemo, useRef, useState } from 'react'
import { ZoomIn } from 'lucide-react'
import { PIECE_REASONS, fmt, toOriginal } from '../timeline.js'
import { transitionLabel } from './TransitionPanel.jsx'

function tickStep(duration, zoom) {
  const target = duration / (10 * zoom)
  return [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300].find((s) => s >= target) ?? 600
}

export default function Timeline({ duration, plan, map, subtitles, time, onSeek, onTogglePiece, transitions = [], transitionCatalog, onToggleTransition }) {
  const [zoom, setZoom] = useState(1)
  const trackRef = useRef(null)
  const pct = (t) => `${(t / duration) * 100}%`

  const subsOrig = useMemo(
    () => subtitles.map((s) => [toOriginal(map, s.start), toOriginal(map, s.end), s.text]),
    [subtitles, map],
  )

  const step = tickStep(duration, zoom)
  const ticks = []
  for (let t = 0; t <= duration; t += step) ticks.push(t)

  const seekFromEvent = (e) => {
    const rect = trackRef.current.getBoundingClientRect()
    const x = Math.min(Math.max(0, e.clientX - rect.left), rect.width)
    onSeek(x / rect.width * duration)
  }

  return (
    <div className="card p-4">
      <div className="mb-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-ink-300">
        <h2 className="mr-auto text-sm font-semibold text-ink-100">
          타임라인 <span className="font-normal text-ink-400">(원본 기준 · 구간을 클릭하면 남김/잘림 전환)</span>
        </h2>
        <span className="flex items-center gap-1.5"><i className="size-2.5 rounded-sm bg-keep" /> 남김</span>
        <span className="flex items-center gap-1.5"><i className="cut-hatch size-2.5 rounded-sm" /> 잘림</span>
        {plan.pieces.some((p) => p.reason === 'ng') && <span className="flex items-center gap-1.5"><i className="ng-hatch size-2.5 rounded-sm" /> NG</span>}
        {plan.pieces.some((p) => p.speed !== 1) && <span className="flex items-center gap-1.5"><i className="size-2.5 rounded-sm bg-violet-400/80" /> 빨리감기</span>}
        <span className="flex items-center gap-1.5"><i className="h-2.5 w-0.5 bg-rose-400" /> 제거된 말</span>
        <span className="flex items-center gap-1.5"><i className="size-2 rotate-45 bg-amber-300" /> 전환 효과</span>
        <label className="flex items-center gap-2">
          <ZoomIn className="size-3.5" />
          <input type="range" min={1} max={20} step={1} value={zoom} onChange={(e) => setZoom(Number(e.target.value))} className="w-24" />
        </label>
      </div>

      <div className="overflow-x-auto pb-1 [scrollbar-width:thin]">
        <div
          ref={trackRef}
          className="relative cursor-pointer select-none"
          style={{ width: `${zoom * 100}%` }}
          onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); seekFromEvent(e) }}
          onPointerMove={(e) => e.buttons === 1 && seekFromEvent(e)}
        >
          {/* 눈금 */}
          <div className="relative h-5 border-b border-ink-800">
            {ticks.map((t, i) => (
              <span
                key={t}
                className={`absolute top-0 font-mono text-[10px] text-ink-400 ${i === 0 ? '' : t > duration - step / 2 ? '-translate-x-full' : '-translate-x-1/2'}`}
                style={{ left: pct(t) }}
              >
                {fmt(t, false)}
              </span>
            ))}
          </div>

          {/* 전환 효과 레인: 컷마다 ◆ (클릭해서 켜기/끄기) */}
          <div className="relative mt-1.5 h-4">
            {plan.keep.slice(0, -1).map(([, e], i) => {
              const next = plan.keep[i + 1][0]
              const tr = transitions[i]
              return (
                <button
                  key={i}
                  onPointerDown={(ev) => ev.stopPropagation()}
                  onClick={(ev) => { ev.stopPropagation(); onToggleTransition?.(i) }}
                  className={`absolute top-1/2 size-2.5 -translate-x-1/2 -translate-y-1/2 rotate-45 transition hover:scale-150
                    ${tr ? 'bg-amber-300 shadow-[0_0_6px_rgb(252_211_77/0.7)]' : 'border border-ink-600 bg-ink-800 hover:border-amber-300'}
                    ${tr?.overridden ? 'ring-2 ring-amber-300/40 ring-offset-1 ring-offset-ink-900' : ''}`}
                  style={{ left: pct((e + next) / 2) }}
                  title={`컷 ${i + 1} (${(next - e).toFixed(1)}초 잘림)\n${tr ? `전환: ${transitionLabel(transitionCatalog, tr.type)} ${tr.duration.toFixed(1)}초` : '전환 없음'}\n클릭해서 ${tr ? '끄기' : '켜기'}`}
                />
              )
            })}
          </div>

          {/* 영상 레인: 조각을 클릭하면 남김 ↔ 잘림 */}
          <div className="relative mt-1 h-10 overflow-hidden rounded-md bg-ink-850">
            {plan.pieces.map((p, i) => {
              const fast = p.keep && p.speed !== 1
              const why = PIECE_REASONS[p.reason] ?? ''
              return (
                <button
                  key={i}
                  onPointerDown={(e) => e.stopPropagation()}
                  onClick={(e) => { e.stopPropagation(); onTogglePiece?.(i) }}
                  className={`group/piece absolute inset-y-0 border-x border-ink-950/60 transition hover:brightness-125
                    ${p.keep ? (fast ? 'bg-violet-400/70' : 'bg-keep/80') : p.reason === 'ng' ? 'ng-hatch' : 'cut-hatch'}`}
                  style={{ left: pct(p.start), width: pct(p.end - p.start) }}
                  title={`${p.keep ? '남김' : '잘림'}${p.label ? ` · ${p.label}` : why ? ` · ${why}` : ''} (${fmt(p.start)} – ${fmt(p.end)})\n클릭해서 ${p.keep ? '자르기' : '되살리기'}`}
                >
                  {fast && (
                    <span className="pointer-events-none absolute inset-0 grid place-items-center overflow-hidden text-[10px] font-semibold whitespace-nowrap text-white/95">
                      {p.speed.toFixed(1)}x
                    </span>
                  )}
                  {!p.keep && p.reason === 'ng' && (
                    <span className="pointer-events-none absolute inset-0 grid place-items-center overflow-hidden text-[10px] font-bold text-orange-100">NG</span>
                  )}
                </button>
              )
            })}
            {plan.dropped_words?.map((w, i) => (
              <div
                key={i}
                className="pointer-events-none absolute bottom-0 h-3 w-0.5 bg-rose-400"
                style={{ left: pct((w.start + w.end) / 2) }}
              />
            ))}
          </div>

          {/* 자막 레인 */}
          <div className="relative mt-1.5 h-7 rounded-md bg-ink-850/60">
            {subsOrig.map(([s, e, text], i) => (
              <div
                key={i}
                className="absolute inset-y-0.5 overflow-hidden rounded border border-sky-400/30 bg-sky-500/20 px-1 text-[10px] leading-6 whitespace-nowrap text-sky-100"
                style={{ left: pct(s), width: pct(Math.max(0, e - s)) }}
                title={text}
              >
                {text}
              </div>
            ))}
          </div>

          {/* 재생 위치 */}
          <div className="pointer-events-none absolute inset-y-0 w-px bg-white shadow-[0_0_6px_rgb(255_255_255/0.7)]" style={{ left: pct(time) }}>
            <span className="absolute -top-0.5 left-1/2 size-2 -translate-x-1/2 rotate-45 bg-white" />
          </div>
        </div>
      </div>
    </div>
  )
}
