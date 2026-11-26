import type { AnomalyStatus, RuleName } from './types'

/** Nhãn mọi loại cảnh báo. Hai loại "(cũ)" đã bỏ, chỉ còn để xem lịch sử. */
export const RULE_LABELS: Record<RuleName, string> = {
  panic: 'Bất thường chuyển động',
  zone_limit: 'Vượt sức chứa',
  surge: 'Tăng đột ngột',
  counterflow: 'Đi ngược chiều',
  overcrowd: 'Quá đông (cũ)',
  hot_cell: 'Ô quá dày (cũ)',
}

/** Trạng thái phát hiện bất thường bằng chữ, thay cho con số điểm khó hiểu. */
export function anomalyState(a: AnomalyStatus): { key: 'learning' | 'none' | 'normal' | 'abnormal'; label: string } {
  if (a.learning) return { key: 'learning', label: `Đang học ${a.have}/${a.need}` }
  if (a.limit == null || a.score == null) return { key: 'none', label: 'Chưa học' }
  return a.score > a.limit ? { key: 'abnormal', label: 'Bất thường' } : { key: 'normal', label: 'Bình thường' }
}

/** Hướng đi cho phép của vùng, theo hướng nhìn trên màn hình (độ: 0 = sang phải, 90 = xuống). */
export const DIRECTIONS = [
  { value: 0, label: '→ sang phải' }, { value: 45, label: '↘ xuống phải' }, { value: 90, label: '↓ đi xuống' },
  { value: 135, label: '↙ xuống trái' }, { value: 180, label: '← sang trái' }, { value: 225, label: '↖ lên trái' },
  { value: 270, label: '↑ đi lên' }, { value: 315, label: '↗ lên phải' },
]

export const VERDICT_LABELS = { true: 'Đúng', false: 'Báo nhầm' } as const

export const TIMEZONES = [
  { value: 'Europe/Dublin', label: 'Dublin' },
  { value: 'Asia/Tokyo', label: 'Osaka / Tokyo' },
  { value: 'Asia/Ho_Chi_Minh', label: 'Việt Nam' },
  { value: 'UTC', label: 'UTC' },
]

/** Giờ địa phương của camera từ thời điểm UTC (giây). */
export function clock(t: number, tz: string, withDate = false): string {
  return new Intl.DateTimeFormat('vi-VN', {
    timeZone: tz,
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    ...(withDate ? { day: '2-digit', month: '2-digit' } : {}),
    hour12: false,
  }).format(new Date(t * 1000))
}

export function duration(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

/** Số theo kiểu Việt Nam (dấu phẩy thập phân). */
export const num = (v: number | null | undefined, digits = 0) =>
  v == null || !Number.isFinite(v) ? '–' : v.toLocaleString('vi-VN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
