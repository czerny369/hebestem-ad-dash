import { fmt } from '../timeline.js'

export default function Stats({ info, plan, subtitles }) {
  const removed = info.duration - plan.duration
  const pct = info.duration ? Math.round((removed / info.duration) * 100) : 0
  const items = [
    ['원본', fmt(info.duration)],
    ['편집본', fmt(plan.duration), 'text-accent'],
    ['줄어든 시간', `${removed.toFixed(1)}초 (${pct}%)`, 'text-rose-300'],
    ['컷 / 자막', `${Math.max(0, plan.keep.length - 1)}곳 / ${subtitles.length}개`],
  ]
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {items.map(([label, value, color]) => (
        <div key={label} className="card px-4 py-3">
          <p className="text-xs text-ink-400">{label}</p>
          <p className={`mt-0.5 font-mono text-lg font-semibold tabular-nums ${color ?? ''}`}>{value}</p>
        </div>
      ))}
    </div>
  )
}
