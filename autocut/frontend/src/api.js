async function request(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: options.body && !(options.body instanceof FormData)
      ? { 'Content-Type': 'application/json', ...options.headers }
      : options.headers,
  })
  const text = await res.text()
  const data = text ? (() => { try { return JSON.parse(text) } catch { return text } })() : null
  if (!res.ok) {
    const detail = data?.detail
    const msg = Array.isArray(detail) ? detail.map((d) => d.msg).join(', ') : detail || res.statusText
    throw new Error(msg)
  }
  return data
}

export const api = {
  config: () => request('/api/config'),
  transitions: () => request('/api/transitions'),
  projects: () => request('/api/projects'),
  project: (id) => request(`/api/projects/${id}`),
  deleteProject: (id) => request(`/api/projects/${id}`, { method: 'DELETE' }),
  analyze: (id, body) => request(`/api/projects/${id}/analyze`, { method: 'POST', body: JSON.stringify(body) }),
  draft: (id, body) => request(`/api/projects/${id}/draft`, { method: 'POST', body: JSON.stringify(body) }),
  srt: (id, subtitles) => request(`/api/projects/${id}/srt`, { method: 'POST', body: JSON.stringify(subtitles) }),
  videoUrl: (id) => `/api/projects/${id}/video`,

  /** 업로드 진행률을 받기 위해 XHR 사용 */
  upload(file, onProgress) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      const form = new FormData()
      form.append('video', file)
      xhr.open('POST', '/api/projects')
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total)
      xhr.onload = () => {
        let data = null
        try { data = JSON.parse(xhr.responseText) } catch { /* noop */ }
        if (xhr.status >= 200 && xhr.status < 300) resolve(data)
        else reject(new Error(data?.detail || `업로드 실패 (${xhr.status})`))
      }
      xhr.onerror = () => reject(new Error('서버에 연결할 수 없습니다'))
      xhr.send(form)
    })
  },
}

/** UTF-8 이 아니면 CP949(EUC-KR) 로 다시 읽는다 — 윈도우 메모장 파일 대응 */
export async function readTextFile(file) {
  const buf = await file.arrayBuffer()
  try {
    return new TextDecoder('utf-8', { fatal: true }).decode(buf).replace(/^﻿/, '')
  } catch {
    return new TextDecoder('euc-kr').decode(buf)
  }
}
