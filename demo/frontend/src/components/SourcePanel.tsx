import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { TIMEZONES } from '../format'
import type { Status } from '../types'

const ACCEPT = '.mp4,.webm,.mkv,.avi,.mov,.ts'
const DEFAULT_URL = 'https://www.youtube.com/watch?v=3nyPER2kzqk'

type Tab = 'file' | 'youtube'

/** Chọn nguồn: video có sẵn (chọn hoặc tải lên) hoặc link livestream YouTube. */
export function SourcePanel({ status }: { status: Status | null }) {
  const [tab, setTab] = useState<Tab>('file')
  const [videos, setVideos] = useState<string[]>([])
  const [video, setVideo] = useState('')
  const [url, setUrl] = useState(DEFAULT_URL)
  const [tz, setTz] = useState('Europe/Dublin')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  const refreshVideos = async (select?: string) => {
    const list = await api.listVideos()
    setVideos(list)
    setVideo((current) => select ?? (list.includes(current) ? current : list[0] ?? ''))
  }

  useEffect(() => {
    refreshVideos().catch((e: Error) => setError(e.message))
  }, [])

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true)
    setError(null)
    try {
      await action()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const upload = (file: File | undefined) =>
    file && run(async () => {
      const { name } = await api.uploadVideo(file)
      await refreshVideos(name)
    })

  const running = status?.state === 'running'
  const shownError = error ?? (status?.state === 'error' ? status.error : null)

  return (
    <section className="source-panel">
      <div className="tabs">
        <button className={tab === 'file' ? 'active' : ''} onClick={() => setTab('file')}>Video có sẵn</button>
        <button className={tab === 'youtube' ? 'active' : ''} onClick={() => setTab('youtube')}>Livestream YouTube</button>
      </div>

      {tab === 'file' ? (
        <div className="row">
          <select value={video} onChange={(e) => setVideo(e.target.value)} disabled={busy}>
            {videos.length === 0 && <option value="">Chưa có video, hãy tải lên</option>}
            {videos.map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
          <button onClick={() => fileInput.current?.click()} disabled={busy}>Tải lên…</button>
          <input ref={fileInput} type="file" accept={ACCEPT} hidden onChange={(e) => upload(e.target.files?.[0])} />
          <button className="primary" disabled={busy || !video} onClick={() => run(() => api.startFile(video, tz))}>
            Phát
          </button>
        </div>
      ) : (
        <div className="row">
          <input className="grow" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://www.youtube.com/watch?v=…" />
          <button className="primary" disabled={busy || !url} onClick={() => run(() => api.startYoutube(url, tz))}>
            {busy ? 'Đang kết nối…' : 'Kết nối'}
          </button>
        </div>
      )}

      <div className="row">
        <label>
          Múi giờ camera
          <select value={tz} onChange={(e) => setTz(e.target.value)}>
            {TIMEZONES.map((z) => <option key={z.value} value={z.value}>{z.label}</option>)}
          </select>
        </label>
        {running && <button onClick={() => run(api.stop)}>Dừng</button>}
        {running && status?.source && <span className="muted">Đang chạy: {status.source.label}</span>}
      </div>
      {shownError && <p className="error">{shownError}</p>}
    </section>
  )
}
