import { useEffect, useState } from 'react'
import { api } from '../api'
import { num } from '../format'
import type { AnomalyModels, CountModelInfo, Status } from '../types'
import { Icon } from './Icon'

/**
 * Mô hình của camera đang xem, theo hai giai đoạn của đề tài.
 * Giai đoạn 1 đếm người; giai đoạn 2 phát hiện bất thường.
 */
export function PipelineCard({ status, canEdit }: { status: Status; canEdit: boolean }) {
  const [counters, setCounters] = useState<CountModelInfo[]>([])
  const [anomaly, setAnomaly] = useState<AnomalyModels | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const cid = status.camera_id

  useEffect(() => {
    api.listModels().then(setCounters).catch((e: Error) => setError(e.message))
    api.listAnomalyModels().then(setAnomaly).catch((e: Error) => setError(e.message))
  }, [])

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const a = status.anomaly
  const locked = busy || !canEdit
  const counter = counters.find((m) => m.name === status.model)
  const detector = anomaly?.models.find((m) => m.name === a.model)

  return (
    <section className="card" aria-labelledby="pipe-title">
      <header className="card-head">
        <h2 id="pipe-title"><Icon name="cpu" /> Mô hình</h2>
        {!canEdit && <span className="muted small">chỉ xem</span>}
      </header>

      <div className="stage-block">
        <label className="field">
          <span className="stage-title"><span className="stage-no">1</span> Đếm người</span>
          <select value={status.model} disabled={locked} onChange={(e) => act(() => api.setModel(cid, e.target.value))}>
            {counters.map((m) => (
              <option key={m.name} value={m.name} disabled={!m.available}>{m.label}{m.available ? '' : ' (thiếu file)'}</option>
            ))}
          </select>
        </label>
        {counter && (
          <dl className="metrics">
            <dt>ShanghaiTech B · MAE / MSE</dt><dd className="mono">{num(counter.mae, 2)} / {num(counter.mse, 2)}</dd>
            <dt>Camera Dublin · MAE</dt><dd className="mono">{counter.mae_dublin == null ? 'chưa đo' : num(counter.mae_dublin, 2)}</dd>
          </dl>
        )}
        <p className="note">MAE càng thấp càng tốt. Bản tinh chỉnh Dublin đếm tốt hơn trên camera Temple Bar,
          đổi lại kém hơn một chút trên ShanghaiTech.</p>
      </div>

      <div className="stage-block">
        <div className="stage-title"><span className="stage-no">2</span> Phát hiện bất thường · Isolation Forest</div>
        {detector && (
          <dl className="metrics">
            <dt>UMN · AUC (càng cao càng tốt)</dt><dd className="mono">{num(detector.umn_auc, 3)}</dd>
          </dl>
        )}
        {a.learning || (!status.calibration.done && status.calibration.need > 0) ? (
          <div className="progress-wrap">
            <progress max={Math.max(a.need, 1)} value={a.have} aria-label="Tiến độ học mức bình thường" />
            <span className="mono small">{a.have}/{a.need} mẫu</span>
          </div>
        ) : (
          <p className="small">{status.calibration.done ? <span className="ok-text">Sẵn sàng</span> : <span className="muted">Chưa sẵn sàng</span>}</p>
        )}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  )
}
