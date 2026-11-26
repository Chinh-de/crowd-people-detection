import { useEffect, useState } from 'react'
import { api } from '../api'
import { RULE_LABELS, VERDICT_LABELS, clock } from '../format'
import type { EventRow, SeriesRow, Verdict } from '../types'
import { Icon } from './Icon'
import { SeriesCharts } from './Timeline'

/** Chi tiết một cảnh báo: clip bằng chứng, diễn biến ±2 phút, phân loại đúng/nhầm để lưu mẫu (quản trị), xác nhận đã xử lý. */
export function EventModal({ event, tz, canJudge, onClose, onAcked }: {
  event: EventRow; tz: string; canJudge: boolean; onClose: () => void; onAcked: (e: EventRow) => void
}) {
  const [series, setSeries] = useState<SeriesRow[]>([])
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<'evidence' | 'sample'>('evidence')
  const [info, setInfo] = useState<string | null>(null)

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

  const run = async (fn: () => Promise<void>) => {
    setBusy(true)
    setError(null)
    setInfo(null)
    try {
      await fn()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const judge = (v: Verdict) => run(async () => {
    const next = event.verdict === v ? null : v            // bấm lại lựa chọn đang chọn để bỏ đánh giá
    onAcked(await api.setVerdict(event.id, next, note))
    setInfo(next ? 'Đã phân loại. Mẫu được giữ lại để fine-tune.' : 'Đã bỏ phân loại.')
  })

  const sendToLabeling = () => {
    if (!window.confirm('Đưa ảnh này vào bộ nhãn Temple Bar? Chỉ nên gửi ảnh của camera Temple Bar.')) return
    run(async () => {
      const { image } = await api.toLabeling(event.id)
      setInfo(`Đã đưa vào trang Gắn nhãn: ${image}. Sửa điểm nháp rồi duyệt để dùng khi fine-tune.`)
    })
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

        {!!event.has_sample && (
          <div className="segmented" role="radiogroup" aria-label="Nội dung xem">
            <button role="radio" aria-checked={view === 'evidence'} className={view === 'evidence' ? 'on' : ''}
              onClick={() => setView('evidence')}>Bằng chứng</button>
            <button role="radio" aria-checked={view === 'sample'} className={view === 'sample' ? 'on' : ''}
              onClick={() => setView('sample')}>Mask và nhãn</button>
          </div>
        )}

        {view === 'sample' && event.has_sample ? (
          <>
            <img src={api.sampleUrl(event.id, 'preview.jpg')} alt="Ảnh lúc cảnh báo kèm mask và điểm nhãn" />
            <p className="muted small">Vàng: vùng mô hình cho là có người. Chấm đỏ: nhãn nháp do mô hình đặt, chưa được người kiểm tra.</p>
          </>
        ) : event.purged ? (
          <p className="muted small">Ảnh và clip đã được tự xóa theo thời hạn lưu trữ.</p>
        ) : event.clip ? (
          <video src={event.clip} controls autoPlay />
        ) : (
          <><img src={event.snapshot} alt="Ảnh bằng chứng" /><p className="muted small">Đang ghi clip trước và sau sự kiện…</p></>
        )}

        {series.length < 2 ? <p className="muted small center">Không còn số liệu chi tiết quanh thời điểm này.</p>
          : <SeriesCharts series={series} events={[event]} tz={tz} limit={event.rule === 'panic' ? event.threshold : null} height={80} />}

        {canJudge && (
          <div className="row verdict-row" role="group" aria-label="Phân loại cảnh báo">
            <span className="small muted">Phân loại mẫu:</span>
            <button className={`btn ${event.verdict === 'true' ? 'btn-primary' : ''}`} aria-pressed={event.verdict === 'true'}
              disabled={busy} onClick={() => judge('true')}><Icon name="check" size={14} /> {VERDICT_LABELS.true}</button>
            <button className={`btn ${event.verdict === 'false' ? 'btn-danger-on' : ''}`} aria-pressed={event.verdict === 'false'}
              disabled={busy} onClick={() => judge('false')}><Icon name="x" size={14} /> {VERDICT_LABELS.false}</button>
            <span className="spacer" />
            {!!event.has_sample && (
              <button className="btn" disabled={busy} onClick={sendToLabeling}><Icon name="edit" size={14} /> Gửi sang Gắn nhãn</button>
            )}
          </div>
        )}
        {info && <p className="small ok-text" role="status">{info}</p>}

        {event.status === 'ack' ? (
          <p className="ack-done">
            <Icon name="check" size={14} /> Đã xử lý bởi <b>{event.ack_by}</b>
            {event.ack_at ? <> lúc <span className="mono">{clock(event.ack_at, tz, true)}</span></> : null}
            {event.verdict ? <> · phân loại: <b>{VERDICT_LABELS[event.verdict]}</b> ({event.verdict_by})</> : null}
            {event.note ? <> · “{event.note}”</> : null}
          </p>
        ) : (
          <div className="row">
            <input className="grow" value={note} onChange={(e) => setNote(e.target.value)} maxLength={500}
              placeholder="Ghi chú (không bắt buộc)" aria-label="Ghi chú xử lý" />
            <button className="btn" disabled={busy} onClick={ack}><Icon name="check" size={14} /> Đã xử lý</button>
          </div>
        )}
        {error && <p className="error" role="alert">{error}</p>}
      </div>
    </div>
  )
}
