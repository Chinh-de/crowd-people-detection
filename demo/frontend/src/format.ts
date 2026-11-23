import type { RuleName } from './types'

export const RULE_LABELS: Record<RuleName, string> = {
  overcrowd: 'Quá đông',
  zone_limit: 'Vượt sức chứa vùng',
  hot_cell: 'Ô quá dày',
  surge: 'Tăng đột ngột',
  panic: 'Bất thường chuyển động',
  counterflow: 'Ngược chiều',
}

export const RULE_HINTS: Record<RuleName, string> = {
  overcrowd: 'Số người trong vùng theo dõi vượt mức thường ngày, hoặc vượt sức chứa tối đa đã đặt.',
  zone_limit: 'Một vùng có tên vượt sức chứa riêng do người vận hành đặt. Áp dụng ngay, không cần học.',
  hot_cell: 'Một ô 64×64 px chứa quá nhiều người: điểm tụ tập cục bộ.',
  surge: 'Số người tăng nhanh trong một phút: đám đông đổ về.',
  panic: 'Điểm của mô hình phát hiện bất thường (giai đoạn 2) vượt ngưỡng học từ chính camera.',
  counterflow: 'Một phần lớn chuyển động đi ngược hướng chính.',
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

/** Số theo kiểu Việt Nam (dấu phẩy thập phân). */
export const num = (v: number | null | undefined, digits = 0) =>
  v == null || !Number.isFinite(v) ? '–' : v.toLocaleString('vi-VN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
