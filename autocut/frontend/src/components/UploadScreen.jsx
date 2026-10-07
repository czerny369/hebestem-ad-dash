import { useEffect, useRef, useState } from 'react'
import { Film, FolderOpen, Trash2, UploadCloud } from 'lucide-react'
import { api } from '../api.js'

export default function UploadScreen({ onUploaded, onOpen, error, setError, serverOk }) {
  const [drag, setDrag] = useState(false)
  const [progress, setProgress] = useState(null)
  const [projects, setProjects] = useState([])
  const inputRef = useRef(null)

  const refresh = () => api.projects().then(setProjects).catch(() => {})
  useEffect(() => {
    if (serverOk) refresh()
  }, [serverOk])

  const upload = async (file) => {
    if (!file) return
    if (!file.type.startsWith('video/') && !/\.(mp4|mov|m4v|mkv|avi|webm)$/i.test(file.name)) {
      setError('영상 파일(mp4, mov 등)을 선택하세요')
      return
    }
    setError(null)
    setProgress(0)
    try {
      const p = await api.upload(file, setProgress)
      setProgress(1)
      onUploaded(p)
    } catch (e) {
      setError(e.message)
      setProgress(null)
    }
  }

  const remove = async (id) => {
    if (!confirm('이 프로젝트를 삭제할까요? 업로드한 영상도 함께 지워지며, 이 영상을 쓰는 CapCut 드래프트는 미디어를 찾지 못하게 됩니다.')) return
    await api.deleteProject(id).catch((e) => setError(e.message))
    refresh()
  }

  const uploading = progress !== null

  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-8 px-4 py-12 sm:px-6 sm:py-16">
      <div className="text-center">
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
          촬영본만 넣으면, <span className="text-accent">편집은 자동으로</span>
        </h1>
        <p className="mx-auto mt-3 max-w-xl text-[15px] leading-relaxed text-ink-300">
          버벅인 부분과 너무 긴 멈춤을 잘라내고, 스크립트에 맞춰 자막을 깔아
          CapCut에서 바로 열 수 있는 프로젝트로 만들어 드려요.
        </p>
      </div>

      <ol className="grid gap-3 text-sm sm:grid-cols-3">
        {[
          ['1', '영상 업로드', '촬영 원본 그대로'],
          ['2', '스크립트 붙여넣기', '한 줄 = 자막 하나'],
          ['3', '확인 후 CapCut으로', '컷·자막 수정 가능'],
        ].map(([n, title, desc]) => (
          <li key={n} className="card flex items-center gap-3 px-4 py-3">
            <span className="grid size-7 shrink-0 place-items-center rounded-full bg-ink-800 text-xs font-semibold text-accent">{n}</span>
            <div>
              <p className="font-medium">{title}</p>
              <p className="text-xs text-ink-400">{desc}</p>
            </div>
          </li>
        ))}
      </ol>

      <div
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => { e.preventDefault(); setDrag(false); upload(e.dataTransfer.files[0]) }}
        onClick={() => !uploading && inputRef.current?.click()}
        className={`card group relative flex cursor-pointer flex-col items-center justify-center gap-3 border-2 border-dashed px-6 py-16 text-center transition
          ${drag ? 'border-accent bg-accent/5' : 'border-ink-700 hover:border-ink-600 hover:bg-ink-850'}
          ${uploading ? 'pointer-events-none' : ''}`}
      >
        <input ref={inputRef} type="file" accept="video/*" hidden onChange={(e) => upload(e.target.files[0])} />
        <span className={`grid size-14 place-items-center rounded-2xl transition ${drag ? 'bg-accent text-ink-950' : 'bg-ink-800 text-accent group-hover:scale-105'}`}>
          <UploadCloud className="size-7" />
        </span>
        {uploading ? (
          <div className="w-full max-w-xs">
            <p className="mb-2 text-sm font-medium">업로드 중… {Math.round(progress * 100)}%</p>
            <div className="h-1.5 overflow-hidden rounded-full bg-ink-800">
              <div className="h-full rounded-full bg-accent transition-[width]" style={{ width: `${progress * 100}%` }} />
            </div>
          </div>
        ) : (
          <>
            <p className="text-base font-medium">영상을 끌어다 놓거나 클릭해서 선택</p>
            <p className="text-sm text-ink-400">MP4 · MOV · MKV 등</p>
          </>
        )}
      </div>

      {error && <p className="rounded-xl border border-cut/40 bg-cut/10 px-4 py-3 text-sm text-rose-200">{error}</p>}

      {projects.length > 0 && (
        <section>
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold text-ink-300">
            <FolderOpen className="size-4" /> 최근 프로젝트
          </h2>
          <ul className="card divide-y divide-ink-800 overflow-hidden">
            {projects.map((p) => (
              <li key={p.id} className="flex items-center gap-3 px-4 py-3 hover:bg-ink-850">
                <Film className="size-4 shrink-0 text-ink-400" />
                <button className="min-w-0 flex-1 truncate text-left text-sm hover:text-accent" onClick={() => onOpen(p.id)}>
                  {p.video_name}
                </button>
                <span className={`rounded-full px-2 py-0.5 text-[11px] ${p.has_plan ? 'bg-keep/15 text-emerald-300' : 'bg-ink-800 text-ink-400'}`}>
                  {p.has_plan ? '분석 완료' : '분석 전'}
                </span>
                <span className="hidden w-28 text-right text-xs text-ink-400 sm:block">
                  {p.created ? new Date(p.created * 1000).toLocaleDateString('ko-KR') : ''}
                </span>
                <button className="text-ink-400 hover:text-cut" onClick={() => remove(p.id)} title="삭제">
                  <Trash2 className="size-4" />
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  )
}
