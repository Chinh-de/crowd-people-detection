import { useEffect, useState } from 'react'
import { api } from '../api'
import { num } from '../format'
import type { AnomalyModels, CountModelInfo, Status } from '../types'
import { Icon } from './Icon'

const KIND_LABEL = { speed: 'Mốc so sánh', if: 'Isolation Forest · học tại chỗ (mặc định)', ae: 'Autoencoder · đã train trên UMN' }

/**
 * Mô hình của camera đang xem, theo hai giai đoạn của đề tài.
 * Giai đoạn 1 đếm người; giai đoạn 2 phát hiện bất thường.
 */
export function PipelineCard({ status, canEdit }: { status: Status; canEdit: boolean }) {
  const [counters, setCounters] = useState<CountModelInfo[]>([])
  const [anomaly, setAnomaly] = useState<AnomalyModels | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [seconds, setSeconds] = useState(60)
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
  const groups = (['speed', 'if', 'ae'] as const).map((k) => [k, anomaly?.models.filter((m) => m.kind === k) ?? []] as const)

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
        <label className="field">
          <span className="stage-title"><span className="stage-no">2</span> Phát hiện bất thường</span>
          <select value={a.model} disabled={locked} onChange={(e) => act(() => api.setAnomalyModel(cid, e.target.value))}>
            {groups.map(([kind, list]) => list.length > 0 && (
              <optgroup key={kind} label={KIND_LABEL[kind]}>
                {list.map((m) => (
                  <option key={m.name} value={m.name} disabled={!m.available}>{m.label}{m.available ? '' : ' (thiếu file)'}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </label>
        {detector && (
          <dl className="metrics">
            <dt>UMN · AUC (càng cao càng tốt)</dt><dd className="mono">{num(detector.umn_auc, 3)}</dd>
          </dl>
        )}
        {a.kind === 'ae' && anomaly && (
          <>
            <div className="field-inline">
              <span>Chuẩn hóa đặc trưng</span>
              <div className="segmented segmented-sm">
                {anomaly.norm_modes.map((n) => (
                  <button key={n} className={a.norm === n ? 'on' : ''} disabled={locked}
                    onClick={() => act(() => api.setAnomalyModel(cid, a.model, n))}>
                    {n === 'camera' ? 'Theo camera' : 'Gốc UMN'}
                  </button>
                ))}
              </div>
            </div>
            <p className="note">Cửa sổ 16 mẫu ở tốc độ phân tích trên CPU dài vài giây, khác 0,5 s lúc train trên UMN,
              nên autoencoder kém ổn định hơn Isolation Forest. "Gốc UMN" chỉ hợp với video UMN.</p>
          </>
        )}
        <p className="note">Đổi mô hình giai đoạn 2 không cần học lại: mô hình mới học ngay từ các mẫu bình thường đã thu.</p>
      </div>

      <div className="stage-block">
        <div className="stage-title"><Icon name="refresh" size={14} /> Học mức bình thường</div>
        {a.learning || (!status.calibration.done && status.calibration.need > 0) ? (
          <div className="progress-wrap">
            <progress max={Math.max(a.need, 1)} value={a.have} aria-label="Tiến độ học" />
            <span className="mono small">{a.have}/{a.need} mẫu</span>
          </div>
        ) : (
          <p className="small">{status.calibration.done ? <span className="ok-text">Đã học xong</span> : <span className="muted">Chưa học</span>}</p>
        )}
        {canEdit && (
          <div className="row">
            <label className="field-inline grow">
              <input type="number" min={5} max={900} value={seconds} onChange={(e) => setSeconds(Number(e.target.value))}
                aria-label="Số giây học" />
              <span>giây</span>
            </label>
            <button className="btn" disabled={busy} onClick={() => act(() => api.calibrate(cid, seconds))}>Học lại</button>
          </div>
        )}
        <p className="note">Học trên đoạn camera bình thường. Video UMN: học khoảng 12 giây đầu (trước lúc mọi người bỏ chạy).</p>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  )
}
