import { useRef, useState } from 'react'
import { ChevronDown, FileText, Loader2, Sparkles } from 'lucide-react'
import { readTextFile } from '../api.js'

function Slider({ label, hint, value, min, max, step, unit = '초', onChange }) {
  return (
    <label className="block">
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <span className="text-sm text-ink-100">{label}</span>
        <span className="font-mono text-xs text-accent">{value}{unit}</span>
      </div>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
      {hint && <p className="mt-1 text-xs leading-snug text-ink-400">{hint}</p>}
    </label>
  )
}

export default function ScriptPanel({ scriptText, setScriptText, options, setOptions, models, status, hasPlan, onAnalyze }) {
  const [advanced, setAdvanced] = useState(false)
  const fileRef = useRef(null)
  const running = status?.state === 'running'
  const lines = scriptText.split('\n').filter((l) => l.trim() && !l.trim().startsWith('#')).length
  const set = (k) => (v) => setOptions((o) => ({ ...o, [k]: v }))

  const loadFile = async (file) => {
    if (file) setScriptText(await readTextFile(file))
  }

  return (
    <div className="card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-semibold">
          <FileText className="size-4 text-accent" /> 자막 스크립트
        </h2>
        <button className="text-xs text-ink-300 underline-offset-2 hover:text-accent hover:underline" onClick={() => fileRef.current?.click()}>
          파일 불러오기 (.txt/.srt)
        </button>
        <input ref={fileRef} type="file" accept=".txt,.srt,text/plain" hidden onChange={(e) => loadFile(e.target.files[0])} />
      </div>

      <textarea
        value={scriptText}
        onChange={(e) => setScriptText(e.target.value)}
        onDrop={(e) => { e.preventDefault(); loadFile(e.dataTransfer.files[0]) }}
        rows={9}
        placeholder={'한 줄에 자막 하나씩 붙여넣으세요.\n\n안녕하세요 여러분\n오늘은 제품을 소개해 드릴게요\n…'}
        className="field resize-y font-sans leading-relaxed"
      />
      <p className="mt-1.5 text-xs text-ink-400">
        {lines}줄 · 스크립트에 없는 말(버벅임·반복·군말)은 잘려요. 살릴 애드리브는 스크립트에도 적어 주세요.
      </p>

      <div className="mt-4 space-y-4">
        <Slider
          label="긴 멈춤 기준"
          hint="이보다 오래 말이 없으면(멈춤·긴 동작) 잘라냅니다. 동작을 살리려면 크게."
          value={options.max_pause} min={0.2} max={5} step={0.1}
          onChange={set('max_pause')}
        />
        <Slider
          label="자른 자리 여유"
          hint="잘라낸 곳에 남겨둘 숨 쉴 틈"
          value={options.pause_keep} min={0} max={1} step={0.05}
          onChange={set('pause_keep')}
        />
        <Slider
          label="자막 한 줄 최대 글자"
          hint="넘으면 문장부호·띄어쓰기 기준으로 나눕니다 (0 = 나누지 않음)"
          value={options.max_chars} min={0} max={40} step={1} unit="자"
          onChange={set('max_chars')}
        />
      </div>

      <button
        className="mt-4 flex w-full items-center justify-between text-xs font-medium text-ink-300 hover:text-ink-100"
        onClick={() => setAdvanced((a) => !a)}
      >
        고급 설정
        <ChevronDown className={`size-4 transition ${advanced ? 'rotate-180' : ''}`} />
      </button>
      {advanced && (
        <div className="mt-3 space-y-4 rounded-xl border border-ink-800 bg-ink-850/60 p-3">
          <label className="block">
            <span className="mb-1.5 block text-sm">음성 인식 모델</span>
            <select className="field" value={options.model} onChange={(e) => set('model')(e.target.value)} disabled={options.no_asr}>
              {models.map((m) => <option key={m} value={m}>{m}{m === 'small' ? ' (기본)' : ''}</option>)}
            </select>
            <p className="mt-1 text-xs text-ink-400">클수록 정확하지만 느립니다. medium 이상은 GPU 권장.</p>
          </label>
          <Slider
            label="단어 일치 기준"
            hint="낮추면 인식이 틀린 단어도 더 살립니다"
            value={options.keep_threshold} min={0.2} max={0.9} step={0.05} unit=""
            onChange={set('keep_threshold')}
          />
          <label className="flex items-start gap-2.5 text-sm">
            <input type="checkbox" className="mt-0.5 size-4 accent-accent" checked={options.no_asr} onChange={(e) => set('no_asr')(e.target.checked)} />
            <span>
              음성 인식 없이 (무음 감지만)
              <span className="block text-xs text-ink-400">빠르지만 버벅임은 못 자르고, 자막은 글자 수 비율로 배치돼요.</span>
            </span>
          </label>
        </div>
      )}

      <button className="btn-primary mt-4 w-full py-2.5" disabled={running || !lines} onClick={onAnalyze}>
        {running ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}
        {running ? status.step || '분석 중…' : hasPlan ? '다시 분석' : '분석 시작'}
      </button>
      {hasPlan && !running && (
        <p className="mt-2 text-center text-xs text-ink-400">음성 인식 결과는 저장돼 있어서 다시 분석은 빨라요.</p>
      )}
    </div>
  )
}
