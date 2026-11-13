import type { RuleName } from './types'

export const RULE_LABELS: Record<RuleName, string> = {
  overcrowd: 'Quá đông',
  hot_cell: 'Ô quá dày',
  surge: 'Tăng đột ngột',
  panic: 'Hỗn loạn',
  counterflow: 'Ngược chiều',
}

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

export const num = (v: number | null | undefined, digits = 0) => (v == null ? '–' : v.toFixed(digits))
