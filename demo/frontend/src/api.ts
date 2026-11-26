// Các lời gọi REST tới backend. Lỗi HTTP được ném thành Error với thông điệp tiếng Việt của server.
// Phiên hết hạn (401) phát sự kiện 'crowd:unauthorized' để ứng dụng quay về trang đăng nhập.
import type { Verdict,
  AnomalyModels, AuditRow, Camera, CameraSummary, CountModelInfo, EventPage, EventRow, Me, RuleConfig, SeriesRow,
  StatsResponse, Status, ViewMode, ZoneSet,
} from './types'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, { credentials: 'same-origin', ...init })
  if (res.status === 401 && path !== '/api/login') window.dispatchEvent(new Event('crowd:unauthorized'))
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

const cam = (id: number) => `/api/cameras/${id}`

export type EventFilter = { camera_id?: number; rule?: string; status?: string; verdict?: string; t0?: number; t1?: number }

const qs = (o: Record<string, string | number | undefined | null>) =>
  new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => [k, String(v)])).toString()

export const api = {
  // đăng nhập
  login: (username: string, password: string) => request<Me>('/api/login', json('POST', { username, password })),
  logout: () => request<{ ok: boolean }>('/api/logout', { method: 'POST' }),
  me: () => request<Me>('/api/me'),
  system: () => request<{ max_cameras: number; running: number; unacked: number; cpu_count: number; clip_days: number }>('/api/system'),

  // model và video
  listModels: () => request<CountModelInfo[]>('/api/models'),
  listAnomalyModels: () => request<AnomalyModels>('/api/anomaly-models'),
  listVideos: () => request<string[]>('/api/videos'),
  uploadVideo: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<{ name: string }>('/api/videos', { method: 'POST', body: form })
  },

  // camera
  listCameras: () => request<CameraSummary[]>('/api/cameras'),
  createCamera: (c: Omit<Camera, 'id' | 'config'>) => request<Camera>('/api/cameras', json('POST', c)),
  updateCamera: (id: number, c: Partial<Camera>) => request<Camera>(cam(id), json('PUT', c)),
  deleteCamera: (id: number) => request<{ ok: boolean }>(cam(id), { method: 'DELETE' }),
  startCamera: (id: number) => request<Status>(`${cam(id)}/start`, { method: 'POST' }),
  stopCamera: (id: number) => request<{ ok: boolean }>(`${cam(id)}/stop`, { method: 'POST' }),
  streamUrl: (id: number, run: string | null) => `${cam(id)}/stream.mjpg?run=${run ?? ''}`,
  snapshotUrl: (id: number, tick: number) => `${cam(id)}/snapshot.jpg?t=${tick}`,
  playback: (id: number, action: 'play' | 'pause' | 'seek', value?: number) =>
    request<Status>(`${cam(id)}/playback`, json('POST', { action, value })),
  setMode: (id: number, mode: ViewMode) => request<{ mode: ViewMode }>(`${cam(id)}/view`, json('PUT', { mode })),
  getZones: (id: number) => request<ZoneSet>(`${cam(id)}/zones`),
  putZones: (id: number, zones: ZoneSet) => request<ZoneSet>(`${cam(id)}/zones`, json('PUT', zones)),
  getRules: (id: number) => request<RuleConfig>(`${cam(id)}/rules`),
  putRules: (id: number, rules: Partial<RuleConfig>) => request<RuleConfig>(`${cam(id)}/rules`, json('PUT', rules)),
  setModel: (id: number, name: string) => request<{ model: string }>(`${cam(id)}/model`, json('PUT', { name })),
  setAnomalyModel: (id: number, name: string, norm?: string) =>
    request<{ model: string; norm: string }>(`${cam(id)}/anomaly-model`, json('PUT', { name, norm })),
  calibrate: (id: number, seconds: number) => request<Status['calibration']>(`${cam(id)}/calibrate`, json('POST', { seconds })),
  getSeries: (id: number, minutes = 10) => request<SeriesRow[]>(`${cam(id)}/series?minutes=${minutes}`),

  // lịch sử, thống kê, nhật ký
  events: (f: EventFilter & { limit?: number; offset?: number } = {}) => request<EventPage>(`/api/events?${qs(f)}`),
  eventsCsvUrl: (f: EventFilter) => `/api/events.csv?${qs(f)}`,
  eventContext: (id: number) => request<{ event: EventRow; series: SeriesRow[] }>(`/api/events/${id}/context`),
  ackEvent: (id: number, note: string) => request<EventRow>(`/api/events/${id}/ack`, json('POST', { note })),
  setVerdict: (id: number, verdict: Verdict | null, note: string) =>
    request<EventRow>(`/api/events/${id}/verdict`, json('POST', { verdict, note })),
  sampleUrl: (id: number, name: 'preview.jpg' | 'frame.jpg' | 'mask.png') => `/api/events/${id}/sample/${name}`,
  toLabeling: (id: number) => request<{ image: string }>(`/api/events/${id}/to-labeling`, { method: 'POST' }),
  feedbackExportUrl: '/api/feedback/export',
  stats: (t0: number, t1: number, camera_id?: number) => request<StatsResponse>(`/api/stats?${qs({ t0, t1, camera_id })}`),
  audit: (limit = 100, offset = 0) => request<AuditRow[]>(`/api/audit?limit=${limit}&offset=${offset}`),
}
