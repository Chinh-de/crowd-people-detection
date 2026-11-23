// Màu biểu đồ (nền tối), đã kiểm bằng validate_palette.js của skill dataviz trên nền thẻ #1b2336:
// 6 màu phân loại đạt mọi kiểm tra (CVD ΔE ≥ 8,4; thị giác thường ΔE ≥ 19,3; tương phản ≥ 3:1).
import type { RuleName } from './types'

/** Mỗi loại cảnh báo một màu cố định (màu theo thực thể, không theo thứ hạng). */
export const RULE_COLORS: Record<RuleName, string> = {
  panic: '#3987e5',
  zone_limit: '#d95926',
  overcrowd: '#199e70',
  surge: '#c98500',
  hot_cell: '#d55181',
  counterflow: '#0ca30c',
}

export const SERIES = { count: '#3987e5', countMax: '#d95926', anomaly: '#199e70', limit: '#94a3b8' }

/** Thang tuần tự một sắc độ (xanh), nhạt dần theo độ lớn trên nền tối: gần 0 chìm về nền. */
const RAMP = ['#0d366b', '#104281', '#184f95', '#1c5cab', '#256abf', '#2a78d6', '#3987e5', '#5598e7', '#6da7ec', '#86b6ef', '#9ec5f4', '#b7d3f6', '#cde2fb']

export function seqColor(v: number, max: number): string {
  if (!(max > 0)) return RAMP[0]
  return RAMP[Math.min(RAMP.length - 1, Math.round((v / max) * (RAMP.length - 1)))]
}

export const AXIS = { tick: { fill: '#94A3B8', fontSize: 11 }, stroke: '#273244' }
export const GRID = '#273244'
export const TOOLTIP = { background: '#1B2336', border: '1px solid #334155', borderRadius: 8, fontSize: 12 }
