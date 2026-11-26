import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { CameraStrip } from '../components/CameraStrip'
import { Icon } from '../components/Icon'
import { AlertsCard, KpiCard, ZonesCard } from '../components/LivePanels'
import { PipelineCard } from '../components/PipelineCard'
import { QuickAddCard } from '../components/QuickAddCard'
import { RulesCard } from '../components/RulesCard'
import { Timeline } from '../components/Timeline'
import { VideoPanel, type ZoneTool } from '../components/VideoPanel'
import type { CameraSummary, EventRow, LiveMessage, Me, SeriesRow, ZoneSet } from '../types'

const SERIES_MINUTES = 10
const CLIP_POLL_MS = 2000
const EMPTY_ZONES: ZoneSet = { roi: [], exclude: [], roi_meta: [] }
const STORE_KEY = 'crowd.camera'
type ConfigTab = 'models' | 'rules' | 'zones'
const CONFIG_TABS: { id: ConfigTab; label: string }[] = [
  { id: 'models', label: 'Mô hình' }, { id: 'rules', label: 'Cảnh báo' }, { id: 'zones', label: 'Vùng' },
]

function savedCamera(): number | null {
  try {
    const v = localStorage.getItem(STORE_KEY)
    return v ? Number(v) : null
  } catch {
    return null
  }
}

/**
 * Trang Giám sát, vừa khít màn hình (không cuộn cả trang, chỉ từng khung tự cuộn).
 * Trái: thanh camera, video, diễn biến. Phải: số liệu, vùng, cảnh báo; nút "Cấu hình" thay cột phải bằng
 * ba mục mô hình, luật, vùng.
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
  const [config, setConfig] = useState<ConfigTab | null>(null)
  const [adding, setAdding] = useState(false)
  const [starting, setStarting] = useState<string | null>(null)
  const [series, setSeries] = useState<SeriesRow[]>([])
  const [events, setEvents] = useState<EventRow[]>([])

  const loadEvents = useCallback(() => {
    if (selected != null) api.events({ camera_id: selected, limit: 30 }).then((p) => setEvents(p.rows))
  }, [selected])

  // Đổi camera hoặc lần chạy mới: nạp lại vùng, chuỗi số liệu, cảnh báo
  useEffect(() => {
    setDraft(null)
    setConfig(null)
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

  const startZones = () => {
    setConfig(null)
    setDraft(zones)
  }

  return (
    <div className="monitor">
      <main className="monitor-main">
        <CameraStrip cameras={cameras} live={live} selected={selected} onSelect={select} canEdit={canEdit}
          onChanged={onCamerasChanged} onAdd={() => setAdding(true)} onStarting={setStarting} />
        <VideoPanel starting={starting} status={status} canEdit={canEdit} configOpen={config != null}
          onConfig={() => setConfig(config ? null : 'models')} draft={draft} tool={tool} onDraft={setDraft} onTool={setTool}
          onStartEdit={startZones} onSave={() => saveZones()} onCancel={() => setDraft(null)} zoneError={zoneError} />
        <Timeline series={series} events={events} tz={tz} limit={status?.anomaly.limit ?? null} />
      </main>

      <aside className="monitor-side" aria-label={config ? 'Cấu hình camera' : 'Số liệu trực tiếp và cảnh báo'}>
        {status && config && !draft ? (
          <>
            <div className="side-head">
              <div className="segmented" role="tablist" aria-label="Mục cấu hình">
                {CONFIG_TABS.map((t) => (
                  <button key={t.id} role="tab" aria-selected={config === t.id} className={config === t.id ? 'on' : ''}
                    onClick={() => setConfig(t.id)}>{t.label}</button>
                ))}
              </div>
              <button className="btn btn-ghost btn-icon" onClick={() => setConfig(null)} aria-label="Đóng cấu hình">
                <Icon name="x" />
              </button>
            </div>
            <div className="side-scroll">
              {config === 'models' && <PipelineCard status={status} canEdit={canEdit} />}
              {config === 'rules' && <RulesCard key={selected ?? 0} status={status} canEdit={canEdit} />}
              {config === 'zones' && (
                <>
                  {canEdit && <button className="btn btn-primary" onClick={startZones}><Icon name="zone" size={14} /> Vẽ vùng trên video</button>}
                  <ZonesCard status={status} zones={zones} editing={false} canEdit={canEdit}
                    onChange={setDraft} onSave={(z) => saveZones(z)} />
                </>
              )}
            </div>
          </>
        ) : status ? (
          <>
            <KpiCard status={status} />
            {(draft || zones.roi.length > 0) && (
              <div className="side-zones">
                <ZonesCard status={status} zones={draft ?? zones} editing={!!draft} canEdit={canEdit}
                  onChange={setDraft} onSave={(z) => saveZones(z)} />
              </div>
            )}
            <AlertsCard events={events} tz={tz} canJudge={canEdit} onChanged={loadEvents} />
          </>
        ) : (
          <p className="muted small side-empty">Chưa có camera đang chạy. Số liệu và cảnh báo sẽ hiện ở đây.</p>
        )}
      </aside>

      {adding && <QuickAddCard onAdded={onCamerasChanged} onSelect={select} onClose={() => setAdding(false)} />}
    </div>
  )
}
