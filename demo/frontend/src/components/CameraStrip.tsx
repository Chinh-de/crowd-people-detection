import { useState } from 'react'
import { api } from '../api'
import { RULE_LABELS, num } from '../format'
import type { CameraSummary, LiveMessage } from '../types'
import { Icon } from './Icon'

/**
 * Thanh camera: mỗi camera một nút gọn (tên, số người, trạng thái); camera đang cảnh báo nổi đỏ.
 * Bấm để xem; quản trị bật/tắt hoặc thêm camera ngay tại đây.
 */
export function CameraStrip({ cameras, live, selected, onSelect, canEdit, onChanged, onAdd, onStarting }: {
  cameras: CameraSummary[]; live: LiveMessage | null; selected: number | null
  onSelect: (id: number) => void; canEdit: boolean; onChanged: () => void; onAdd: () => void
  onStarting: (name: string | null) => void
}) {
  const [busy, setBusy] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  const running = cameras.filter((c) => live?.cameras[c.id]).length
  const max = live?.max_cameras ?? 4

  const toggle = async (c: CameraSummary, on: boolean) => {
    setBusy(c.id)
    setError(null)
    try {
      if (on) {
        onStarting(c.name)
        await api.startCamera(c.id)
        onSelect(c.id)
      } else {
        await api.stopCamera(c.id)
      }
      onChanged()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      if (on) onStarting(null)
      setBusy(null)
    }
  }

  return (
    <section className="cam-bar" aria-label="Danh sách camera">
      <div className="cam-chips">
        {cameras.map((c) => {
          const st = live?.cameras[c.id]
          const alerting = (st?.active_alerts.length ?? 0) > 0
          const lost = st?.state === 'error'
          const waiting = busy === c.id
          const detail = waiting ? (st ? 'đang tắt…' : 'đang bật…') : !st ? 'đang tắt' : lost ? 'mất tín hiệu'
            : alerting ? st.active_alerts.map((r) => RULE_LABELS[r]).join(', ') : `${num(st.counts.roi)} người`
          return (
            <div key={c.id} className={`cam-chip ${selected === c.id ? 'on' : ''} ${alerting || lost ? 'alerting' : ''} ${st ? '' : 'off'}`}>
              <button className="cam-chip-main" onClick={() => st && onSelect(c.id)} disabled={!st}
                aria-pressed={selected === c.id} title={`${c.name} · ${detail}`}>
                {waiting ? <span className="spinner spinner-sm" aria-hidden="true" /> : <span className="cam-dot" aria-hidden="true" />}
                <span className="cam-name">{c.name}</span>
                <span className="cam-detail small">{detail}</span>
              </button>
              {canEdit && (
                <button className="cam-chip-toggle" disabled={busy === c.id} onClick={() => toggle(c, !st)}
                  aria-label={st ? `Tắt camera ${c.name}` : `Bật camera ${c.name}`} title={st ? 'Tắt' : 'Bật'}>
                  {waiting ? <span className="spinner spinner-sm" aria-hidden="true" /> : <Icon name={st ? 'stop' : 'play'} size={12} />}
                </button>
              )}
            </div>
          )
        })}
        {canEdit && <button className="btn btn-sm" onClick={onAdd}><Icon name="plus" size={13} /> Thêm</button>}
      </div>
      <span className="muted small cam-limit" title="Mỗi camera cần một luồng phân tích trên CPU">
        {running}/{max} · giới hạn phần cứng
      </span>
      {error && <p className="error cam-error" role="alert">{error}</p>}
    </section>
  )
}
