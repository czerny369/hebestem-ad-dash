// 원본 시간 <-> 편집본 시간 변환 (keep = [[start, end], ...], 원본 기준)

export function buildMap(keep, speeds) {
  const sp = speeds && speeds.length === keep.length ? speeds : keep.map(() => 1)
  const offsets = []
  let acc = 0
  keep.forEach(([s, e], i) => {
    offsets.push(acc)
    acc += (e - s) / sp[i]
  })
  return { keep, speeds: sp, offsets, total: acc }
}

/** 원본 → 편집본. 잘린 구간은 다음 유지 구간 시작으로 붙는다. */
export function toEdited(map, t) {
  const { keep, offsets, speeds } = map
  for (let i = keep.length - 1; i >= 0; i--) {
    const [s, e] = keep[i]
    if (t >= s) return offsets[i] + (Math.min(t, e) - s) / speeds[i]
  }
  return 0
}

/** 편집본 → 원본 */
export function toOriginal(map, t) {
  const { keep, offsets, speeds } = map
  for (let i = 0; i < keep.length; i++) {
    const [s, e] = keep[i]
    if (t <= offsets[i] + (e - s) / speeds[i]) return s + Math.max(0, t - offsets[i]) * speeds[i]
  }
  return keep.length ? keep[keep.length - 1][1] : 0
}

/** 서버의 keep_from_pieces 와 같음: 남길 조각 → keep/speeds (붙어 있고 속도가 같으면 합침) */
export function piecesToKeep(pieces) {
  const keep = []
  const speeds = []
  for (const p of [...pieces].sort((a, b) => a.start - b.start)) {
    if (!p.keep || p.end - p.start <= 1e-6) continue
    const last = keep.length - 1
    if (last >= 0 && Math.abs(keep[last][1] - p.start) < 1e-6 && Math.abs(speeds[last] - p.speed) < 1e-6) {
      keep[last] = [keep[last][0], p.end]
    } else {
      keep.push([p.start, p.end])
      speeds.push(p.speed ?? 1)
    }
  }
  return { keep, speeds }
}

/** 현재 재생 위치(원본)가 속한 유지 구간 번호 (-1 = 잘린 곳) */
export function keepIndexAt(keep, t) {
  return keep.findIndex(([s, e]) => t >= s && t < e)
}

export const PIECE_REASONS = {
  ng: 'NG (다시 찍은 동작)',
  long: '긴 동작',
  stutter: '버벅임',
  pause: '긴 멈춤',
  idle: '정지 화면',
  action: '동작',
  cut: '잘림',
}

/** 원본 시간 t 가 유지 구간 밖이면 다음 유지 구간 시작(없으면 null) */
export function nextKeepStart(keep, t) {
  for (const [s, e] of keep) {
    if (t < s) return s
    if (t < e) return t
  }
  return null
}

export function fmt(t, withMs = true) {
  if (t == null || Number.isNaN(t)) return '--:--'
  const m = Math.floor(t / 60)
  const s = t - m * 60
  return withMs ? `${String(m).padStart(2, '0')}:${s.toFixed(1).padStart(4, '0')}` : `${m}:${String(Math.floor(s)).padStart(2, '0')}`
}

// 서버의 transitions.resolve 와 같은 규칙: 컷 경계 i (keep[i] 와 keep[i+1] 사이) 마다 {type, duration} 또는 null
export const MIN_TRANSITION = 0.1

export function resolveTransitions(keep, settings, speeds) {
  const sp = speeds && speeds.length === keep.length ? speeds : keep.map(() => 1)
  const out = []
  for (let i = 0; i < keep.length - 1; i++) {
    const override = settings.overrides?.[i]
    let type
    if (override === 'none') { out.push(null); continue }
    if (override) type = override
    else if (!settings.enabled) { out.push(null); continue }
    else {
      const removed = keep[i + 1][0] - keep[i][1]
      if (settings.apply === 'long_cuts' && removed < settings.min_cut) { out.push(null); continue }
      type = settings.type
    }
    const limit = Math.min((keep[i][1] - keep[i][0]) / sp[i], (keep[i + 1][1] - keep[i + 1][0]) / sp[i + 1]) / 2
    const duration = Math.min(settings.duration, limit)
    out.push(duration >= MIN_TRANSITION ? { type, duration, overridden: !!override } : null)
  }
  return out
}

/** 컷 i 에 전환을 켜고/끄는 개별 설정 (기본 규칙과 같아지면 개별 설정을 지운다) */
export function toggleTransitionAt(keep, settings, i, speeds) {
  const current = resolveTransitions(keep, settings, speeds)[i]
  const overrides = { ...settings.overrides }
  delete overrides[i]
  const base = resolveTransitions(keep, { ...settings, overrides }, speeds)[i]
  const wantOn = !current
  if (!!base !== wantOn) overrides[i] = wantOn ? settings.type : 'none'
  return { ...settings, overrides }
}
