import { Palette } from 'lucide-react'
import { SubtitleOverlay } from './Player.jsx'

const PRESETS = [
  { name: '기본', color: '#FFFFFF', border: true, border_color: '#000000', bold: false },
  { name: '노랑', color: '#FFE14D', border: true, border_color: '#000000', bold: true },
  { name: '검정', color: '#111111', border: true, border_color: '#FFFFFF', bold: true },
  { name: '테두리 없음', color: '#FFFFFF', border: false, border_color: '#000000', bold: false },
]

function ColorInput({ label, value, onChange, disabled }) {
  return (
    <label className={`flex items-center gap-2 text-sm ${disabled ? 'opacity-40' : ''}`}>
      <span className="relative size-7 overflow-hidden rounded-md border border-ink-600" style={{ background: value }}>
        <input type="color" value={value} disabled={disabled} onChange={(e) => onChange(e.target.value.toUpperCase())} className="absolute inset-0 size-full cursor-pointer opacity-0" />
      </span>
      {label}
    </label>
  )
}

export default function StylePanel({ style, setStyle, fonts, vertical }) {
  const set = (k) => (v) => setStyle((s) => ({ ...s, [k]: v }))
  const position = style.position ?? (vertical ? -0.55 : -0.8)

  return (
    <div className="card p-4">
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <Palette className="size-4 text-accent" /> 자막 스타일
      </h2>

      <div
        className="relative mb-3 overflow-hidden rounded-lg bg-[linear-gradient(135deg,#334155,#0f172a_60%,#1e293b)] [container-type:size]"
        style={{ aspectRatio: vertical ? '9 / 16' : '16 / 9', maxHeight: vertical ? 220 : undefined, marginInline: vertical ? 'auto' : undefined }}
      >
        <SubtitleOverlay text="자막 미리보기 예시입니다" style={style} vertical={vertical} />
      </div>

      <div className="mb-4 flex flex-wrap gap-1.5">
        {PRESETS.map((p) => (
          <button
            key={p.name}
            className="inline-flex items-center rounded-md border border-ink-700 bg-ink-850 py-1 pr-2.5 pl-1 text-xs hover:border-accent/60"
            onClick={() => setStyle((s) => ({ ...s, color: p.color, border: p.border, border_color: p.border_color, bold: p.bold }))}
          >
            <span
              className="mr-1 inline-grid size-5 place-items-center rounded bg-ink-600 text-[13px] font-extrabold"
              style={{ color: p.color, WebkitTextStroke: p.border ? `1px ${p.border_color}` : undefined, paintOrder: 'stroke fill' }}
            >가</span>
            {p.name}
          </button>
        ))}
      </div>

      <div className="space-y-4">
        <label className="block">
          <div className="mb-1.5 flex justify-between text-sm"><span>글자 크기</span><span className="font-mono text-xs text-accent">{style.size}</span></div>
          <input type="range" min={3} max={15} step={0.5} value={style.size} onChange={(e) => set('size')(Number(e.target.value))} />
        </label>
        <label className="block">
          <div className="mb-1.5 flex justify-between text-sm"><span>세로 위치</span><span className="font-mono text-xs text-accent">{position.toFixed(2)}</span></div>
          <input type="range" min={-0.95} max={0.95} step={0.05} value={position} onChange={(e) => set('position')(Number(e.target.value))} />
        </label>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-3">
          <ColorInput label="글자색" value={style.color} onChange={set('color')} />
          <ColorInput label="테두리" value={style.border_color} onChange={set('border_color')} disabled={!style.border} />
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="size-4 accent-accent" checked={style.border} onChange={(e) => set('border')(e.target.checked)} /> 테두리
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" className="size-4 accent-accent" checked={style.bold} onChange={(e) => set('bold')(e.target.checked)} /> 굵게
          </label>
        </div>
        <label className="block">
          <span className="mb-1.5 block text-sm">폰트</span>
          <select className="field" value={style.font} onChange={(e) => set('font')(e.target.value)}>
            <option value="">CapCut 기본 폰트 (한글 지원)</option>
            {fonts.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
          <p className="mt-1 text-xs text-ink-400">pyCapCut 내장 폰트는 대부분 영문용이에요. 한글 폰트는 CapCut에서 자막 전체 선택 후 바꾸는 걸 추천해요.</p>
        </label>
      </div>
    </div>
  )
}
