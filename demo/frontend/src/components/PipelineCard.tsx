import { useEffect, useState } from 'react'
import { api } from '../api'
import { num } from '../format'
import type { AnomalyModels, CountModelInfo, Status } from '../types'
import { Icon } from './Icon'

const KIND_LABEL = { speed: 'Mốc so sánh', if: 'Isolation Forest · học tại chỗ', ae: 'Autoencoder · đã train trên UMN' }

/**
 * Mô hình của camera đang xem, theo hai giai đoạn của đề tài.
 * Giai đoạn 1 đếm người (MAE/MSE trên ShanghaiTech B); giai đoạn 2 phát hiện bất thường (AUC trên UMN).
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
  const groups = (['speed', 'if', 'ae'] as const).map((k) => [k, anomaly?.models.filter((m) => m.kind === k) ?? []] as const)

  return (
    <section className="card" aria-labelledby="pipe-title">
      <header className="card-head">
        <h2 id="pipe-title"><Icon name="cpu" /> Mô hình</h2>
        {!canEdit && <span className="muted small">chỉ xem</span>}
      </header>

      <div className="stage-block">
        <div className="stage-title"><span className="stage-no">1</span> Đếm người <span className="muted">MAE / MSE · ShanghaiTech B</span></div>
        <div className="options" role="radiogroup" aria-label="Mô hình đếm người">
          {counters.map((m) => {
            const on = status.model === m.name
            return (
              <button key={m.name} role="radio" aria-checked={on} disabled={locked || !m.available || on}
                className={`option ${on ? 'on' : ''}`} onClick={() => act(() => api.setModel(cid, m.name))}>
                <span className="option-label">{m.label}</span>
                <span className="option-metric mono">{num(m.mae, 2)} / {num(m.mse, 2)}</span>
                {!m.available && <span className="muted small">thiếu file</span>}
              </button>
            )
          })}
        </div>
      </div>

      <div className="stage-block">
        <div className="stage-title"><span className="stage-no">2</span> Phát hiện bất thường <span className="muted">AUC · UMN</span></div>
        {groups.map(([kind, list]) => list.length > 0 && (
          <div key={kind} className="option-group">
            <div className="group-label">{KIND_LABEL[kind]}</div>
            <div className="options" role="radiogroup" aria-label={KIND_LABEL[kind]}>
              {list.map((m) => {
                const on = a.model === m.name
                return (
                  <button key={m.name} role="radio" aria-checked={on} disabled={locked || !m.available || on}
                    className={`option ${on ? 'on' : ''}`} onClick={() => act(() => api.setAnomalyModel(cid, m.name))}>
                    <span className="option-label">{m.label}</span>
                    <span className="auc" aria-label={`AUC ${num(m.umn_auc, 3)}`}>
                      <span className="auc-bar"><span style={{ width: `${Math.max(0, (m.umn_auc - 0.8) / 0.2) * 100}%` }} /></span>
                      <span className="mono">{num(m.umn_auc, 3)}</span>
                    </span>
                    {!m.available && <span className="muted small">thiếu file trọng số</span>}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
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
