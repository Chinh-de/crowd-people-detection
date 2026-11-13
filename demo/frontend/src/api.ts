// Các lời gọi REST tới backend. Lỗi HTTP được ném thành Error với thông điệp tiếng Việt của server.
import type { EventRow, ModelInfo, RuleConfig, SeriesRow, Status, ViewMode, ZoneSet } from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init)
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    const detail = body?.detail
    throw new Error(typeof detail === 'string' ? detail : `Lỗi ${res.status}`)
  }
  return res.json() as Promise<T>
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const api = {
  listVideos: () => request<string[]>('/api/videos'),
  uploadVideo: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ name: string }>('/api/videos', { method: 'POST', body: form })
  },
  startFile: (path: string, tz: string) => request<Status>('/api/source', json('POST', { kind: 'file', path, tz })),
  startYoutube: (url: string, tz: string) => request<Status>('/api/source', json('POST', { kind: 'youtube', url, tz })),
  stop: () => request<Status>('/api/stop', { method: 'POST' }),
  playback: (action: 'play' | 'pause' | 'seek', value?: number) =>
    request<Status>('/api/playback', json('POST', { action, value })),
  listModels: () => request<ModelInfo[]>('/api/models'),
  setModel: (name: string) => request<ModelInfo[]>('/api/model', json('PUT', { name })),
  setMode: (mode: ViewMode) => request<{ mode: ViewMode }>('/api/view', json('PUT', { mode })),
  getZones: () => request<ZoneSet>('/api/zones'),
  putZones: (zones: ZoneSet) => request<ZoneSet>('/api/zones', json('PUT', zones)),
  getRules: () => request<RuleConfig>('/api/rules'),
  putRules: (rules: Partial<RuleConfig>) => request<RuleConfig>('/api/rules', json('PUT', rules)),
  calibrate: (seconds: number) => request<Status['calibration']>('/api/calibrate', json('POST', { seconds })),
  getSeries: (minutes = 10) => request<SeriesRow[]>(`/api/series?minutes=${minutes}`),
  getEvents: (limit = 50) => request<EventRow[]>(`/api/events?limit=${limit}`),
}
