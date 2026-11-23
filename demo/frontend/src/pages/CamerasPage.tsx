import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { Icon } from '../components/Icon'
import { TIMEZONES, num } from '../format'
import type { CameraKind, CameraSummary, LiveMessage } from '../types'

const ACCEPT = '.mp4,.webm,.mkv,.avi,.mov,.ts'
type Form = { id: number | null; name: string; kind: CameraKind; source: string; tz: string; autostart: boolean }
const EMPTY: Form = { id: null, name: '', kind: 'youtube', source: '', tz: 'Europe/Dublin', autostart: false }

/** Trang Camera (quản trị): thêm, sửa, xóa, bật/tắt camera; tải video lên. */
export function CamerasPage({ cameras, live, onChanged }: {
  cameras: CameraSummary[]; live: LiveMessage | null; onChanged: () => void
}) {
  const [form, setForm] = useState<Form | null>(null)
  const [videos, setVideos] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    api.listVideos().then(setVideos)
  }, [])

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await fn()
      onChanged()
      return true
    } catch (e) {
      setError((e as Error).message)
      return false
    } finally {
      setBusy(false)
    }
  }

  const save = async () => {
    if (!form) return
    const body = { name: form.name, kind: form.kind, source: form.source, tz: form.tz, autostart: form.autostart }
    const ok = await act(() => (form.id == null ? api.createCamera(body) : api.updateCamera(form.id, body)))
    if (ok) setForm(null)
  }

  const upload = (file: File | undefined) => file && act(async () => {
    const { name } = await api.uploadVideo(file)
    setVideos(await api.listVideos())
    setForm((f) => (f && f.kind === 'file' ? { ...f, source: name } : f))
  })

  const max = live?.max_cameras ?? 4
  const running = Object.keys(live?.cameras ?? {}).length

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h2>Camera</h2>
          <p className="muted small">{cameras.length} camera · {running}/{max} đang chạy (giới hạn phần cứng CPU)</p>
        </div>
        <div className="row">
          <button className="btn" onClick={() => fileInput.current?.click()} disabled={busy}>
            <Icon name="upload" size={14} /> Tải video lên
          </button>
          <input ref={fileInput} type="file" accept={ACCEPT} hidden onChange={(e) => upload(e.target.files?.[0])} />
          <button className="btn btn-primary" onClick={() => setForm({ ...EMPTY })}><Icon name="plus" size={14} /> Thêm camera</button>
        </div>
      </header>
      {error && <p className="error" role="alert">{error}</p>}

      {form && (
        <section className="card form-card" aria-label={form.id == null ? 'Thêm camera' : 'Sửa camera'}>
          <h2>{form.id == null ? 'Thêm camera' : `Sửa camera #${form.id}`}</h2>
          <div className="form-grid">
            <label className="field">
              <span>Tên camera</span>
              <input value={form.name} maxLength={80} onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="Ví dụ: Cổng chính" autoFocus />
            </label>
            <div className="field">
              <span>Loại nguồn</span>
              <div className="segmented">
                <button className={form.kind === 'youtube' ? 'on' : ''} onClick={() => setForm({ ...form, kind: 'youtube', source: '' })}>
                  <Icon name="live" size={14} /> Livestream
                </button>
                <button className={form.kind === 'file' ? 'on' : ''} onClick={() => setForm({ ...form, kind: 'file', source: videos[0] ?? '' })}>
                  <Icon name="video" size={14} /> Video có sẵn
                </button>
              </div>
            </div>
            {form.kind === 'youtube' ? (
              <label className="field">
                <span>Link livestream YouTube</span>
                <input value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })}
                  placeholder="https://www.youtube.com/watch?v=…" />
              </label>
            ) : (
              <label className="field">
                <span>Video</span>
                <select value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })}>
                  {videos.length === 0 && <option value="">Chưa có video, hãy tải lên</option>}
                  {videos.map((v) => <option key={v} value={v}>{v}</option>)}
                </select>
              </label>
            )}
            <label className="field">
              <span>Múi giờ camera</span>
              <select value={form.tz} onChange={(e) => setForm({ ...form, tz: e.target.value })}>
                {TIMEZONES.map((z) => <option key={z.value} value={z.value}>{z.label}</option>)}
              </select>
            </label>
            <label className="switch">
              <input type="checkbox" checked={form.autostart} onChange={(e) => setForm({ ...form, autostart: e.target.checked })} />
              <span className="track" aria-hidden="true" />
              <span>Tự chạy khi khởi động server</span>
            </label>
          </div>
          <div className="row">
            <button className="btn btn-ghost" onClick={() => setForm(null)}>Hủy</button>
            <button className="btn btn-primary" disabled={busy || !form.name || !form.source} onClick={save}>
              <Icon name="check" size={14} /> {busy ? 'Đang lưu…' : 'Lưu'}
            </button>
          </div>
          <p className="note">Vùng giám sát, sức chứa, luật và mô hình của từng camera chỉnh ở trang Giám sát khi camera đang chạy.</p>
        </section>
      )}

      <section className="card table-card">
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Tên</th><th scope="col">Nguồn</th><th scope="col">Múi giờ</th><th scope="col">Trạng thái</th>
                <th scope="col">Tự chạy</th><th scope="col"><span className="sr-only">Thao tác</span></th>
              </tr>
            </thead>
            <tbody>
              {cameras.map((c) => {
                const st = live?.cameras[c.id]
                return (
                  <tr key={c.id}>
                    <td><b>{c.name}</b></td>
                    <td className="small"><Icon name={c.kind === 'youtube' ? 'live' : 'video'} size={13} /> <span className="break">{c.source}</span></td>
                    <td className="small">{c.tz}</td>
                    <td className="small">
                      {st ? (st.state === 'error'
                        ? <span className="status-new">Mất tín hiệu</span>
                        : <span className="status-ok">Đang chạy · {num(st.perf.analysis_fps, 1)} lần/s</span>)
                        : <span className="muted">Đang tắt</span>}
                    </td>
                    <td>{c.autostart ? <Icon name="check" size={14} className="ok-text" /> : <span className="muted">–</span>}</td>
                    <td className="actions">
                      <button className="btn btn-sm" disabled={busy}
                        onClick={() => act(() => (st ? api.stopCamera(c.id) : api.startCamera(c.id)))}>
                        <Icon name={st ? 'stop' : 'play'} size={13} /> {st ? 'Tắt' : 'Bật'}
                      </button>
                      <button className="btn btn-sm btn-ghost" aria-label={`Sửa ${c.name}`}
                        onClick={() => setForm({ id: c.id, name: c.name, kind: c.kind, source: c.source, tz: c.tz, autostart: c.autostart })}>
                        <Icon name="edit" size={13} />
                      </button>
                      <button className="btn btn-sm btn-ghost danger" aria-label={`Xóa ${c.name}`} disabled={busy}
                        onClick={() => window.confirm(`Xóa camera "${c.name}"? Lịch sử cảnh báo và thống kê vẫn được giữ.`)
                          && act(() => api.deleteCamera(c.id))}>
                        <Icon name="trash" size={13} />
                      </button>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  )
}
