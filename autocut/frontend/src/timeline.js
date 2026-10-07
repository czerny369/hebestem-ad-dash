// 원본 시간 <-> 편집본 시간 변환 (keep = [[start, end], ...], 원본 기준)

export function buildMap(keep) {
  const offsets = []
  let acc = 0
  for (const [s, e] of keep) {
    offsets.push(acc)
    acc += e - s
  }
  return { keep, offsets, total: acc }
}

/** 원본 → 편집본. 잘린 구간은 다음 유지 구간 시작으로 붙는다. */
export function toEdited(map, t) {
  const { keep, offsets } = map
  for (let i = keep.length - 1; i >= 0; i--) {
    const [s, e] = keep[i]
    if (t >= s) return offsets[i] + Math.min(t, e) - s
  }
  return 0
}

/** 편집본 → 원본 */
export function toOriginal(map, t) {
  const { keep, offsets } = map
  for (let i = 0; i < keep.length; i++) {
    const [s, e] = keep[i]
    if (t <= offsets[i] + (e - s)) return s + Math.max(0, t - offsets[i])
  }
  return keep.length ? keep[keep.length - 1][1] : 0
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
