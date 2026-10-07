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
  const rows = scriptText.split('\n').map((l) => l.trim()).filter((l) => l && !l.startsWith('#'))
  const isAction = (l) => /^[\[［【(（].*[\]］】)）]$/.test(l)
  const lines = rows.filter((l) => !isAction(l)).length
  const actions = rows.filter(isAction).length + rows.filter((l) => !isAction(l) && /\[[^\]]+\]\s*$/.test(l)).length
  const visual = options.mode === 'visual'
  const voice = options.mode === 'voice'
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
        placeholder={'한 줄에 자막 하나씩, 그 아래 [동작 설명]을 적으세요.\n\n안녕하세요 여러분\n[카메라를 보며 손을 흔든다]\n오늘은 이 제품을 소개해 드릴게요\n[제품을 들어 보여준다]\n…'}
        className="field resize-y font-sans leading-relaxed"
      />
      <p className="mt-1.5 text-xs text-ink-400">
        자막 {lines}줄{actions > 0 && <> · <span className="text-amber-300/90">동작 설명 {actions}개</span></>}
        {' · '}[대괄호] 줄은 자막이 아니라 바로 위 자막의 장면 설명이에요. 음성이 없는 영상은 이 설명으로 장면을 찾아 자막을 맞춰요.
      </p>

      <div className="mt-4">
        <p className="mb-1.5 text-sm">편집 기준</p>
        <div className="grid grid-cols-3 gap-1 rounded-lg border border-ink-700 bg-ink-850 p-0.5 text-xs font-medium">
          {[['auto', '자동'], ['voice', '음성'], ['visual', '화면']].map(([v, label]) => (
            <button
              key={v}
              className={`rounded-md py-1.5 transition ${options.mode === v ? 'bg-ink-700 text-ink-100' : 'text-ink-400 hover:text-ink-100'}`}
              onClick={() => set('mode')(v)}
            >
              {label}
            </button>
          ))}
        </div>
        <p className="mt-1 text-xs text-ink-400">
          {options.mode === 'auto' && '영상에 소리가 있으면 음성, 없으면 화면을 기준으로 자동 선택해요.'}
          {voice && '말소리를 받아 적어 버벅임·긴 멈춤을 자르고 말하는 타이밍에 자막을 맞춰요.'}
          {visual && '음성이 없는 영상용. 화면 움직임으로 긴 동작·NG를 자르고 [동작 설명]에 맞는 장면에 자막을 붙여요.'}
        </p>
      </div>

      {!voice && (
        <div className="mt-4 space-y-4 rounded-xl border border-ink-800 bg-ink-850/40 p-3">
          <p className="text-xs font-semibold text-ink-300">화면 기준 (음성 없는 영상)</p>
          <Slider
            label="긴 동작 기준"
            hint="한 장면이 이보다 길면 줄여요"
            value={options.max_action} min={2} max={20} step={0.5}
            onChange={set('max_action')}
          />
          <div>
            <p className="mb-1.5 text-sm">긴 동작 줄이는 방법</p>
            <div className="grid grid-cols-2 gap-1 rounded-lg border border-ink-700 bg-ink-850 p-0.5 text-xs font-medium">
              {[['speed', '빨리감기'], ['trim', '중간 자르기']].map(([v, label]) => (
                <button
                  key={v}
                  className={`rounded-md py-1.5 transition ${options.long_mode === v ? 'bg-ink-700 text-ink-100' : 'text-ink-400 hover:text-ink-100'}`}
                  onClick={() => set('long_mode')(v)}
                >
                  {label}
                </button>
              ))}
            </div>
            <p className="mt-1 text-xs text-ink-400">
              {options.long_mode === 'speed' ? '기준 길이에 맞게 최대 4배까지 빠르게 재생해요.' : '앞뒤만 남기고 가운데를 잘라요.'}
            </p>
          </div>
          <label className="flex items-start gap-2.5 text-sm">
            <input type="checkbox" className="mt-0.5 size-4 accent-accent" checked={options.remove_ng} onChange={(e) => set('remove_ng')(e.target.checked)} />
            <span>
              NG 동작 자동 제거
              <span className="block text-xs text-ink-400">같은 [동작]을 여러 번 찍었으면 마지막 것만 남겨요. 잘못 잘렸으면 타임라인에서 클릭해 되살리세요.</span>
            </span>
          </label>
        </div>
      )}

      <div className={`mt-4 space-y-4 ${visual ? 'hidden' : ''}`}>
        {!voice && <p className="text-xs font-semibold text-ink-300">음성 기준</p>}
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
      </div>

      <div className="mt-4">
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
