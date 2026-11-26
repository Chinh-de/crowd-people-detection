import { useEffect, useState } from 'react'
import { DIRECTIONS, RULE_LABELS, VERDICT_LABELS, anomalyState, clock, num } from '../format'
import type { EventRow, Status, ZoneMeta, ZoneSet } from '../types'
import { EventModal } from './EventModal'
import { Icon } from './Icon'

/** Số người và điểm bất thường hiện tại: hai đầu ra chính của hai giai đoạn. */
export function KpiCard({ status }: { status: Status }) {
  const c = status.counts
  const a = status.anomaly
  const state = anomalyState(a)
  const over = state.key === 'abnormal'
  return (
    <section className="card kpi-card" aria-label="Chỉ số trực tiếp">
      <div className="kpi">
        <span className="kpi-label"><Icon name="users" size={14} /> Số người</span>
        <span className="kpi-value mono">{num(c.roi)}</span>
        <span className="kpi-sub muted" title={`loại trừ ${num(c.excluded)} · ô đông nhất ${num(c.max_cell, 1)}`}>toàn khung {num(c.total)}</span>
      </div>
      <div className={`kpi ${over ? 'kpi-alert' : ''}`}>
        <span className="kpi-label"><Icon name="activity" size={14} /> Chuyển động</span>
        <span className={`kpi-state state-${state.key}`}
          title={a.score != null && a.limit != null ? `điểm ${num(a.score, 3)} · ngưỡng ${num(a.limit, 3)}` : undefined}>
          {a.learning ? 'Đang học' : state.label}
        </span>
        {a.learning ? (
          <>
            <progress max={Math.max(a.need, 1)} value={a.have} aria-label="Tiến độ học mức bình thường" />
            <span className="kpi-sub muted">{a.have}/{a.need} mẫu bình thường</span>
          </>
        ) : (
          <span className="kpi-sub muted">{state.key === 'none' ? 'cần học mức bình thường trước' : a.label}</span>
        )}
      </div>
    </section>
  )
}

/** Vùng giám sát có tên: số người so với sức chứa, chiều đi cho phép; sửa tại chỗ. */
export function ZonesCard({ status, zones, editing, canEdit, onChange, onSave }: {
  status: Status
  canEdit: boolean
  zones: ZoneSet
  editing: boolean
  onChange: (z: ZoneSet) => void
  onSave: (z: ZoneSet) => void
}) {
  const [local, setLocal] = useState<ZoneMeta[]>(zones.roi_meta)
  useEffect(() => setLocal(zones.roi_meta), [zones])
  const dirty = !editing && JSON.stringify(local) !== JSON.stringify(zones.roi_meta)

  const setMeta = (i: number, patch: Partial<ZoneMeta>) => {
    const next = local.map((m, j) => (j === i ? { ...m, ...patch } : m))
    setLocal(next)
    if (editing) onChange({ ...zones, roi_meta: next })
  }

  return (
    <section className="card" aria-labelledby="zones-title">
      <header className="card-head">
        <h2 id="zones-title"><Icon name="zone" /> Vùng giám sát</h2>
        {dirty && canEdit && <button className="btn btn-primary btn-sm" onClick={() => onSave({ ...zones, roi_meta: local })}>Lưu</button>}
      </header>
      {zones.roi.length === 0 ? (
        <p className="muted small">Chưa có vùng: đang theo dõi cả khung hình. Bấm "Vẽ vùng" phía trên video để khoanh vùng và đặt sức chứa.</p>
      ) : (
        <ul className="zone-list">
          {zones.roi.map((_, i) => {
            const live = status.zones[i]
            const meta = local[i] ?? { name: `Vùng ${i + 1}`, limit: null }
            const pct = live && meta.limit ? live.count / meta.limit : null
            return (
              <li key={i} className={pct != null && pct > 1 ? 'over' : ''}>
                <div className="zone-row">
                  <input className="zone-name" value={meta.name} disabled={!canEdit} aria-label={`Tên vùng ${i + 1}`}
                    onChange={(e) => setMeta(i, { name: e.target.value })} />
                  <span className="mono zone-count">{live ? num(live.count) : '–'}</span>
                  <span className="muted">/</span>
                  <input className="zone-limit mono" type="number" min={0} disabled={!canEdit} placeholder="∞" value={meta.limit ?? ''}
                    aria-label={`Sức chứa ${meta.name}`}
                    onChange={(e) => setMeta(i, { limit: e.target.value === '' ? null : Number(e.target.value) })} />
                </div>
                <label className="zone-direction small muted">
                  <span>Chiều đi</span>
                  <select value={meta.direction ?? ''} disabled={!canEdit} aria-label={`Chiều đi cho phép của ${meta.name}`}
                    onChange={(e) => setMeta(i, { direction: e.target.value === '' ? null : Number(e.target.value) })}>
                    <option value="">hai chiều (không xét)</option>
                    {DIRECTIONS.map((d) => <option key={d.value} value={d.value}>{d.label}</option>)}
                  </select>
                </label>
                {live?.direction != null && live.wrong_share != null && (
                  <span className="small muted">{num(live.wrong_share * 100)}% đang đi ngược</span>
                )}
                <div className="bar" aria-hidden="true">
                  <span style={{ width: `${Math.min(1, pct ?? 0) * 100}%` }} />
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}

/** Cảnh báo của camera đang xem: ảnh bằng chứng, giờ camera, trạng thái xử lý; bấm để xem chi tiết. */
export function AlertsCard({ events, tz, canJudge, onChanged }: {
  events: EventRow[]; tz: string; canJudge: boolean; onChanged: () => void
}) {
  const [open, setOpen] = useState<EventRow | null>(null)
  const pending = events.filter((e) => e.status === 'new').length
  return (
    <section className="card alerts-card" aria-labelledby="alerts-title">
      <header className="card-head">
        <h2 id="alerts-title"><Icon name="alert" /> Cảnh báo</h2>
        <span className={`count-badge mono ${pending ? 'count-badge-alert' : ''}`} title="Chưa xử lý / tổng">
          {pending}/{events.length}
        </span>
      </header>
      {events.length === 0 && <p className="muted small">Chưa có cảnh báo của camera này.</p>}
      <ul className="alert-list">
        {events.map((e) => (
          <li key={e.id}>
            <button className={`alert-item rule-${e.rule} ${e.status === 'ack' ? 'acked' : ''}`} onClick={() => setOpen(e)}>
              <img src={e.snapshot} alt="" loading="lazy" width={88} height={50} />
              <span className="alert-text">
                <span className="alert-rule">{RULE_LABELS[e.rule]}
                  {e.verdict && <span className={`verdict-tag v-${e.verdict}`}>{VERDICT_LABELS[e.verdict]}</span>}</span>
                <span className="mono small muted">{clock(e.t, tz, true)}</span>
                <span className="small">{e.message.replace(/^[^:]+:\s*/, '')}</span>
              </span>
              {e.status === 'ack'
                ? <Icon name="check" size={14} className="ok-text" />
                : e.clip ? <Icon name="film" size={14} className="muted" /> : null}
            </button>
          </li>
        ))}
      </ul>
      {open && <EventModal event={open} tz={tz} canJudge={canJudge} onClose={() => setOpen(null)}
        onAcked={(e) => { setOpen(e); onChanged() }} />}
    </section>
  )
}
