import { CartesianGrid, Legend, Line, LineChart, ReferenceDot, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { clock } from '../format'
import type { EventRow, SeriesRow } from '../types'

/** Số người trong vùng giám sát và tốc độ chuyển động theo thời gian; chấm đỏ = có cảnh báo. */
export function CountChart({ series, events, tz, limit }: {
  series: SeriesRow[]; events: EventRow[]; tz: string; limit: number | null
}) {
  const t0 = series[0]?.t ?? 0
  const roiAt = (t: number) => series.reduce((best, r) => (Math.abs(r.t - t) < Math.abs(best.t - t) ? r : best), series[0])?.roi ?? 0
  return (
    <section className="panel chart">
      <header><h2>Diễn biến</h2></header>
      <ResponsiveContainer width="100%" height={220}>
        <LineChart data={series} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
          <CartesianGrid stroke="#2a3140" />
          <XAxis dataKey="t" type="number" domain={['dataMin', 'dataMax']} tickFormatter={(t) => clock(t, tz)} stroke="#8b94a7" fontSize={11} />
          <YAxis yAxisId="count" stroke="#8b94a7" fontSize={11} />
          <YAxis yAxisId="speed" orientation="right" stroke="#8b94a7" fontSize={11} />
          <Tooltip labelFormatter={(t) => clock(Number(t), tz)} contentStyle={{ background: '#151a23', border: '1px solid #2a3140' }}
            formatter={(v, name) => [Number(v).toFixed(name === 'Tốc độ (px/s)' ? 0 : 1), name]} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Line yAxisId="count" dataKey="roi" name="Người trong vùng" stroke="#4ea1ff" dot={false} isAnimationActive={false} />
          <Line yAxisId="speed" dataKey="speed" name="Tốc độ (px/s)" stroke="#9b8cff" dot={false} strokeOpacity={0.6} isAnimationActive={false} />
          {limit != null && <ReferenceLine yAxisId="count" y={limit} stroke="#e64646" strokeDasharray="4 4" />}
          {events.filter((e) => e.t >= t0).map((e) => (
            <ReferenceDot key={e.id} yAxisId="count" x={e.t} y={roiAt(e.t)} r={4} fill="#e64646" stroke="none" />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </section>
  )
}
