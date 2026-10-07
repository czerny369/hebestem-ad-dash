import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api } from './api.js'
import { buildMap, resolveTransitions, toggleTransitionAt } from './timeline.js'
import Header from './components/Header.jsx'
import UploadScreen from './components/UploadScreen.jsx'
import ScriptPanel from './components/ScriptPanel.jsx'
import Player from './components/Player.jsx'
import Timeline from './components/Timeline.jsx'
import SubtitleList from './components/SubtitleList.jsx'
import StylePanel from './components/StylePanel.jsx'
import ExportPanel from './components/ExportPanel.jsx'
import Stats from './components/Stats.jsx'
import TransitionPanel from './components/TransitionPanel.jsx'

const DEFAULT_OPTIONS = {
  max_chars: 18,
  max_pause: 0.6,
  pause_keep: 0.3,
  keep_threshold: 0.5,
  no_asr: false,
  model: 'small',
}

const DEFAULT_TRANSITION = {
  enabled: false,
  type: '叠化',
  duration: 0.5,
  apply: 'long_cuts',
  min_cut: 2,
  overrides: {},
}

const DEFAULT_STYLE = {
  size: 7,
  color: '#FFFFFF',
  border: true,
  border_color: '#000000',
  bold: false,
  position: null,
  font: '',
}

function projectIdFromHash() {
  const m = window.location.hash.match(/^#\/p\/([0-9a-f]{12})$/)
  return m ? m[1] : null
}

export default function App() {
  const [config, setConfig] = useState(null)
  const [project, setProject] = useState(null)
  const [error, setError] = useState(null)
  const [scriptText, setScriptText] = useState('')
  const [options, setOptions] = useState(DEFAULT_OPTIONS)
  const [style, setStyle] = useState(DEFAULT_STYLE)
  const [transition, setTransition] = useState(DEFAULT_TRANSITION)
  const [transitionCatalog, setTransitionCatalog] = useState(null)
  const [subtitles, setSubtitles] = useState([])
  const [time, setTime] = useState(0) // 원본 기준 재생 위치
  const playerRef = useRef(null)

  const pid = project?.id
  const plan = project?.plan
  const running = project?.status?.state === 'running'

  // ---- 초기 로드 ----
  useEffect(() => {
    api.config().then(setConfig).catch((e) => setError(`서버에 연결할 수 없습니다: ${e.message}`))
    api.transitions().then(setTransitionCatalog).catch(() => {})
  }, [])

  const loadedId = useRef(null) // 중복 로드(해시 변경 이벤트 등)로 최신 상태가 덮이지 않게

  const openProject = useCallback(async (id) => {
    if (loadedId.current === id) return
    loadedId.current = id
    if (window.location.hash !== `#/p/${id}`) window.location.hash = `/p/${id}`
    try {
      const p = await api.project(id)
      if (loadedId.current !== id) return
      setProject(p)
      setScriptText(p.script_text || '')
      if (p.options) setOptions((o) => ({ ...o, ...p.options }))
      setSubtitles(p.plan?.subtitles ?? [])
      setTransition({ ...DEFAULT_TRANSITION, ...(p.transition ?? {}) })
      setTime(0)
    } catch (e) {
      loadedId.current = null
      setError(e.message)
      window.location.hash = ''
    }
  }, [])

  useEffect(() => {
    const sync = () => {
      const id = projectIdFromHash()
      if (id) openProject(id)
      else {
        loadedId.current = null
        setProject(null)
      }
    }
    sync()
    window.addEventListener('hashchange', sync)
    return () => window.removeEventListener('hashchange', sync)
  }, [openProject])

  // ---- 분석 중이면 상태 폴링 ----
  useEffect(() => {
    if (!running) return
    const timer = setInterval(async () => {
      try {
        const p = await api.project(pid)
        setProject(p)
        if (p.status.state === 'done') {
          setSubtitles(p.plan?.subtitles ?? [])
          // 컷 위치가 바뀌었으니 컷별 개별 설정은 초기화
          setTransition((t) => ({ ...t, overrides: {} }))
        }
        if (p.status.state === 'error') setError(p.status.error)
      } catch (e) {
        setError(e.message)
      }
    }, 1000)
    return () => clearInterval(timer)
  }, [running, pid])

  const runAnalyze = async () => {
    setError(null)
    try {
      setProject(await api.analyze(pid, { ...options, script_text: scriptText }))
    } catch (e) {
      setError(e.message)
    }
  }

  const map = useMemo(() => (plan ? buildMap(plan.keep) : null), [plan])
  const resolvedTransitions = useMemo(() => (plan ? resolveTransitions(plan.keep, transition) : []), [plan, transition])
  const info = project?.info
  const vertical = info ? info.height > info.width : false

  if (!project) {
    return (
      <div className="min-h-full">
        <Header />
        <UploadScreen
          onUploaded={(p) => openProject(p.id)}
          onOpen={openProject}
          error={error}
          setError={setError}
          serverOk={!!config}
        />
      </div>
    )
  }

  return (
    <div className="min-h-full">
      <Header project={project} onClose={() => (window.location.hash = '')} />

      {error && (
        <div className="mx-auto mt-4 max-w-[1600px] px-4 sm:px-6">
          <div className="flex items-start justify-between gap-4 rounded-xl border border-cut/40 bg-cut/10 px-4 py-3 text-sm text-rose-200">
            <span className="whitespace-pre-wrap">{error}</span>
            <button className="text-rose-300 hover:text-white" onClick={() => setError(null)}>닫기</button>
          </div>
        </div>
      )}

      <main className="mx-auto grid max-w-[1600px] gap-5 px-4 py-5 sm:px-6 lg:grid-cols-[minmax(0,1fr)_380px]">
        <section className="flex min-w-0 flex-col gap-5">
          <Player
            ref={playerRef}
            src={api.videoUrl(pid)}
            info={info}
            plan={plan}
            map={map}
            subtitles={subtitles}
            style={style}
            transitions={resolvedTransitions}
            transitionCatalog={transitionCatalog}
            vertical={vertical}
            onTime={setTime}
          />
          {plan && map ? (
            <>
              <Stats info={info} plan={plan} subtitles={subtitles} />
              <Timeline
                duration={info.duration}
                plan={plan}
                map={map}
                subtitles={subtitles}
                time={time}
                onSeek={(t) => playerRef.current?.seekOriginal(t)}
                transitions={resolvedTransitions}
                transitionCatalog={transitionCatalog}
                onToggleTransition={(i) => setTransition((s) => toggleTransitionAt(plan.keep, s, i))}
              />
              <SubtitleList
                subtitles={subtitles}
                setSubtitles={setSubtitles}
                map={map}
                time={time}
                onSeekEdited={(t) => playerRef.current?.seekEdited(t)}
              />
            </>
          ) : (
            <EmptyResult running={running} />
          )}
        </section>

        <aside className="flex flex-col gap-5 lg:sticky lg:top-[76px] lg:max-h-[calc(100vh-92px)] lg:overflow-y-auto lg:pb-2 [scrollbar-width:thin]">
          <ScriptPanel
            scriptText={scriptText}
            setScriptText={setScriptText}
            options={options}
            setOptions={setOptions}
            models={config?.models ?? []}
            status={project.status}
            hasPlan={!!plan}
            onAnalyze={runAnalyze}
          />
          {plan && (
            <>
              <StylePanel style={style} setStyle={setStyle} fonts={config?.fonts ?? []} vertical={vertical} />
              <TransitionPanel
                settings={transition}
                setSettings={setTransition}
                catalog={transitionCatalog}
                resolved={resolvedTransitions}
                keep={plan.keep}
              />
              <ExportPanel
                project={project}
                config={config}
                subtitles={subtitles}
                style={style}
                transition={transition}
                transitionCount={resolvedTransitions.filter(Boolean).length}
                onError={setError}
                onDone={() => api.project(pid).then(setProject)}
              />
            </>
          )}
        </aside>
      </main>
    </div>
  )
}

function EmptyResult({ running }) {
  return (
    <div className="card flex flex-col items-center justify-center gap-2 px-6 py-14 text-center">
      <p className="text-base font-medium text-ink-100">
        {running ? '분석 중입니다…' : '스크립트를 넣고 분석을 시작하세요'}
      </p>
      <p className="max-w-md text-sm text-ink-400">
        {running
          ? '음성 인식은 영상 길이와 모델 크기에 따라 몇 분 걸릴 수 있어요. 처음 실행할 때는 모델도 내려받습니다.'
          : '오른쪽에 자막 스크립트를 붙여넣고 [분석 시작]을 누르면, 잘라낼 부분과 자막 타이밍이 여기에 표시됩니다.'}
      </p>
    </div>
  )
}
