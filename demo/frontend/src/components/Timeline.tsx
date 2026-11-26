import { useState } from 'react'
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { AXIS, GRID, SERIES, TOOLTIP } from '../charts'
import { RULE_LABELS, clock, num } from '../format'
import type { EventRow, SeriesRow } from '../types'
import { Icon } from './Icon'

/**
 * Hai biểu đồ xếp chồng, chung trục thời gian (không dùng hai trục tung trên một biểu đồ):
 * số người, và điểm bất thường kèm đường ngưỡng. Vạch đỏ nhạt = thời điểm cảnh báo.
 */
export function SeriesCharts({ series, events, tz, limit, height = 90 }: {
  series: SeriesRow[]; events: EventRow[]; tz: string; limit: number | null; height?: number
}) {
  const t0 = series[0]?.t ?? 0
  const marks = events.filter((e) => e.t >= t0)
  const x = (show: boolean) => (
    <XAxis dataKey="t" type="number" domain={['dataMin', 'dataMax']} tick={show ? AXIS.tick : false}
      tickFormatter={(t: number) => clock(t, tz)} stroke={AXIS.stroke} minTickGap={48} height={show ? 20 : 4} />
  )
  const tooltip = (digits: number) => (
    <Tooltip contentStyle={TOOLTIP} labelFormatter={(t) => clock(Number(t), tz, true)}
      formatter={(v, name) => [num(Number(v), digits), name]} />
  )
  return (
    <div className="stacked-charts">
      <div style={{ height }}>
        <span className="chart-label"><i style={{ background: SERIES.count }} /> Số người</span>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series} syncId="tl" margin={{ top: 18, right: 8, bottom: 0, left: -8 }}>
            <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
            {x(false)}
            <YAxis tick={AXIS.tick} stroke={AXIS.stroke} width={44} allowDecimals={false} />
            {tooltip(0)}
            {marks.map((e) => <ReferenceLine key={e.id} x={e.t} stroke="#EF444466" strokeWidth={6} />)}
            <Line dataKey="roi" name="Số người" stroke={SERIES.count} dot={false} strokeWidth={2} isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <div style={{ height: height + 16 }}>
        <span className="chart-label"><i style={{ background: SERIES.anomaly }} /> Điểm bất thường
          <i className="dash" style={{ borderColor: SERIES.limit }} /> ngưỡng</span>
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series} syncId="tl" margin={{ top: 18, right: 8, bottom: 0, left: -8 }}>
            <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
            {x(true)}
            <YAxis tick={AXIS.tick} stroke={AXIS.stroke} width={44} domain={['auto', 'auto']}
              tickFormatter={(v: number) => num(v, 2)} />
            {tooltip(3)}
            {marks.map((e) => (
              <ReferenceLine key={e.id} x={e.t} stroke="#EF444466" strokeWidth={6}
                label={{ value: RULE_LABELS[e.rule], fill: '#FCA5A5', fontSize: 10, position: 'insideTopLeft' }} />
            ))}
            {limit != null && <ReferenceLine y={limit} stroke={SERIES.limit} strokeDasharray="5 4" />}
            <Line dataKey="anomaly" name="Điểm bất thường" stroke={SERIES.anomaly} dot={false} strokeWidth={2}
              connectNulls isAnimationActive={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

const OPEN_KEY = 'crowd.timeline'
function readOpen(): boolean {
  try {
    return localStorage.getItem(OPEN_KEY) !== '0'
  } catch {
    return true
  }
}

/** Diễn biến 10 phút gần nhất của camera đang xem; thu gọn được để video cao hơn. */
export function Timeline({ series, events, tz, limit }: {
  series: SeriesRow[]; events: EventRow[]; tz: string; limit: number | null
}) {
  const last = series[series.length - 1]
  const [open, setOpen] = useState(() => readOpen())
  const toggle = () => {
    setOpen(!open)
    try {
      localStorage.setItem(OPEN_KEY, open ? '0' : '1')
    } catch { /* trình duyệt chặn lưu trữ: chỉ không nhớ lựa chọn */ }
  }
  return (
    <section className="card timeline" aria-labelledby="tl-title">
      <header className="card-head">
        <h2 id="tl-title"><Icon name="chart" /> Diễn biến 10 phút</h2>
        <span className="muted small spacer">
          {last ? `hiện ${num(last.roi)} người · điểm ${num(last.anomaly, 3)}` : ''}
        </span>
        <button className="btn btn-ghost btn-sm" onClick={toggle} aria-expanded={open}>{open ? 'Thu gọn' : 'Mở biểu đồ'}</button>
      </header>
      {!open ? null : series.length < 2 ? <p className="muted small center">Đang chờ dữ liệu…</p>
        : <SeriesCharts series={series} events={events} tz={tz} limit={limit} height={window.innerHeight < 900 ? 48 : 84} />}
    </section>
  )
}
