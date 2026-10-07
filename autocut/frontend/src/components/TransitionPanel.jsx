import { useMemo, useState } from 'react'
import { Search, Sparkle, Undo2 } from 'lucide-react'

export function transitionLabel(catalog, id) {
  const item = catalog?.all.find((t) => t.id === id)
  return item ? item.label || item.name : id
}

export default function TransitionPanel({ settings, setSettings, catalog, resolved, keep }) {
  const [query, setQuery] = useState('')
  const [showAll, setShowAll] = useState(false)
  const set = (k) => (v) => setSettings((s) => ({ ...s, [k]: v }))

  const groups = useMemo(() => {
    const g = {}
    for (const p of catalog?.presets ?? []) (g[p.group] ??= []).push(p)
    return g
  }, [catalog])

  const results = useMemo(() => {
    if (!catalog) return []
    const q = query.trim().toLowerCase()
    const list = q
      ? catalog.all.filter((t) => t.id.toLowerCase().includes(q) || t.name.toLowerCase().includes(q) || t.label?.includes(q))
      : catalog.all
    return list.slice(0, 120)
  }, [catalog, query])

  const cuts = Math.max(0, keep.length - 1)
  const active = resolved.filter(Boolean).length
  const overrideCount = Object.keys(settings.overrides ?? {}).length
  const selected = catalog?.all.find((t) => t.id === settings.type)

  return (
    <div className="card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <Sparkle className="size-4 text-accent" /> 전환 효과
        </h2>
        <label className="relative inline-flex cursor-pointer items-center">
          <input type="checkbox" className="peer sr-only" checked={settings.enabled} onChange={(e) => set('enabled')(e.target.checked)} />
          <span className="h-5 w-9 rounded-full bg-ink-700 transition peer-checked:bg-accent" />
          <span className="absolute left-0.5 size-4 rounded-full bg-white transition peer-checked:translate-x-4" />
        </label>
      </div>

      <p className="mb-3 text-xs leading-relaxed text-ink-400">
        잘라낸 자리(컷)에 넣을 효과예요. 말 버벅임처럼 짧게 잘린 곳에 전부 넣으면 산만해서,
        기본은 <b className="text-ink-300">오래 잘린 곳에만</b> 넣어요. 타임라인의 ◆ 표시를 눌러 컷마다 켜고 끌 수 있어요.
      </p>

      <div className={settings.enabled ? '' : 'pointer-events-none opacity-40'}>
        {Object.entries(groups).map(([group, items]) => (
          <div key={group} className="mb-2.5">
            <p className="mb-1.5 text-[11px] font-medium tracking-wide text-ink-400">{group}</p>
            <div className="flex flex-wrap gap-1.5">
              {items.map((p) => (
                <button
                  key={p.id}
                  onClick={() => set('type')(p.id)}
                  className={`rounded-md border px-2 py-1 text-xs transition ${settings.type === p.id
                    ? 'border-accent bg-accent/15 text-emerald-200'
                    : 'border-ink-700 bg-ink-850 text-ink-300 hover:border-ink-600 hover:text-ink-100'}`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>
        ))}

        <button className="mt-1 flex items-center gap-1.5 text-xs text-ink-300 hover:text-accent" onClick={() => setShowAll((v) => !v)}>
          <Search className="size-3.5" /> 전체 {catalog?.all.length ?? 0}개에서 찾기
        </button>
        {showAll && (
          <div className="mt-2 rounded-xl border border-ink-800 bg-ink-850/60 p-2">
            <input className="field mb-2 py-1.5 text-xs" placeholder="이름 검색 (예: 叠化, Flash, 줌)" value={query} onChange={(e) => setQuery(e.target.value)} />
            <ul className="max-h-48 overflow-y-auto text-xs [scrollbar-width:thin]">
              {results.map((t) => (
                <li key={t.id}>
                  <button
                    onClick={() => set('type')(t.id)}
                    className={`flex w-full items-center justify-between gap-2 rounded px-2 py-1 text-left hover:bg-ink-800 ${settings.type === t.id ? 'text-accent' : ''}`}
                  >
                    <span className="truncate">{t.label ? `${t.label} · ` : ''}<span className="text-ink-400">{t.name}</span></span>
                    {t.vip && <span className="shrink-0 rounded bg-amber-400/15 px-1.5 text-[10px] font-semibold text-amber-300">Pro</span>}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
        {selected?.vip && (
          <p className="mt-2 rounded-lg bg-amber-400/10 px-2.5 py-1.5 text-xs text-amber-200">
            CapCut Pro(유료) 효과예요. 무료 계정에서는 내보낼 때 워터마크/제한이 생길 수 있어요.
          </p>
        )}

        <div className="mt-4 space-y-4">
          <label className="block">
            <div className="mb-1.5 flex justify-between text-sm">
              <span>전환 길이</span><span className="font-mono text-xs text-accent">{settings.duration.toFixed(1)}초</span>
            </div>
            <input type="range" min={0.1} max={1.5} step={0.1} value={settings.duration} onChange={(e) => set('duration')(Number(e.target.value))} />
            <p className="mt-1 text-xs text-ink-400">앞뒤 조각이 짧으면 자동으로 줄어들어요.</p>
          </label>

          <div>
            <p className="mb-1.5 text-sm">넣을 위치</p>
            <div className="grid grid-cols-2 gap-1 rounded-lg border border-ink-700 bg-ink-850 p-0.5 text-xs font-medium">
              {[['long_cuts', '오래 잘린 곳만'], ['all', '모든 컷']].map(([v, label]) => (
                <button
                  key={v}
                  className={`rounded-md py-1.5 transition ${settings.apply === v ? 'bg-ink-700 text-ink-100' : 'text-ink-400 hover:text-ink-100'}`}
                  onClick={() => set('apply')(v)}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          {settings.apply === 'long_cuts' && (
            <label className="block">
              <div className="mb-1.5 flex justify-between text-sm">
                <span>이만큼 이상 잘린 곳</span><span className="font-mono text-xs text-accent">{settings.min_cut.toFixed(1)}초</span>
              </div>
              <input type="range" min={0.5} max={10} step={0.5} value={settings.min_cut} onChange={(e) => set('min_cut')(Number(e.target.value))} />
            </label>
          )}
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between rounded-lg bg-ink-850 px-3 py-2 text-xs">
        <span className="text-ink-300">
          적용 <b className="font-mono text-accent">{active}</b> / 컷 {cuts}곳
          {overrideCount > 0 && <span className="text-ink-400"> · 개별 설정 {overrideCount}</span>}
        </span>
        {overrideCount > 0 && (
          <button className="flex items-center gap-1 text-ink-400 hover:text-ink-100" onClick={() => set('overrides')({})}>
            <Undo2 className="size-3.5" /> 개별 설정 초기화
          </button>
        )}
      </div>
    </div>
  )
}
