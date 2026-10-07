import { useMemo, useRef, useState } from 'react'
import { ZoomIn } from 'lucide-react'
import { fmt, toOriginal } from '../timeline.js'

function tickStep(duration, zoom) {
  const target = duration / (10 * zoom)
  return [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300].find((s) => s >= target) ?? 600
}

export default function Timeline({ duration, plan, map, subtitles, time, onSeek }) {
  const [zoom, setZoom] = useState(1)
  const trackRef = useRef(null)
  const pct = (t) => `${(t / duration) * 100}%`

  const cuts = useMemo(() => {
    const out = []
    let cursor = 0
    for (const [s, e] of plan.keep) {
      if (s > cursor + 0.001) out.push([cursor, s])
      cursor = e
    }
    if (cursor < duration - 0.001) out.push([cursor, duration])
    return out
  }, [plan.keep, duration])

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
        <h2 className="mr-auto text-sm font-semibold text-ink-100">타임라인 <span className="font-normal text-ink-400">(원본 기준)</span></h2>
        <span className="flex items-center gap-1.5"><i className="size-2.5 rounded-sm bg-keep" /> 남김</span>
        <span className="flex items-center gap-1.5"><i className="cut-hatch size-2.5 rounded-sm" /> 잘림</span>
        <span className="flex items-center gap-1.5"><i className="h-2.5 w-0.5 bg-rose-400" /> 제거된 말</span>
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

          {/* 영상 레인 */}
          <div className="relative mt-2 h-10 overflow-hidden rounded-md bg-ink-850">
            {plan.keep.map(([s, e], i) => (
              <div
                key={i}
                className="absolute inset-y-0 border-x border-ink-950/60 bg-keep/80"
                style={{ left: pct(s), width: pct(e - s) }}
                title={`남김 ${fmt(s)} – ${fmt(e)}`}
              />
            ))}
            {cuts.map(([s, e], i) => (
              <div key={i} className="cut-hatch absolute inset-y-0" style={{ left: pct(s), width: pct(e - s) }} title={`잘림 ${(e - s).toFixed(1)}초`} />
            ))}
            {plan.dropped_words?.map((w, i) => (
              <div
                key={i}
                className="absolute bottom-0 h-3 w-0.5 bg-rose-400"
                style={{ left: pct((w.start + w.end) / 2) }}
                title={`제거: "${w.text}" (${fmt(w.start)})`}
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
