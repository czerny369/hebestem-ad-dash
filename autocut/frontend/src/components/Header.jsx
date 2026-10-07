import { Clapperboard, X } from 'lucide-react'
import { fmt } from '../timeline.js'

export default function Header({ project, onClose }) {
  return (
    <header className="sticky top-0 z-30 border-b border-ink-800 bg-ink-950/85 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-[1600px] items-center gap-3 px-4 sm:px-6">
        <div className="flex items-center gap-2">
          <span className="grid size-8 place-items-center rounded-lg bg-accent text-ink-950">
            <Clapperboard className="size-4.5" strokeWidth={2.4} />
          </span>
          <span className="text-[15px] font-semibold tracking-tight">AutoCut</span>
          <span className="hidden text-xs text-ink-400 sm:inline">자동 컷편집 · 자막 → CapCut</span>
        </div>

        {project && (
          <div className="ml-auto flex min-w-0 items-center gap-3">
            <div className="min-w-0 text-right">
              <p className="truncate text-sm font-medium">{project.video_name}</p>
              <p className="text-xs text-ink-400">
                {project.info.width}×{project.info.height} · {Math.round(project.info.fps)}fps · {fmt(project.info.duration, false)}
              </p>
            </div>
            <button className="btn-ghost px-2.5" onClick={onClose} title="프로젝트 닫기">
              <X className="size-4" />
            </button>
          </div>
        )}
      </div>
    </header>
  )
}
