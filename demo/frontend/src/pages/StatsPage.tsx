import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { AXIS, GRID, RULE_COLORS, SERIES, TOOLTIP, seqColor } from '../charts'
import { Icon } from '../components/Icon'
import { RULE_LABELS, clock, num } from '../format'
import type { CameraSummary, RuleName, StatsResponse } from '../types'

type Range = 'today' | '7d' | '30d' | 'custom'
const RANGES: { id: Range; label: string }[] = [
  { id: 'today', label: 'Hôm nay' }, { id: '7d', label: '7 ngày' }, { id: '30d', label: '30 ngày' }, { id: 'custom', label: 'Tự chọn' },
]
const WEEKDAYS = ['T2', 'T3', 'T4', 'T5', 'T6', 'T7', 'CN']
const RULES = Object.keys(RULE_LABELS) as RuleName[]

function rangeSeconds(r: Range, from: string, to: string): [number, number] {
  const now = Date.now() / 1000
  if (r === 'today') {
    const d = new Date()
    d.setHours(0, 0, 0, 0)
    return [d.getTime() / 1000, now]
  }
  if (r === '7d') return [now - 7 * 86400, now]
  if (r === '30d') return [now - 30 * 86400, now]
  const t0 = from ? new Date(`${from}T00:00`).getTime() / 1000 : now - 86400
  const t1 = to ? new Date(`${to}T23:59:59`).getTime() / 1000 : now
  return [t0, t1]
}

function bucketLabel(t: number, bucket: number, tz: string): string {
  const o: Intl.DateTimeFormatOptions = bucket >= 86400 ? { day: '2-digit', month: '2-digit' }
    : bucket >= 3600 ? { day: '2-digit', month: '2-digit', hour: '2-digit' } : { hour: '2-digit', minute: '2-digit' }
  return new Intl.DateTimeFormat('vi-VN', { timeZone: tz, hour12: false, ...o }).format(new Date(t * 1000))
}

/** Trang Thống kê: tóm tắt, số người theo thời gian, giờ cao điểm trong tuần, cảnh báo theo ngày. */
export function StatsPage({ cameras }: { cameras: CameraSummary[] }) {
  const [cameraId, setCameraId] = useState<string>('')
  const [range, setRange] = useState<Range>('7d')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [data, setData] = useState<StatsResponse | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!cameraId && cameras.length) setCameraId(String((cameras.find((c) => c.running) ?? cameras[0]).id))
  }, [cameras, cameraId])

  useEffect(() => {
    const [t0, t1] = rangeSeconds(range, from, to)
    api.stats(t0, t1, cameraId ? Number(cameraId) : undefined)
      .then((d) => { setData(d); setError(null) }).catch((e: Error) => setError(e.message))
  }, [cameraId, range, from, to])

  const tz = data?.tz ?? 'UTC'
  const s = data?.summary
  const totalEvents = s ? Object.values(s.events).reduce((a, b) => a + b, 0) : 0

  const byDay = useMemo(() => {
    const days = new Map<string, Record<string, number | string>>()
    for (const r of data?.events_by_day ?? []) {
      const row = days.get(r.day) ?? { day: r.day.slice(5).split('-').reverse().join('/') }
      row[r.rule] = r.n
      days.set(r.day, row)
    }
    return [...days.values()]
  }, [data])
  const rulesPresent = RULES.filter((r) => data?.events_by_day.some((e) => e.rule === r))

  const heat = useMemo(() => {
    const m = new Map((data?.heatmap ?? []).map((h) => [`${h.weekday}-${h.hour}`, h.roi_avg]))
    const max = Math.max(0, ...(data?.heatmap ?? []).map((h) => h.roi_avg))
    return { m, max }
  }, [data])

  const series = (data?.series ?? []).map((r) => ({ ...r, label: bucketLabel(r.t, data!.bucket, tz) }))
  const unit = !data ? '' : data.bucket >= 86400 ? 'ngày' : data.bucket >= 3600 ? 'giờ' : 'phút'

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h2>Thống kê</h2>
          <p className="muted small">Giờ theo múi giờ camera ({tz}). Số liệu gom theo phút, lưu lâu dài.</p>
        </div>
      </header>

      <section className="card filters" aria-label="Bộ lọc">
        <label className="field">
          <span>Camera</span>
          <select value={cameraId} onChange={(e) => setCameraId(e.target.value)}>
            {cameras.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            <option value="">Tất cả camera</option>
          </select>
        </label>
        <div className="field">
          <span>Khoảng thời gian</span>
          <div className="segmented" role="radiogroup" aria-label="Khoảng thời gian">
            {RANGES.map((r) => (
              <button key={r.id} role="radio" aria-checked={range === r.id} className={range === r.id ? 'on' : ''}
                onClick={() => setRange(r.id)}>{r.label}</button>
            ))}
          </div>
        </div>
        {range === 'custom' && (
          <>
            <label className="field"><span>Từ ngày</span><input type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></label>
            <label className="field"><span>Đến ngày</span><input type="date" value={to} onChange={(e) => setTo(e.target.value)} /></label>
          </>
        )}
      </section>
      {error && <p className="error" role="alert">{error}</p>}

      <div className="kpi-row">
        <div className="card kpi-tile">
          <span className="kpi-label"><Icon name="users" size={14} /> Số người trung bình</span>
          <span className="kpi-value mono">{num(s?.roi_avg, 1)}</span>
        </div>
        <div className="card kpi-tile">
          <span className="kpi-label"><Icon name="users" size={14} /> Cao nhất</span>
          <span className="kpi-value mono">{num(s?.roi_max)}</span>
          <span className="kpi-sub muted">{s?.roi_max_t ? clock(s.roi_max_t, tz, true) : '–'}</span>
        </div>
        <div className="card kpi-tile">
          <span className="kpi-label"><Icon name="alert" size={14} /> Cảnh báo</span>
          <span className="kpi-value mono">{totalEvents}</span>
          <span className="kpi-sub muted">
            {RULES.filter((r) => s?.events[r]).map((r) => `${RULE_LABELS[r]} ${s!.events[r]}`).join(' · ') || 'không có'}
          </span>
        </div>
        <div className="card kpi-tile">
          <span className="kpi-label"><Icon name="check" size={14} /> Đã xử lý</span>
          <span className="kpi-value mono">{totalEvents ? `${num((100 * (s?.acked ?? 0)) / totalEvents)}%` : '–'}</span>
          <span className="kpi-sub muted">{s?.acked ?? 0}/{totalEvents} cảnh báo</span>
        </div>
      </div>

      <div className="stats-grid">
        <section className="card" aria-labelledby="st-count">
          <header className="card-head">
            <h2 id="st-count"><Icon name="chart" /> Số người theo {unit}</h2>
          </header>
          <div className="chart-box chart-md">
            {!cameraId ? <p className="muted small center">Chọn một camera để xem số người theo thời gian.</p>
              : series.length === 0 ? <p className="muted small center">Chưa có số liệu trong khoảng này.</p> : (
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={series} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
                    <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="label" tick={AXIS.tick} stroke={AXIS.stroke} minTickGap={32} />
                    <YAxis tick={AXIS.tick} stroke={AXIS.stroke} width={44} allowDecimals={false} />
                    <Tooltip contentStyle={TOOLTIP} formatter={(v, n) => [num(Number(v), 1), n]} />
                    <Legend wrapperStyle={{ fontSize: 12, color: '#cbd5e1' }} />
                    <Line dataKey="roi_avg" name="Trung bình" stroke={SERIES.count} dot={series.length < 4 ? { r: 4 } : false} strokeWidth={2} isAnimationActive={false} />
                    <Line dataKey="roi_max" name="Cao nhất" stroke={SERIES.countMax} dot={series.length < 4 ? { r: 4 } : false} strokeWidth={2} isAnimationActive={false} />
                  </LineChart>
                </ResponsiveContainer>
              )}
          </div>
        </section>

        <section className="card" aria-labelledby="st-heat">
          <header className="card-head">
            <h2 id="st-heat"><Icon name="layers" /> Giờ cao điểm trong tuần</h2>
            <span className="muted small">số người trung bình</span>
          </header>
          {heat.m.size === 0 ? <p className="muted small center">Chưa có số liệu.</p> : (
            <div className="heatmap" role="table" aria-label="Số người trung bình theo thứ và giờ">
              <div className="hm-row" role="row">
                <span className="hm-head" role="columnheader" />
                {Array.from({ length: 24 }, (_, h) => (
                  <span key={h} className="hm-head mono" role="columnheader">{h % 3 === 0 ? h : ''}</span>
                ))}
              </div>
              {WEEKDAYS.map((w, d) => (
                <div key={w} className="hm-row" role="row">
                  <span className="hm-head" role="rowheader">{w}</span>
                  {Array.from({ length: 24 }, (_, h) => {
                    const v = heat.m.get(`${d}-${h}`)
                    return (
                      <span key={h} role="cell" className="hm-cell"
                        style={{ background: v == null ? 'transparent' : seqColor(v, heat.max) }}
                        title={v == null ? `${w} ${h}h: không có số liệu` : `${w} ${h}h: ${num(v, 1)} người`} />
                    )
                  })}
                </div>
              ))}
              <div className="hm-legend small muted">
                <span>0</span><span className="hm-scale" /><span className="mono">{num(heat.max, 1)} người</span>
              </div>
            </div>
          )}
        </section>

        <section className="card stats-wide" aria-labelledby="st-ev">
          <header className="card-head">
            <h2 id="st-ev"><Icon name="alert" /> Cảnh báo theo ngày</h2>
          </header>
          <div className="chart-box chart-md">
            {byDay.length === 0 ? <p className="muted small center">Không có cảnh báo trong khoảng này.</p> : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={byDay} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
                  <CartesianGrid stroke={GRID} strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="day" tick={AXIS.tick} stroke={AXIS.stroke} />
                  <YAxis tick={AXIS.tick} stroke={AXIS.stroke} width={36} allowDecimals={false} />
                  <Tooltip contentStyle={TOOLTIP} cursor={{ fill: '#ffffff0d' }} />
                  <Legend wrapperStyle={{ fontSize: 12, color: '#cbd5e1' }} />
                  {rulesPresent.map((r, i) => (
                    <Bar key={r} dataKey={r} name={RULE_LABELS[r]} stackId="ev" fill={RULE_COLORS[r]} stroke="#1b2336" strokeWidth={2}
                      radius={i === rulesPresent.length - 1 ? [4, 4, 0, 0] : 0} isAnimationActive={false} maxBarSize={36} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
