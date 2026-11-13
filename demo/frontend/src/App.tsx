import { useEffect, useState } from 'react'
import { api } from './api'
import { AlertList } from './components/AlertList'
import { CountChart } from './components/CountChart'
import { ModelSwitch } from './components/ModelSwitch'
import { ModeSwitch } from './components/ModeSwitch'
import { PlaybackBar } from './components/PlaybackBar'
import { RulesPanel } from './components/RulesPanel'
import { SourcePanel } from './components/SourcePanel'
import { StatsPanel } from './components/StatsPanel'
import { VideoStage } from './components/VideoStage'
import { ZoneCanvas, ZoneToolbar, type ZoneTool } from './components/ZoneEditor'
import { useLiveStatus } from './hooks/useLiveStatus'
import type { EventRow, SeriesRow, ZoneSet } from './types'

const SERIES_MINUTES = 10
const CLIP_POLL_MS = 2000
const EMPTY_ZONES: ZoneSet = { roi: [], exclude: [] }

export default function App() {
  const { status, connected } = useLiveStatus()
  const run = status?.source?.run ?? null
  const tz = status?.source?.tz ?? 'UTC'

  // --- vùng giám sát ---
  const [zones, setZones] = useState<ZoneSet>(EMPTY_ZONES)
  const [draft, setDraft] = useState<ZoneSet | null>(null)     // khác null = đang vẽ
  const [tool, setTool] = useState<ZoneTool>('roi')
  const [zoneError, setZoneError] = useState<string | null>(null)

  // --- chuỗi số liệu và cảnh báo ---
  const [series, setSeries] = useState<SeriesRow[]>([])
  const [events, setEvents] = useState<EventRow[]>([])

  // Mỗi lần chạy mới: nạp lại vùng, chuỗi số liệu, cảnh báo
  useEffect(() => {
    setDraft(null)
    if (!run) {
      setSeries([])
      setEvents([])
      return
    }
    api.getZones().then(setZones)
    api.getSeries(SERIES_MINUTES).then(setSeries)
    api.getEvents().then(setEvents)
  }, [run])

  // Nối mẫu mới nhất vào biểu đồ
  useEffect(() => {
    if (!status?.sample_t) return
    const row: SeriesRow = { t: status.sample_t, roi: status.counts.roi, total: status.counts.total,
      speed: status.motion.speed, entropy: status.motion.entropy, counterflow: status.motion.counterflow }
    setSeries((prev) => {
      if (prev.length && prev[prev.length - 1].t >= row.t) return prev
      const cutoff = row.t - SERIES_MINUTES * 60
      return [...prev.filter((r) => r.t >= cutoff), row]
    })
  }, [status?.sample_t])

  // Có sự kiện mới: tải lại danh sách
  useEffect(() => {
    if (run && status?.latest_event_id) api.getEvents().then(setEvents)
  }, [run, status?.latest_event_id])

  // Còn sự kiện chưa có clip (clip ghi sau sự kiện vài giây): hỏi lại định kỳ
  const pendingClip = events.some((e) => !e.clip)
  useEffect(() => {
    if (!pendingClip) return
    const id = window.setInterval(() => api.getEvents().then(setEvents), CLIP_POLL_MS)
    return () => window.clearInterval(id)
  }, [pendingClip])

  const saveZones = async () => {
    if (!draft) return
    try {
      setZones(await api.putZones(draft))
      setDraft(null)
      setZoneError(null)
    } catch (e) {
      setZoneError((e as Error).message)
    }
  }

  const source = status?.source
  return (
    <div className="app">
      <header className="topbar">
        <h1>Giám sát đám đông</h1>
        <span className={`dot ${connected ? 'on' : ''}`} title={connected ? 'Đã kết nối máy chủ' : 'Mất kết nối máy chủ'} />
      </header>

      <SourcePanel status={status} />

      <main className={`layout ${source ? '' : 'single'}`}>
        <div className="left">
          <VideoStage status={status}>
            {draft && <ZoneCanvas zones={draft} tool={tool} onChange={setDraft} />}
          </VideoStage>

          {source && (
            <div className="controls">
              <ModeSwitch mode={status?.mode} />
              <ModelSwitch active={status?.model} />
              {draft
                ? <ZoneToolbar tool={tool} onTool={setTool} onSave={saveZones} onCancel={() => setDraft(null)}
                    onClear={() => setDraft(EMPTY_ZONES)} />
                : <button onClick={() => setDraft(zones)}>Vẽ vùng giám sát / loại trừ</button>}
            </div>
          )}
          {zoneError && <p className="error">{zoneError}</p>}
          {source && !source.live && <PlaybackBar source={source} />}
          {source && <CountChart series={series} events={events} tz={tz}
            limit={status?.thresholds.overcrowd ?? status?.thresholds.count_limit ?? null} />}
        </div>

        {status && source && (
          <aside className="right">
            <StatsPanel status={status} />
            <RulesPanel status={status} />
            <AlertList events={events} tz={tz} />
          </aside>
        )}
      </main>
    </div>
  )
}
