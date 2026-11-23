import { useEffect, useState } from 'react'
import { api } from '../api'
import { RULE_LABELS, clock } from '../format'
import type { EventRow, SeriesRow } from '../types'
import { Icon } from './Icon'
import { SeriesCharts } from './Timeline'

/** Chi tiết một cảnh báo: clip bằng chứng, diễn biến ±2 phút, xác nhận đã xử lý kèm ghi chú. */
export function EventModal({ event, tz, onClose, onAcked }: {
  event: EventRow; tz: string; onClose: () => void; onAcked: (e: EventRow) => void
}) {
  const [series, setSeries] = useState<SeriesRow[]>([])
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.eventContext(event.id).then((r) => setSeries(r.series)).catch(() => setSeries([]))
  }, [event.id])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const ack = async () => {
    setBusy(true)
    setError(null)
    try {
      onAcked(await api.ackEvent(event.id, note))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label={RULE_LABELS[event.rule]} onClick={onClose}>
      <div className="modal-body" onClick={(ev) => ev.stopPropagation()}>
        <header className="card-head">
          <h2>
            <span className={`rule-dot rule-${event.rule}`} /> {RULE_LABELS[event.rule]} · {event.source} ·{' '}
            <span className="mono">{clock(event.t, tz, true)}</span>
          </h2>
          <button className="btn btn-icon" onClick={onClose} aria-label="Đóng"><Icon name="x" /></button>
        </header>
        <p>{event.message}</p>

        {event.purged ? (
          <p className="muted small">Ảnh và clip đã được tự xóa theo thời hạn lưu trữ.</p>
        ) : event.clip ? (
          <video src={event.clip} controls autoPlay />
        ) : (
          <><img src={event.snapshot} alt="Ảnh bằng chứng" /><p className="muted small">Đang ghi clip trước và sau sự kiện…</p></>
        )}

        {series.length < 2 ? <p className="muted small center">Không còn số liệu chi tiết quanh thời điểm này.</p>
          : <SeriesCharts series={series} events={[event]} tz={tz} limit={event.rule === 'panic' ? event.threshold : null} height={80} />}

        {event.status === 'ack' ? (
          <p className="ack-done">
            <Icon name="check" size={14} /> Đã xử lý bởi <b>{event.ack_by}</b>
            {event.ack_at ? <> lúc <span className="mono">{clock(event.ack_at, tz, true)}</span></> : null}
            {event.note ? <> · “{event.note}”</> : null}
          </p>
        ) : (
          <div className="row">
            <input className="grow" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500}
              placeholder="Ghi chú xử lý (không bắt buộc)" aria-label="Ghi chú xử lý" />
            <button className="btn btn-primary" disabled={busy} onClick={ack}><Icon name="check" size={14} /> Đã xử lý</button>
          </div>
        )}
        {error && <p className="error" role="alert">{error}</p>}
      </div>
    </div>
  )
}
