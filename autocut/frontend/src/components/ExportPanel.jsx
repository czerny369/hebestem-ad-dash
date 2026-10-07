import { useEffect, useState } from 'react'
import { CheckCircle2, Download, Loader2, Send } from 'lucide-react'
import { api } from '../api.js'

export default function ExportPanel({ project, config, subtitles, style, onError, onDone }) {
  const stem = project.video_name.replace(/\.[^.]+$/, '')
  const [name, setName] = useState(project.draft?.name ?? `${stem}_autocut`)
  const [dir, setDir] = useState('')
  const [replace, setReplace] = useState(!!project.draft)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)

  useEffect(() => {
    let saved = null
    try { saved = localStorage.getItem('autocut.draftsDir') } catch { /* noop */ }
    setDir(saved || config?.drafts_dir || '')
  }, [config])

  const create = async () => {
    setBusy(true)
    setResult(null)
    onError(null)
    try {
      const res = await api.draft(project.id, { name: name.trim(), drafts_dir: dir.trim(), replace, subtitles, style: { ...style, font: style.font || null } })
      try { localStorage.setItem('autocut.draftsDir', dir.trim()) } catch { /* noop */ }
      setResult(res.path)
      setReplace(true)
      onDone?.()
    } catch (e) {
      onError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const downloadSrt = async () => {
    try {
      const text = await api.srt(project.id, subtitles)
      const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }))
      const a = Object.assign(document.createElement('a'), { href: url, download: `${name || stem}.srt` })
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      onError(e.message)
    }
  }

  return (
    <div className="card p-4">
      <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
        <Send className="size-4 text-accent" /> CapCut으로 내보내기
      </h2>

      <label className="block">
        <span className="mb-1.5 block text-sm">프로젝트 이름</span>
        <input className="field" value={name} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="mt-3 block">
        <span className="mb-1.5 block text-sm">CapCut 드래프트 폴더</span>
        <input className="field font-mono text-xs" value={dir} onChange={(e) => setDir(e.target.value)} placeholder="…/CapCut/User Data/Projects/com.lveditor.draft" />
        <p className="mt-1 text-xs text-ink-400">
          {config?.drafts_dir ? '자동으로 찾았어요.' : '자동으로 찾지 못했어요.'} CapCut → 설정 → 드래프트 위치에서 확인할 수 있어요.
        </p>
      </label>
      <label className="mt-3 flex items-center gap-2 text-sm">
        <input type="checkbox" className="size-4 accent-accent" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
        같은 이름이 있으면 덮어쓰기
      </label>

      <button className="btn-primary mt-4 w-full py-2.5" disabled={busy || !name.trim() || !dir.trim() || !subtitles.length} onClick={create}>
        {busy ? <Loader2 className="size-4 animate-spin" /> : <Send className="size-4" />}
        CapCut 드래프트 만들기
      </button>
      <button className="btn-ghost mt-2 w-full" onClick={downloadSrt}>
        <Download className="size-4" /> 자막 SRT 받기
      </button>

      {result && (
        <div className="mt-3 rounded-xl border border-keep/40 bg-keep/10 p-3 text-sm">
          <p className="flex items-center gap-2 font-medium text-emerald-300"><CheckCircle2 className="size-4" /> 드래프트를 만들었어요</p>
          <p className="mt-1 text-xs text-ink-300">CapCut 홈 화면에 <b className="text-ink-100">{name}</b> 프로젝트가 보여요. 안 보이면 CapCut을 다시 켜 주세요.</p>
          <p className="mt-2 break-all font-mono text-[11px] text-ink-400">{result}</p>
        </div>
      )}
    </div>
  )
}
