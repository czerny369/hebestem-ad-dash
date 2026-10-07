import { useEffect, useImperativeHandle, useRef, useState } from 'react'
import { Pause, Play, RotateCcw, Scissors } from 'lucide-react'
import { fmt, nextKeepStart, toEdited, toOriginal } from '../timeline.js'
import { transitionLabel } from './TransitionPanel.jsx'

// 미리보기용 대략적인 모양: 밝게 번쩍 / 어둡게 번쩍 / 살짝 어두워짐
const WHITE = new Set(['闪白', '泛白', 'White_Flash', '闪光灯', '光束', '炫光', '白色烟雾'])
const BLACK = new Set(['闪黑', '眨眼', '快门', '百叶窗'])
function flashColor(type) {
  if (WHITE.has(type)) return 'rgb(255 255 255 / 0.9)'
  if (BLACK.has(type)) return 'rgb(0 0 0 / 0.95)'
  return 'rgb(0 0 0 / 0.55)'
}

/** CapCut 자막 스타일을 대략적으로 흉내 낸 오버레이 */
export function SubtitleOverlay({ text, style, vertical }) {
  if (!text) return null
  const y = style.position ?? (vertical ? -0.55 : -0.8)
  return (
    <div
      className="pointer-events-none absolute inset-x-0 flex -translate-y-1/2 justify-center px-[6%]"
      style={{ top: `${50 - y * 50}%` }}
    >
      <p
        className="text-center leading-tight whitespace-pre-wrap"
        style={{
          // 컨테이너 높이 기준 대략적인 크기 (CapCut 실제 렌더와 약간 다를 수 있음)
          fontSize: `${style.size * (vertical ? 0.42 : 0.62)}cqh`,
          color: style.color,
          fontWeight: style.bold ? 800 : 600,
          WebkitTextStroke: style.border ? `${style.size * 0.09}cqh ${style.border_color}` : undefined,
          paintOrder: 'stroke fill',
          maxWidth: vertical ? '90%' : '82%',
        }}
      >
        {text}
      </p>
    </div>
  )
}

export default function Player({ ref, src, info, plan, map, subtitles, style, vertical, onTime, transitions = [], transitionCatalog }) {
  const videoRef = useRef(null)
  const [playing, setPlaying] = useState(false)
  const [edited, setEdited] = useState(true)
  const [t, setT] = useState(0)
  const [unsupported, setUnsupported] = useState(false)
  const [flash, setFlash] = useState(null) // { type, duration, key }
  const transitionsRef = useRef(transitions)
  transitionsRef.current = transitions
  const editedMode = edited && !!plan

  useImperativeHandle(ref, () => ({
    seekOriginal(time) {
      const v = videoRef.current
      if (v) v.currentTime = time
    },
    seekEdited(time) {
      const v = videoRef.current
      if (v && map) v.currentTime = toOriginal(map, time) + 0.001
    },
  }), [map])

  // 재생 중에는 매 프레임 위치를 확인해서 잘린 구간을 건너뛴다
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    let raf
    let last = -1
    const tick = () => {
      let now = v.currentTime
      if (editedMode && !v.paused) {
        const next = nextKeepStart(plan.keep, now)
        if (next === null) {
          v.pause()
        } else if (next - now > 0.02) {
          // 컷을 건너뛸 때 그 자리에 전환 효과가 있으면 미리보기로 표시
          const k = plan.keep.findIndex(([s]) => s === next) - 1
          const tr = k >= 0 ? transitionsRef.current[k] : null
          if (tr) setFlash({ ...tr, key: performance.now() })
          v.currentTime = next
          now = next
        }
      }
      // 화면 갱신은 초당 ~20회로 제한
      if (Math.abs(now - last) >= 0.05) {
        last = now
        setT(now)
        onTime?.(now)
      }
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [editedMode, plan, onTime])

  const toggle = () => {
    const v = videoRef.current
    if (!v) return
    if (v.paused) {
      if (editedMode && nextKeepStart(plan.keep, v.currentTime) === null) v.currentTime = plan.keep[0]?.[0] ?? 0
      v.play().catch(() => {})
    } else v.pause()
  }

  const inKeep = !plan || plan.keep.some(([s, e]) => t >= s && t <= e)
  const editedT = map ? toEdited(map, t) : t
  const current = map && inKeep ? subtitles.find((s) => editedT >= s.start && editedT < s.end) : null

  const total = editedMode ? map.total : info.duration
  const shown = editedMode ? editedT : t

  return (
    <div className="card overflow-hidden">
      <div className="relative bg-black">
        <div
          className="relative mx-auto [container-type:size]"
          style={{ aspectRatio: `${info.width} / ${info.height}`, width: `min(100%, calc(62vh * ${info.width / info.height}))` }}
        >
          <video
            ref={videoRef}
            src={src}
            className="absolute inset-0 size-full"
            onPlay={() => setPlaying(true)}
            onPause={() => setPlaying(false)}
            onClick={toggle}
            onError={() => setUnsupported(true)}
            onLoadedData={() => setUnsupported(false)}
            playsInline
            preload="auto"
          />
          <SubtitleOverlay text={current?.text} style={style} vertical={vertical} />
          {flash && editedMode && (
            <>
              <div
                key={flash.key}
                className="pointer-events-none absolute inset-0"
                style={{ background: flashColor(flash.type), animation: `tr-flash ${Math.max(0.25, flash.duration)}s ease-in-out forwards` }}
              />
              <span
                key={`chip-${flash.key}`}
                className="pointer-events-none absolute top-3 right-3 rounded-md bg-amber-300 px-2 py-1 text-xs font-semibold text-ink-950 shadow"
                style={{ animation: 'tr-chip 1.2s ease-out forwards' }}
              >
                ◆ {transitionLabel(transitionCatalog, flash.type)}
              </span>
            </>
          )}
          {unsupported && (
            <div className="absolute inset-0 grid place-items-center bg-ink-950/90 p-6 text-center">
              <div>
                <p className="text-sm font-medium">이 브라우저에서는 영상 코덱을 재생할 수 없어요</p>
                <p className="mt-1 text-xs text-ink-400">미리보기만 안 될 뿐, 분석과 CapCut 드래프트 생성은 정상적으로 됩니다. (HEVC 영상은 Chrome/Edge 최신 버전이나 Safari에서 재생돼요)</p>
              </div>
            </div>
          )}
          {plan && !editedMode && !inKeep && (
            <span className="absolute top-3 left-3 rounded-md bg-cut px-2 py-1 text-xs font-semibold text-white shadow">
              잘리는 구간
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-ink-800 px-4 py-3">
        <button className="btn-primary size-9 rounded-full p-0" onClick={toggle} title="재생/일시정지 (영상 클릭)">
          {playing ? <Pause className="size-4" fill="currentColor" /> : <Play className="size-4 translate-x-px" fill="currentColor" />}
        </button>
        <button
          className="btn-ghost size-9 p-0"
          title="처음으로"
          onClick={() => { if (videoRef.current) videoRef.current.currentTime = editedMode ? plan.keep[0]?.[0] ?? 0 : 0 }}
        >
          <RotateCcw className="size-4" />
        </button>
        <span className="font-mono text-sm tabular-nums text-ink-300">
          <span className="text-ink-100">{fmt(shown)}</span> / {fmt(total)}
        </span>

        {plan && (
          <div className="ml-auto flex rounded-lg border border-ink-700 bg-ink-850 p-0.5 text-xs font-medium">
            <button
              className={`flex items-center gap-1.5 rounded-md px-3 py-1.5 transition ${editedMode ? 'bg-accent text-ink-950' : 'text-ink-300 hover:text-ink-100'}`}
              onClick={() => setEdited(true)}
            >
              <Scissors className="size-3.5" /> 편집본 미리보기
            </button>
            <button
              className={`rounded-md px-3 py-1.5 transition ${!editedMode ? 'bg-ink-700 text-ink-100' : 'text-ink-300 hover:text-ink-100'}`}
              onClick={() => setEdited(false)}
            >
              원본
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
