import { useEffect, useRef } from 'react'
import { Merge, Play, Trash2, Type } from 'lucide-react'
import { fmt, toEdited } from '../timeline.js'

export default function SubtitleList({ subtitles, setSubtitles, map, time, onSeekEdited }) {
  const editedT = toEdited(map, time)
  const active = subtitles.findIndex((s) => editedT >= s.start && editedT < s.end)
  const listRef = useRef(null)
  const follow = useRef(true)

  useEffect(() => {
    if (active < 0 || !follow.current) return
    const el = listRef.current?.querySelector(`[data-idx="${active}"]`)
    el?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [active])

  const update = (i, patch) => setSubtitles((list) => list.map((s, k) => (k === i ? { ...s, ...patch } : s)))
  const remove = (i) => setSubtitles((list) => list.filter((_, k) => k !== i))
  const mergeNext = (i) =>
    setSubtitles((list) => {
      if (i + 1 >= list.length) return list
      const merged = { text: `${list[i].text} ${list[i + 1].text}`, start: list[i].start, end: list[i + 1].end }
      return [...list.slice(0, i), merged, ...list.slice(i + 2)]
    })

  const setTime = (i, key, value) => {
    const v = Number(value)
    if (Number.isNaN(v)) return
    const s = subtitles[i]
    const prevEnd = i > 0 ? subtitles[i - 1].end : 0
    const nextStart = i + 1 < subtitles.length ? subtitles[i + 1].start : map.total
    if (key === 'start') update(i, { start: Math.min(Math.max(prevEnd, v), s.end - 0.1) })
    else update(i, { end: Math.max(Math.min(nextStart, v), s.start + 0.1) })
  }

  return (
    <div className="card overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 border-b border-ink-800 px-4 py-3">
        <h2 className="flex shrink-0 items-center gap-2 text-sm font-semibold">
          <Type className="size-4 text-accent" /> 자막 <span className="font-normal text-ink-400">{subtitles.length}개 · 편집본 기준 시간</span>
        </h2>
        <span className="text-xs text-ink-400">여기서 고친 내용이 CapCut 드래프트에 들어가요</span>
      </div>
      <ol
        ref={listRef}
        className="max-h-[440px] divide-y divide-ink-800/70 overflow-y-auto [scrollbar-width:thin]"
        onMouseEnter={() => (follow.current = false)}
        onMouseLeave={() => (follow.current = true)}
      >
        {subtitles.map((s, i) => (
          <li
            key={i}
            data-idx={i}
            className={`group grid grid-cols-[2rem_minmax(0,1fr)] gap-3 px-4 py-2.5 transition sm:grid-cols-[2rem_9.5rem_minmax(0,1fr)_auto] sm:items-center
              ${i === active ? 'bg-accent/8 shadow-[inset_3px_0_0_0_var(--color-accent)]' : 'hover:bg-ink-850/70'}`}
          >
            <button
              className={`grid size-7 place-items-center rounded-md font-mono text-xs ${i === active ? 'bg-accent text-ink-950' : 'bg-ink-800 text-ink-300 group-hover:hidden'}`}
              onClick={() => onSeekEdited(s.start)}
            >
              {i + 1}
            </button>
            <button
              className={`hidden size-7 place-items-center rounded-md bg-ink-700 text-ink-100 ${i === active ? '' : 'group-hover:grid'}`}
              onClick={() => onSeekEdited(s.start)}
              title="여기부터 재생 위치로 이동"
            >
              <Play className="size-3.5" fill="currentColor" />
            </button>

            <div className="col-start-2 flex items-center gap-1 font-mono text-xs text-ink-300 sm:col-start-auto">
              <TimeInput value={s.start} onChange={(v) => setTime(i, 'start', v)} />
              <span className="text-ink-600">→</span>
              <TimeInput value={s.end} onChange={(v) => setTime(i, 'end', v)} />
            </div>

            <input
              className="col-start-2 w-full rounded-md border border-transparent bg-transparent px-2 py-1 text-sm outline-none hover:border-ink-700 focus:border-accent/60 focus:bg-ink-850 sm:col-start-auto"
              value={s.text}
              onChange={(e) => update(i, { text: e.target.value })}
            />

            <div className="col-start-2 flex gap-1 opacity-60 transition group-hover:opacity-100 sm:col-start-auto">
              <button className="rounded-md p-1.5 text-ink-300 hover:bg-ink-800 hover:text-ink-100" title="다음 자막과 합치기" onClick={() => mergeNext(i)} disabled={i === subtitles.length - 1}>
                <Merge className="size-3.5" />
              </button>
              <button className="rounded-md p-1.5 text-ink-300 hover:bg-ink-800 hover:text-cut" title="삭제" onClick={() => remove(i)}>
                <Trash2 className="size-3.5" />
              </button>
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}

function TimeInput({ value, onChange }) {
  return (
    <input
      type="number"
      step={0.1}
      min={0}
      value={Number(value.toFixed(2))}
      onChange={(e) => onChange(e.target.value)}
      title={fmt(value)}
      className="w-[4.2rem] rounded-md border border-transparent bg-ink-850 px-1.5 py-1 text-right tabular-nums outline-none [appearance:textfield] hover:border-ink-700 focus:border-accent/60 [&::-webkit-inner-spin-button]:appearance-none"
    />
  )
}
