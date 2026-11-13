import { useState } from 'react'
import { RULE_LABELS, clock } from '../format'
import type { EventRow } from '../types'

/** Danh sách cảnh báo kèm ảnh bằng chứng; click để xem clip trước/sau sự kiện. */
export function AlertList({ events, tz }: { events: EventRow[]; tz: string }) {
  const [open, setOpen] = useState<EventRow | null>(null)
  return (
    <section className="panel">
      <header><h2>Cảnh báo</h2><span className="muted">{events.length}</span></header>
      {events.length === 0 && <p className="muted">Chưa có cảnh báo.</p>}
      <ul className="alerts">
        {events.map((e) => (
          <li key={e.id} onClick={() => setOpen(e)}>
            <img src={e.snapshot} alt="" loading="lazy" />
            <div>
              <b className={`rule rule-${e.rule}`}>{RULE_LABELS[e.rule]}</b>
              <span className="muted mono">{clock(e.t, tz, true)}</span>
              <p>{e.message}</p>
            </div>
          </li>
        ))}
      </ul>

      {open && (
        <div className="modal" onClick={() => setOpen(null)}>
          <div className="modal-body" onClick={(ev) => ev.stopPropagation()}>
            <header>
              <h2>{RULE_LABELS[open.rule]} · {clock(open.t, tz, true)}</h2>
              <button onClick={() => setOpen(null)}>Đóng</button>
            </header>
            <p>{open.message}</p>
            {open.clip
              ? <video src={open.clip} controls autoPlay />
              : <><img src={open.snapshot} alt="Ảnh bằng chứng" /><p className="muted">Đang ghi clip…</p></>}
          </div>
        </div>
      )}
    </section>
  )
}
