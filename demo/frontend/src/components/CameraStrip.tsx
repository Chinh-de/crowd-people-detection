import { useEffect, useState } from 'react'
import { api } from '../api'
import { RULE_LABELS, num } from '../format'
import type { CameraSummary, LiveMessage } from '../types'
import { Icon } from './Icon'

const SNAPSHOT_MS = 1000

/**
 * Dải camera: mọi camera trong danh sách. Camera đang chạy có ảnh trực tiếp (làm mới mỗi giây), số người,
 * trạng thái; ô đang cảnh báo nổi đỏ. Bấm vào ô để xem camera đó; quản trị bật/tắt camera ngay tại đây.
 */
export function CameraStrip({ cameras, live, selected, onSelect, canEdit, onChanged }: {
  cameras: CameraSummary[]; live: LiveMessage | null; selected: number | null
  onSelect: (id: number) => void; canEdit: boolean; onChanged: () => void
}) {
  const [tick, setTick] = useState(0)
  const [busy, setBusy] = useState<number | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const id = window.setInterval(() => setTick((t) => t + 1), SNAPSHOT_MS)
    return () => window.clearInterval(id)
  }, [])

  const running = cameras.filter((c) => live?.cameras[c.id]).length
  const max = live?.max_cameras ?? 4

  const toggle = async (c: CameraSummary, on: boolean) => {
    setBusy(c.id)
    setError(null)
    try {
      if (on) {
        await api.startCamera(c.id)
        onSelect(c.id)
      } else {
        await api.stopCamera(c.id)
      }
      onChanged()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  return (
    <section className="cam-strip" aria-label="Danh sách camera">
      <div className="cam-strip-head">
        <span className="small"><b>{running}/{max}</b> camera đang chạy</span>
        <span className="muted small">Giới hạn {max} camera cùng lúc do phần cứng: mỗi camera cần một luồng phân tích trên CPU.</span>
      </div>
      <div className="cam-tiles">
        {cameras.map((c) => {
          const st = live?.cameras[c.id]
          const alerting = (st?.active_alerts.length ?? 0) > 0
          const lost = st?.state === 'error'
          return (
            <div key={c.id} className={`cam-tile ${selected === c.id ? 'on' : ''} ${alerting ? 'alerting' : ''} ${st ? '' : 'off'}`}>
              <button className="cam-tile-main" onClick={() => st && onSelect(c.id)} disabled={!st}
                aria-pressed={selected === c.id} aria-label={`Xem camera ${c.name}`}>
                <span className="cam-thumb">
                  {st && !lost ? <img src={api.snapshotUrl(c.id, tick)} alt="" /> : (
                    <span className="cam-thumb-empty"><Icon name={lost ? 'alert' : 'video'} size={18} />{lost ? 'Mất tín hiệu' : 'Đang tắt'}</span>
                  )}
                  {st && <span className={`cam-live ${c.kind === 'youtube' ? 'live' : ''}`}>{c.kind === 'youtube' ? 'TRỰC TIẾP' : 'VIDEO'}</span>}
                </span>
                <span className="cam-info">
                  <span className="cam-name">{c.name}</span>
                  {st ? (
                    <span className="small">
                      <span className="mono">{num(st.counts.roi)}</span> người
                      {alerting
                        ? <span className="cam-alert"> · {st.active_alerts.map((r) => RULE_LABELS[r]).join(', ')}</span>
                        : <span className="muted"> · {num(st.perf.analysis_fps, 1)} lần/s</span>}
                    </span>
                  ) : <span className="muted small">{c.kind === 'youtube' ? 'Livestream' : c.source}</span>}
                </span>
              </button>
              {canEdit && (
                <button className="btn btn-ghost btn-sm cam-toggle" disabled={busy === c.id}
                  onClick={() => toggle(c, !st)} aria-label={st ? `Tắt ${c.name}` : `Bật ${c.name}`}>
                  <Icon name={st ? 'stop' : 'play'} size={13} /> {busy === c.id ? '…' : st ? 'Tắt' : 'Bật'}
                </button>
              )}
            </div>
          )
        })}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  )
}
