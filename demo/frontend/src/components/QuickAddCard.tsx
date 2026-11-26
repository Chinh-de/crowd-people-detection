import { useRef, useState } from 'react'
import { api } from '../api'
import type { CameraKind } from '../types'
import { Icon } from './Icon'

const ACCEPT = '.mp4,.webm,.mkv,.avi,.mov,.ts'

/** Thêm nhanh camera từ link YouTube hoặc file video trên máy, rồi bật và xem luôn. */
export function QuickAddCard({ onAdded, onSelect, onClose }: {
  onAdded: () => void; onSelect: (id: number) => void; onClose: () => void
}) {
  const [kind, setKind] = useState<CameraKind>('youtube')
  const [url, setUrl] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const ready = kind === 'youtube' ? !!url.trim() : !!file

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!ready || busy) return
    setBusy(true)
    setError(null)
    try {
      const source = kind === 'youtube' ? url.trim() : (await api.uploadVideo(file!)).name
      const fallback = kind === 'youtube' ? 'Camera YouTube' : source.replace(/\.[^.]+$/, '')
      const cam = await api.createCamera({ name: (name.trim() || fallback).slice(0, 80), kind, source,
        tz: kind === 'youtube' ? 'Europe/Dublin' : 'Asia/Ho_Chi_Minh', autostart: false })
      setUrl('')
      setFile(null)
      setName('')
      if (fileInput.current) fileInput.current.value = ''
      try {
        await api.startCamera(cam.id)
        onSelect(cam.id)
        onClose()
      } catch (err) {
        setError(`Đã thêm camera nhưng chưa bật được: ${(err as Error).message}`)
      }
      onAdded()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="modal" role="dialog" aria-modal="true" aria-label="Thêm camera"
      onKeyDown={(e) => e.key === 'Escape' && onClose()}>
    <section className="modal-body modal-narrow">
      <header className="card-head">
        <h2>Thêm camera</h2>
        <button type="button" className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Đóng"><Icon name="x" /></button>
      </header>
      <form className="quick-add" onSubmit={submit}>
        <div className="segmented" role="radiogroup" aria-label="Loại nguồn">
          <button type="button" role="radio" aria-checked={kind === 'youtube'} className={kind === 'youtube' ? 'on' : ''}
            onClick={() => setKind('youtube')}><Icon name="live" size={14} /> Link YouTube</button>
          <button type="button" role="radio" aria-checked={kind === 'file'} className={kind === 'file' ? 'on' : ''}
            onClick={() => setKind('file')}><Icon name="video" size={14} /> File video</button>
        </div>
        {kind === 'youtube' ? (
          <label className="field">
            <span>Link YouTube</span>
            <input type="url" autoFocus value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.youtube.com/watch?v=…" />
          </label>
        ) : null}
        {/* luôn có trong DOM để giữ file đã chọn khi đổi qua lại giữa hai loại nguồn */}
        <label className="field" hidden={kind !== 'file'}>
          <span>File video trên máy</span>
          <input ref={fileInput} type="file" accept={ACCEPT} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        </label>
        <label className="field">
          <span>Tên camera (không bắt buộc)</span>
          <input value={name} maxLength={80} onChange={(e) => setName(e.target.value)} />
        </label>
        <button className="btn btn-primary" disabled={!ready || busy}>
          <Icon name="plus" size={14} /> {busy ? (kind === 'file' ? 'Đang tải lên…' : 'Đang kết nối…') : 'Thêm và bật'}
        </button>
        {error && <p className="error small" role="alert">{error}</p>}
      </form>
    </section>
    </div>
  )
}
