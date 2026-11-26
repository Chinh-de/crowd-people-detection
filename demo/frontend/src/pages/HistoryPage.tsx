import { useCallback, useEffect, useState } from 'react'
import { api, type EventFilter } from '../api'
import { EventModal } from '../components/EventModal'
import { Icon } from '../components/Icon'
import { RULE_LABELS, VERDICT_LABELS, clock } from '../format'
import type { CameraSummary, EventRow, RuleName, VerdictCounts } from '../types'

const PAGE = 25
const LOCAL_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone

/** Chuỗi 'YYYY-MM-DDTHH:mm' (ô datetime-local, giờ máy người xem) ↔ giây UTC. */
const toSec = (v: string) => (v ? new Date(v).getTime() / 1000 : undefined)

/** Trang Lịch sử cảnh báo: lọc, phân trang, xem clip và diễn biến, xác nhận đã xử lý, xuất CSV. */
export function HistoryPage({ cameras, unacked, canJudge }: {
  cameras: CameraSummary[]; unacked: number; canJudge: boolean
}) {
  const [cameraId, setCameraId] = useState('')
  const [rule, setRule] = useState('')
  const [status, setStatus] = useState('')
  const [verdict, setVerdict] = useState('')
  const [from, setFrom] = useState('')
  const [to, setTo] = useState('')
  const [page, setPage] = useState(0)
  const [rows, setRows] = useState<EventRow[]>([])
  const [total, setTotal] = useState(0)
  const [open, setOpen] = useState<EventRow | null>(null)
  const [counts, setCounts] = useState<VerdictCounts>({ none: 0, true: 0, false: 0 })
  const [error, setError] = useState<string | null>(null)

  const filter: EventFilter = {
    camera_id: cameraId ? Number(cameraId) : undefined, rule: rule || undefined, status: status || undefined, verdict: verdict || undefined,
    t0: toSec(from), t1: toSec(to),
  }
  const key = JSON.stringify(filter)

  const load = useCallback(() => {
    api.events({ ...JSON.parse(key), limit: PAGE, offset: page * PAGE })
      .then((p) => { setRows(p.rows); setTotal(p.total); setCounts(p.verdicts); setError(null) })
      .catch((e: Error) => setError(e.message))
  }, [key, page])

  useEffect(load, [load])
  useEffect(() => setPage(0), [key])
  useEffect(load, [unacked])          // có cảnh báo mới hoặc vừa xử lý: làm mới

  const tzOf = (e: EventRow) => cameras.find((c) => c.id === e.camera_id)?.tz ?? LOCAL_TZ
  const pages = Math.max(1, Math.ceil(total / PAGE))

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h2>Lịch sử cảnh báo</h2>
          <p className="muted small">{total} cảnh báo đang xem · {unacked} chưa xử lý · giờ theo múi giờ của từng camera</p>
        </div>
        <div className="row">
          {canJudge && (
            <a className="btn" href={api.feedbackExportUrl} download title="Ảnh gốc, mask, nhãn nháp và đặc trưng của các cảnh báo đã phân loại, dùng để fine-tune">
              <Icon name="download" size={14} /> Xuất mẫu đã phân loại
            </a>
          )}
          <a className="btn" href={api.eventsCsvUrl(filter)} download><Icon name="download" size={14} /> Xuất CSV</a>
        </div>
      </header>

      <div className="segmented" role="tablist" aria-label="Phân loại cảnh báo">
        {([['', 'Tất cả', counts.none + counts.true + counts.false], ['none', 'Chưa phân loại', counts.none],
          ['true', VERDICT_LABELS.true, counts.true], ['false', VERDICT_LABELS.false, counts.false]] as const).map(([v, label, n]) => (
          <button key={v} role="tab" aria-selected={verdict === v} className={verdict === v ? 'on' : ''}
            onClick={() => setVerdict(v)}>{label} <span className="mono muted">{n}</span></button>
        ))}
      </div>

      <section className="card filters" aria-label="Bộ lọc">
        <label className="field">
          <span>Camera</span>
          <select value={cameraId} onChange={(e) => setCameraId(e.target.value)}>
            <option value="">Tất cả</option>
            {cameras.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </label>
        <label className="field">
          <span>Loại cảnh báo</span>
          <select value={rule} onChange={(e) => setRule(e.target.value)}>
            <option value="">Tất cả</option>
            {(Object.keys(RULE_LABELS) as RuleName[]).map((r) => <option key={r} value={r}>{RULE_LABELS[r]}</option>)}
          </select>
        </label>
        <label className="field">
          <span>Trạng thái</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="">Tất cả</option>
            <option value="new">Chưa xử lý</option>
            <option value="ack">Đã xử lý</option>
          </select>
        </label>
        <label className="field">
          <span>Từ</span>
          <input type="datetime-local" value={from} onChange={(e) => setFrom(e.target.value)} />
        </label>
        <label className="field">
          <span>Đến</span>
          <input type="datetime-local" value={to} onChange={(e) => setTo(e.target.value)} />
        </label>
        <button className="btn btn-ghost" onClick={() => { setCameraId(''); setRule(''); setStatus(''); setVerdict(''); setFrom(''); setTo('') }}>
          Xóa lọc
        </button>
      </section>

      {error && <p className="error" role="alert">{error}</p>}

      <section className="card table-card">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Ảnh</th><th scope="col">Thời điểm</th><th scope="col">Camera</th><th scope="col">Loại</th>
                <th scope="col">Nội dung</th><th scope="col">Trạng thái</th><th scope="col">Phân loại</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((e) => (
                <tr key={e.id} onClick={() => setOpen(e)} tabIndex={0}
                  onKeyDown={(ev) => (ev.key === 'Enter' || ev.key === ' ') && setOpen(e)} className="clickable">
                  <td>{e.purged ? <span className="thumb-empty">đã xóa</span> : <img className="thumb" src={e.snapshot} alt="" loading="lazy" />}</td>
                  <td className="mono nowrap">{clock(e.t, tzOf(e), true)}</td>
                  <td>{e.source}</td>
                  <td><span className={`rule-chip rule-${e.rule}`}>{RULE_LABELS[e.rule]}</span></td>
                  <td className="small">{e.message.replace(/^[^:]+:\s*/, '')}</td>
                  <td>
                    {e.status === 'ack'
                      ? <span className="status-ok"><Icon name="check" size={13} /> {e.ack_by}</span>
                      : <span className="status-new">Chưa xử lý</span>}
                  </td>
                  <td>{e.verdict ? <span className={`verdict-tag v-${e.verdict}`}>{VERDICT_LABELS[e.verdict]}</span>
                    : <span className="muted">–</span>}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={7} className="muted center">Không có cảnh báo nào khớp bộ lọc.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="pager">
          <button className="btn btn-sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Trước</button>
          <span className="mono small">Trang {page + 1}/{pages}</span>
          <button className="btn btn-sm" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Sau</button>
        </div>
      </section>

      {open && <EventModal event={open} tz={tzOf(open)} canJudge={canJudge} onClose={() => setOpen(null)}
        onAcked={(e) => { setOpen(e); load() }} />}
    </div>
  )
}
