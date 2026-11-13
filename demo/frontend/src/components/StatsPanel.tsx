import { clock, num } from '../format'
import type { Status } from '../types'

/** Số liệu trực tiếp: số người, chuyển động, hiệu năng. */
export function StatsPanel({ status }: { status: Status }) {
  const { counts, motion, perf, source } = status
  return (
    <section className="panel">
      <header>
        <h2>Hiện tại</h2>
        {source && status.sample_t && <span className="muted mono">{clock(status.sample_t, source.tz)}</span>}
      </header>

      <div className="big-stat">
        <span className="value">{num(counts.roi)}</span>
        <span className="label">người trong vùng giám sát</span>
      </div>
      <div className="stat-grid">
        <Stat label="Toàn khung" value={num(counts.total)} />
        <Stat label="Vùng loại trừ" value={num(counts.excluded)} />
        <Stat label="Ô đông nhất" value={num(counts.max_cell, 1)} unit="người" />
        <Stat label="Ô vượt ngưỡng" value={String(counts.hot_cells)} />
      </div>

      <h3>Chuyển động</h3>
      <div className="stat-grid">
        <Stat label="Tốc độ" value={num(motion.speed)} unit="px/s" />
        <div className="stat">
          <span className="label">Hướng chính</span>
          <span className="value">
            {motion.active_ratio > 0.01
              ? <span className="arrow" style={{ transform: `rotate(${motion.direction_deg}deg)` }}>➜</span>
              : '–'}
          </span>
        </div>
        <Stat label="Mức hỗn loạn" value={num(motion.entropy, 2)} unit="0–1" />
        <Stat label="Ngược chiều" value={`${num(motion.counterflow * 100)}%`} />
      </div>

      <h3>Hiệu năng</h3>
      <div className="stat-grid">
        <Stat label="FPS video" value={num(perf.video_fps, 1)} />
        <Stat label="Phân tích" value={num(perf.analysis_fps, 1)} unit="lần/s" />
        <Stat label="Mỗi lần" value={num(perf.analysis_ms)} unit="ms" />
      </div>
    </section>
  )
}

function Stat({ label, value, unit }: { label: string; value: string; unit?: string }) {
  return (
    <div className="stat">
      <span className="label">{label}</span>
      <span className="value">{value}{unit && <small> {unit}</small>}</span>
    </div>
  )
}
