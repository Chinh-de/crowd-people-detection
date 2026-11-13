// Kiểu dữ liệu khớp với API backend (crowd_demo/api.py, pipeline.status()).

export type ViewMode = 'video' | 'overlay' | 'overlay_only' | 'gray'
export type RuleName = 'overcrowd' | 'hot_cell' | 'surge' | 'panic' | 'counterflow'
export type Point = [number, number]          // tọa độ chuẩn hóa 0–1
export type Polygon = Point[]

export interface ZoneSet {
  roi: Polygon[]
  exclude: Polygon[]
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
  overcrowd: number | null
  hot_cell: number | null
  panic_speed: number | null
  panic_entropy: number | null
  counterflow: number | null
}

export interface Status {
  state: 'idle' | 'running' | 'error'
  error: string | null
  mode: ViewMode
  model: string
  source: SourceInfo | null
  counts: { total: number; roi: number; excluded: number; max_cell: number; hot_cells: number }
  motion: { speed: number; direction_deg: number; entropy: number; counterflow: number; active_ratio: number }
  perf: { video_fps: number; analysis_fps: number; analysis_ms: number }
  calibration: { done: boolean; have: number; need: number }
  thresholds: Thresholds
  active_alerts: RuleName[]
  latest_event_id: number
  sample_t: number | null
}

export interface RuleConfig {
  k_sigma: number
  persist_s: number
  cooldown_s: number
  smooth: number
  count_margin_abs: number
  count_margin_rel: number
  surge_window_s: number
  surge_abs: number
  surge_rel: number
  cell_factor: number
  min_cell_limit: number
  panic_k: number
  counterflow_k: number
  min_counterflow: number
  baseline_window_s: number
  count_limit: number | null
  enabled: Record<RuleName, boolean>
}

export interface EventRow {
  id: number
  t: number
  source: string
  rule: RuleName
  value: number
  threshold: number
  message: string
  snapshot: string
  clip: string | null
}

export interface SeriesRow {
  t: number
  roi: number
  total: number
  speed: number
  entropy: number
  counterflow: number
}

export interface ModelInfo {
  name: string
  label: string
  active: boolean
  available: boolean
  has_mask: boolean | null
}
