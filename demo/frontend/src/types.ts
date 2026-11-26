// Kiểu dữ liệu khớp với API backend (crowd_demo/api.py, pipeline.status()).

export type ViewMode = 'video' | 'overlay' | 'overlay_only' | 'gray'
export type RuleName = 'overcrowd' | 'zone_limit' | 'hot_cell' | 'surge' | 'panic' | 'counterflow'
export type Point = [number, number]          // tọa độ chuẩn hóa 0–1
export type Polygon = Point[]

export interface ZoneMeta {
  name: string
  limit: number | null
  direction?: number | null
}

export interface ZoneSet {
  roi: Polygon[]
  exclude: Polygon[]
  roi_meta: ZoneMeta[]
}

export interface SourceInfo {
  label: string
  kind: 'file' | 'youtube'
  live: boolean
  tz: string
  fps: number
  size: [number, number]
  run: string | null
  position_s?: number
  duration_s?: number
  paused?: boolean
}

export interface Thresholds {
  count_limit: number | null
  panic_score: number | null
  counterflow: number
}

export interface AnomalyStatus {
  model: string
  label: string
  kind: 'speed' | 'if' | 'ae'
  umn_auc: number
  norm: 'camera' | 'umn'
  ready: boolean
  learning: boolean
  have: number
  need: number
  score: number | null
  limit: number | null
}

export interface ZoneCount {
  name: string
  count: number
  limit: number | null
  direction: number | null
  wrong_share: number | null
}

export interface Status {
  camera_id: number
  camera: string | null
  state: 'idle' | 'running' | 'error'
  error: string | null
  mode: ViewMode
  model: string
  source: SourceInfo | null
  counts: { total: number; roi: number; excluded: number; max_cell: number }
  motion: { speed: number; direction_deg: number; entropy: number; counterflow: number; active_ratio: number }
  perf: { video_fps: number; analysis_fps: number; analysis_ms: number; delay_ms: number }
  calibration: { done: boolean; have: number; need: number }
  anomaly: AnomalyStatus
  zones: ZoneCount[]
  thresholds: Thresholds
  active_alerts: RuleName[]
  latest_event_id: number
  sample_t: number | null
}

export interface RuleConfig {
  persist_s: number
  cooldown_s: number
  smooth: number
  surge_window_s: number
  surge_abs: number
  surge_rel: number
  panic_persist_s: number
  counterflow_share: number
  count_limit: number | null
  enabled: Record<RuleName, boolean>
}

export interface EventRow {
  id: number
  camera_id: number
  t: number
  source: string
  rule: RuleName
  value: number
  threshold: number
  message: string
  snapshot: string
  clip: string | null
  status: 'new' | 'ack'
  ack_by: string | null
  ack_at: number | null
  note: string | null
  purged: number
  has_sample: number
  verdict: Verdict | null
  verdict_by: string | null
  verdict_at: number | null
}

export type Verdict = 'true' | 'false'
export type VerdictCounts = Record<'none' | Verdict, number>

export interface SeriesRow {
  t: number
  roi: number
  total: number
  anomaly: number | null
  anomaly_limit: number | null
}

export interface CountModelInfo {
  mae_dublin: number | null
  name: string
  label: string
  available: boolean
  has_mask: boolean | null
  mae: number | null
  mse: number | null
}

export interface AnomalyModelInfo {
  name: string
  label: string
  kind: 'speed' | 'if' | 'ae'
  umn_auc: number
  available: boolean
}

export interface AnomalyModels {
  norm_modes: ('camera' | 'umn')[]
  models: AnomalyModelInfo[]
}

export type CameraKind = 'file' | 'youtube'

export interface Camera {
  id: number
  name: string
  kind: CameraKind
  source: string
  tz: string
  autostart: boolean
  config?: Record<string, unknown>
}

/** Một dòng trong danh sách camera (GET /api/cameras). */
export interface CameraSummary extends Camera {
  running: boolean
  state: 'stopped' | 'idle' | 'running' | 'error'
  error: string | null
  roi: number | null
  active_alerts: RuleName[]
  analysis_fps: number | null
  model: string
  anomaly_model: string
}

export interface LiveMessage {
  cameras: Record<string, Status>
  unacked: number
  max_cameras: number
}

export interface Me {
  name: string
  role: 'admin' | 'viewer'
}

export interface EventPage {
  rows: EventRow[]
  total: number
  verdicts: VerdictCounts
}

export interface StatsResponse {
  tz: string
  bucket: number
  summary: { roi_avg: number | null; roi_max: number | null; roi_max_t: number | null; events: Record<string, number>; acked: number }
  series: { t: number; roi_avg: number; roi_max: number; anomaly_max: number | null; n: number }[]
  heatmap: { weekday: number; hour: number; roi_avg: number }[]
  events_by_day: { day: string; rule: RuleName; n: number }[]
}

export interface AuditRow {
  id: number
  t: number
  user: string
  action: string
  detail: string
}
