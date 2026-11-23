import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { CameraStrip } from '../components/CameraStrip'
import { AlertsCard, KpiCard, ZonesCard } from '../components/LivePanels'
import { PipelineCard } from '../components/PipelineCard'
import { RulesCard } from '../components/RulesCard'
import { Timeline } from '../components/Timeline'
import { VideoPanel, type ZoneTool } from '../components/VideoPanel'
import type { CameraSummary, EventRow, LiveMessage, Me, SeriesRow, ZoneSet } from '../types'

const SERIES_MINUTES = 10
const CLIP_POLL_MS = 2000
const EMPTY_ZONES: ZoneSet = { roi: [], exclude: [], roi_meta: [] }
const STORE_KEY = 'crowd.camera'

function savedCamera(): number | null {
  try {
    const v = localStorage.getItem(STORE_KEY)
    return v ? Number(v) : null
  } catch {
    return null
  }
}

/**
 * Trang Giám sát: dải camera ở trên; camera chính ở dưới với bố cục phòng điều khiển
 * (trái: mô hình và luật · giữa: video và diễn biến · phải: số liệu, vùng, cảnh báo).
 */
export function MonitorPage({ me, live, cameras, onCamerasChanged }: {
  me: Me; live: LiveMessage | null; cameras: CameraSummary[]; onCamerasChanged: () => void
}) {
  const canEdit = me.role === 'admin'
  const runningIds = Object.keys(live?.cameras ?? {}).map(Number)
  const [picked, setPicked] = useState<number | null>(savedCamera)
  const selected = picked != null && runningIds.includes(picked) ? picked : runningIds[0] ?? null
  const status = selected != null ? live?.cameras[selected] ?? null : null
  const run = status?.source?.run ?? null
  const tz = status?.source?.tz ?? 'UTC'

  const select = (id: number) => {
    setPicked(id)
    try {
      localStorage.setItem(STORE_KEY, String(id))
    } catch { /* trình duyệt chặn lưu trữ: chỉ không nhớ lựa chọn */ }
  }

  const [zones, setZones] = useState<ZoneSet>(EMPTY_ZONES)
  const [draft, setDraft] = useState<ZoneSet | null>(null)
  const [tool, setTool] = useState<ZoneTool>('roi')
  const [zoneError, setZoneError] = useState<string | null>(null)
  const [series, setSeries] = useState<SeriesRow[]>([])
  const [events, setEvents] = useState<EventRow[]>([])

  const loadEvents = useCallback(() => {
    if (selected != null) api.events({ camera_id: selected, limit: 30 }).then((p) => setEvents(p.rows))
  }, [selected])

  // Đổi camera hoặc lần chạy mới: nạp lại vùng, chuỗi số liệu, cảnh báo
  useEffect(() => {
    setDraft(null)
    setSeries([])
    setEvents([])
    if (selected == null || !run) return
    api.getZones(selected).then(setZones)
    api.getSeries(selected, SERIES_MINUTES).then(setSeries)
    loadEvents()
  }, [selected, run, loadEvents])

  // Nối mẫu mới nhất vào biểu đồ
  useEffect(() => {
    if (!status?.sample_t) return
    const row: SeriesRow = { t: status.sample_t, roi: status.counts.roi, total: status.counts.total,
      anomaly: status.anomaly.score, anomaly_limit: status.anomaly.limit }
    setSeries((prev) => {
      if (prev.length && prev[prev.length - 1].t >= row.t) return prev
      const cutoff = row.t - SERIES_MINUTES * 60
      return [...prev.filter((r) => r.t >= cutoff), row]
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status?.sample_t])

  useEffect(() => {
    if (status?.latest_event_id) loadEvents()
  }, [status?.latest_event_id, loadEvents])

  // Clip được ghi xong vài giây sau sự kiện: hỏi lại định kỳ tới khi có
  const pendingClip = events.some((e) => !e.clip && !e.purged)
  useEffect(() => {
    if (!pendingClip) return
    const id = window.setInterval(loadEvents, CLIP_POLL_MS)
    return () => window.clearInterval(id)
  }, [pendingClip, loadEvents])

  const saveZones = async (z: ZoneSet | null = draft) => {
    if (!z || selected == null) return
    try {
      setZones(await api.putZones(selected, z))
      setDraft(null)
      setZoneError(null)
    } catch (e) {
      setZoneError((e as Error).message)
    }
  }

  return (
    <div className="monitor">
      <CameraStrip cameras={cameras} live={live} selected={selected} onSelect={select} canEdit={canEdit}
        onChanged={onCamerasChanged} />

      <div className="app">
        <aside className="rail rail-left" aria-label="Mô hình và luật">
          {status ? (
            <>
              <PipelineCard status={status} canEdit={canEdit} />
              <RulesCard key={selected ?? 0} status={status} canEdit={canEdit} />
            </>
          ) : (
            <section className="card">
              <h2>Đề tài</h2>
              <ol className="steps">
                <li><b>Giai đoạn 1 · Đếm người:</b> MobileCount + Mask ước lượng bản đồ mật độ và vùng có người.</li>
                <li><b>Khoanh vùng:</b> vùng giám sát có tên và sức chứa, vùng loại trừ (đèn, biển hiệu).</li>
                <li><b>Giai đoạn 2 · Phát hiện bất thường:</b> mô hình học chuyển động bình thường của camera, cảnh báo khi lệch.</li>
                <li><b>Lịch sử:</b> mọi cảnh báo lưu ảnh, clip; xem lại và thống kê ở các trang bên trên.</li>
              </ol>
            </section>
          )}
        </aside>

        <main className="center">
          <VideoPanel status={status} canEdit={canEdit} draft={draft} tool={tool} onDraft={setDraft} onTool={setTool}
            onStartEdit={() => setDraft(zones)} onSave={() => saveZones()} onCancel={() => setDraft(null)}
            zoneError={zoneError} />
          <Timeline series={series} events={events} tz={tz} limit={status?.anomaly.limit ?? null} />
        </main>

        <aside className="rail rail-right" aria-label="Số liệu trực tiếp và cảnh báo">
          {status && (
            <>
              <KpiCard status={status} />
              <ZonesCard status={status} zones={draft ?? zones} editing={!!draft} canEdit={canEdit}
                onChange={setDraft} onSave={(z) => saveZones(z)} />
              <AlertsCard events={events} tz={tz} onChanged={loadEvents} />
            </>
          )}
        </aside>
      </div>
    </div>
  )
}
