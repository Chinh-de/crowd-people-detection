import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { RULE_LABELS, duration } from '../format'
import type { Point, Polygon, Status, ViewMode, ZoneSet } from '../types'
import { Icon } from './Icon'

export type ZoneTool = 'roi' | 'exclude'

const MODES: { value: ViewMode; label: string }[] = [
  { value: 'video', label: 'Video' },
  { value: 'overlay', label: 'Nhận diện' },
  { value: 'gray', label: 'Nền xám' },
  { value: 'overlay_only', label: 'Chỉ lớp phủ' },
]
const COLORS = { roi: '#22C55E', exclude: '#EF4444', draft: '#F59E0B' }
const CLOSE_RADIUS = 12

/** Khung video trung tâm: luồng MJPEG đã vẽ lớp nhận diện, chế độ hiển thị, vẽ vùng và điều khiển phát. */
export function VideoPanel({ starting, status, canEdit, configOpen, onConfig, draft, tool, onDraft, onTool, onStartEdit, onSave, onCancel, zoneError }: {
  starting: string | null      // tên camera đang được bật (đang mở nguồn)
  status: Status | null
  canEdit: boolean
  configOpen: boolean
  onConfig: () => void
  draft: ZoneSet | null
  tool: ZoneTool
  onDraft: (z: ZoneSet) => void
  onTool: (t: ZoneTool) => void
  onStartEdit: () => void
  onSave: () => void
  onCancel: () => void
  zoneError: string | null
}) {
  const src = status?.source
  const alerting = (status?.active_alerts.length ?? 0) > 0
  const frame = useRef<HTMLDivElement>(null)
  const [full, setFull] = useState(false)
  const [shownRun, setShownRun] = useState<string | null>(null)     // lần chạy đã nhận được khung hình đầu tiên

  useEffect(() => {
    const onChange = () => setFull(document.fullscreenElement === frame.current)
    document.addEventListener('fullscreenchange', onChange)
    return () => document.removeEventListener('fullscreenchange', onChange)
  }, [])

  const toggleFull = () => {
    if (document.fullscreenElement) document.exitFullscreen()
    else frame.current?.requestFullscreen()
  }

  // Phím F: bật/tắt toàn màn hình (bỏ qua khi đang gõ trong ô nhập)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName
      if ((e.key === 'f' || e.key === 'F') && src && !['INPUT', 'SELECT', 'TEXTAREA'].includes(tag)) toggleFull()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [src])

  return (
    <section className="video-panel" aria-label="Video giám sát">
      <div className="video-toolbar">
        <div className="segmented" role="radiogroup" aria-label="Chế độ hiển thị">
          {MODES.map((m) => (
            <button key={m.value} role="radio" aria-checked={status?.mode === m.value}
              className={status?.mode === m.value ? 'on' : ''} disabled={!src} onClick={() => status && api.setMode(status.camera_id, m.value)}>
              {m.label}
            </button>
          ))}
        </div>
        <div className="spacer" />
        {src && status && (
          <span className="muted small" title="Video được phát trễ để lớp phủ khớp với hình">
            Video trễ {(status.perf.delay_ms / 1000).toFixed(1)} s
          </span>
        )}
        {draft ? (
          <>
            <div className="segmented" role="radiogroup" aria-label="Loại vùng">
              <button role="radio" aria-checked={tool === 'roi'} className={tool === 'roi' ? 'on' : ''} onClick={() => onTool('roi')}>
                <span className="swatch swatch-roi" /> Vùng giám sát
              </button>
              <button role="radio" aria-checked={tool === 'exclude'} className={tool === 'exclude' ? 'on' : ''} onClick={() => onTool('exclude')}>
                <span className="swatch swatch-exclude" /> Vùng loại trừ
              </button>
            </div>
            <button className="btn btn-ghost" onClick={() => onDraft({ roi: [], exclude: [], roi_meta: [] })}>
              <Icon name="trash" size={14} /> Xóa hết
            </button>
            <button className="btn btn-ghost" onClick={onCancel}>Hủy</button>
            <button className="btn btn-primary" onClick={onSave}><Icon name="check" size={14} /> Lưu vùng</button>
          </>
        ) : (
          canEdit && <button className="btn" disabled={!src} onClick={onStartEdit}><Icon name="zone" size={14} /> Vẽ vùng</button>
        )}
        {!draft && (
          <button className={`btn ${configOpen ? 'btn-on' : ''}`} disabled={!src} onClick={onConfig} aria-expanded={configOpen}>
            <Icon name="sliders" size={14} /> Cấu hình
          </button>
        )}
        <button className="btn btn-icon" disabled={!src} onClick={toggleFull}
          aria-label={full ? 'Thoát toàn màn hình (F)' : 'Toàn màn hình (F)'} title={full ? 'Thoát toàn màn hình (F)' : 'Toàn màn hình (F)'}>
          <Icon name={full ? 'shrink' : 'expand'} />
        </button>
      </div>

      <div className="video-frame" ref={frame}>
        {src ? (
          <div className={`stage ${alerting ? 'alerting' : ''}`}
            style={{ '--ar': `${src.size[0]} / ${src.size[1]}` } as React.CSSProperties}
            onDoubleClick={draft ? undefined : toggleFull}>
            {/* đổi key khi đổi lần chạy để trình duyệt mở lại luồng */}
            <img key={src.run} src={api.streamUrl(status!.camera_id, src.run)} alt={`Video giám sát: ${src.label}`} draggable={false}
              onLoad={() => setShownRun(src.run)} />
            {shownRun !== src.run && status!.state !== 'error' && (
              <Loading text="Đang chờ hình đầu tiên…" note="Video được phát trễ vài giây để lớp phủ khớp với hình." />
            )}
            {draft && <ZoneCanvas zones={draft} tool={tool} onChange={onDraft} />}
            {full && alerting && (
              <div className="stage-alert" role="status">
                <Icon name="alert" size={16} /> Đang cảnh báo · {status!.active_alerts.map((r) => RULE_LABELS[r]).join(', ')}
              </div>
            )}
            {status?.anomaly.learning && (
              <div className="stage-badge" role="status">
                <Icon name="refresh" size={14} /> Đang học mức bình thường {status.anomaly.have}/{status.anomaly.need}
              </div>
            )}
          </div>
        ) : starting ? (
          <Loading text={`Đang bật camera "${starting}"…`} note="Đang mở nguồn video. Livestream YouTube có thể mất lâu hơn." />
        ) : (
          <div className="stage-empty">
            <Icon name="video" size={40} />
            <p>Chưa có camera nào đang chạy.</p>
            <p className="muted small">Bật camera ở thanh phía trên, hoặc bấm "Thêm" để thêm camera mới.</p>
          </div>
        )}
      </div>

      {draft && <p className="hint">Click để thêm điểm · double-click hoặc click lại điểm đầu để đóng vùng · Esc hủy vùng đang vẽ · click phải lên vùng để xóa. Đặt tên, sức chứa và chiều đi ở bảng "Vùng giám sát" bên phải.</p>}
      {zoneError && <p className="error" role="alert">{zoneError}</p>}
      {src && !src.live && <PlaybackBar status={status!} />}
    </section>
  )
}

function Loading({ text, note }: { text: string; note: string }) {
  return (
    <div className="stage-loading" role="status">
      <span className="spinner" aria-hidden="true" />
      <p>{text}</p>
      <p className="muted small">{note}</p>
    </div>
  )
}

function PlaybackBar({ status }: { status: Status }) {
  const src = status.source!
  const pos = src.position_s ?? 0
  const total = src.duration_s ?? 0
  return (
    <div className="playback">
      <button className="btn btn-icon" onClick={() => api.playback(status.camera_id, src.paused ? 'play' : 'pause')}
        aria-label={src.paused ? 'Phát' : 'Tạm dừng'}>
        <Icon name={src.paused ? 'play' : 'pause'} />
      </button>
      <input type="range" min={0} max={Math.max(total, 1)} step={0.5} value={pos}
        onChange={(e) => api.playback(status.camera_id, 'seek', Number(e.target.value))} aria-label="Tua video" />
      <span className="mono small">{duration(pos)} / {duration(total)}</span>
    </div>
  )
}

/**
 * Lớp vẽ vùng đặt chồng lên video, tọa độ chuẩn hóa 0–1.
 * Click: thêm điểm · double-click hoặc click lại điểm đầu: đóng vùng · Esc: hủy · click phải: xóa vùng.
 */
function ZoneCanvas({ zones, tool, onChange }: { zones: ZoneSet; tool: ZoneTool; onChange: (z: ZoneSet) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null)
  const [draft, setDraft] = useState<Polygon>([])
  const [size, setSize] = useState({ w: 1, h: 1 })

  useEffect(() => {
    const el = canvas.current!
    const ro = new ResizeObserver(([entry]) => setSize({ w: entry.contentRect.width, h: entry.contentRect.height }))
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setDraft([])
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    const el = canvas.current!
    el.width = size.w
    el.height = size.h
    const ctx = el.getContext('2d')!
    ctx.clearRect(0, 0, size.w, size.h)
    const toPx = ([x, y]: Point): Point => [x * size.w, y * size.h]
    const drawPoly = (poly: Polygon, color: string, fill: boolean, closed = true, label?: string) => {
      if (poly.length === 0) return
      ctx.beginPath()
      poly.map(toPx).forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y)))
      if (closed) ctx.closePath()
      ctx.strokeStyle = color
      ctx.lineWidth = 2
      ctx.stroke()
      if (fill) {
        ctx.fillStyle = `${color}33`
        ctx.fill()
      }
      poly.map(toPx).forEach(([x, y]) => {
        ctx.fillStyle = color
        ctx.fillRect(x - 3, y - 3, 6, 6)
      })
      if (label) {
        const [x, y] = toPx(poly[0])
        ctx.font = '600 12px "Fira Sans", system-ui, sans-serif'
        const w = ctx.measureText(label).width + 10
        ctx.fillStyle = '#0F172ACC'
        ctx.fillRect(x, y - 20, w, 18)
        ctx.fillStyle = color
        ctx.fillText(label, x + 5, y - 7)
      }
    }
    zones.roi.forEach((p, i) => drawPoly(p, COLORS.roi, false, true, zones.roi_meta[i]?.name || `Vùng ${i + 1}`))
    zones.exclude.forEach((p) => drawPoly(p, COLORS.exclude, true))
    drawPoly(draft, COLORS.draft, false, false)
  }, [zones, draft, size])

  const point = (e: React.MouseEvent): Point => {
    const r = canvas.current!.getBoundingClientRect()
    return [clamp((e.clientX - r.left) / r.width), clamp((e.clientY - r.top) / r.height)]
  }

  const finish = (poly: Polygon) => {
    if (poly.length >= 3) {
      if (tool === 'roi') {
        const meta = [...zones.roi_meta]
        while (meta.length < zones.roi.length) meta.push({ name: `Vùng ${meta.length + 1}`, limit: null })
        meta.push({ name: `Vùng ${zones.roi.length + 1}`, limit: null })
        onChange({ ...zones, roi: [...zones.roi, poly], roi_meta: meta })
      } else {
        onChange({ ...zones, exclude: [...zones.exclude, poly] })
      }
    }
    setDraft([])
  }

  const onClick = (e: React.MouseEvent) => {
    const p = point(e)
    if (draft.length >= 3) {
      const [fx, fy] = draft[0]
      const r = canvas.current!.getBoundingClientRect()
      if (Math.hypot((p[0] - fx) * r.width, (p[1] - fy) * r.height) < CLOSE_RADIUS) return finish(draft)
    }
    setDraft([...draft, p])
  }

  const onContextMenu = (e: React.MouseEvent) => {
    e.preventDefault()
    const p = point(e)
    const ex = zones.exclude.findIndex((poly) => inside(p, poly))
    if (ex >= 0) return onChange({ ...zones, exclude: zones.exclude.filter((_, i) => i !== ex) })
    const ri = zones.roi.findIndex((poly) => inside(p, poly))
    if (ri >= 0) onChange({ ...zones, roi: zones.roi.filter((_, i) => i !== ri), roi_meta: zones.roi_meta.filter((_, i) => i !== ri) })
  }

  return <canvas ref={canvas} className="zone-canvas" onClick={onClick} onDoubleClick={() => finish(draft)}
    onContextMenu={onContextMenu} aria-label="Lớp vẽ vùng" />
}

const clamp = (v: number) => Math.min(1, Math.max(0, v))

function inside([x, y]: Point, poly: Polygon): boolean {
  let hit = false
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i]
    const [xj, yj] = poly[j]
    if (yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) hit = !hit
  }
  return hit
}
