import { useEffect, useRef, useState } from 'react'
import type { Point, Polygon, ZoneSet } from '../types'

export type ZoneTool = 'roi' | 'exclude'

const COLORS = { roi: '#50dc50', exclude: '#e64646', draft: '#ffd23c' }
const CLOSE_RADIUS = 12          // px: click gần điểm đầu thì đóng polygon

/**
 * Lớp vẽ vùng đặt chồng lên video.
 * Click: thêm điểm · double-click hoặc click lại điểm đầu: đóng vùng · Esc: hủy vùng đang vẽ ·
 * click phải lên một vùng: xóa vùng đó.
 */
export function ZoneCanvas({ zones, tool, onChange }: { zones: ZoneSet; tool: ZoneTool; onChange: (z: ZoneSet) => void }) {
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
    const drawPoly = (poly: Polygon, color: string, fill: boolean, closed = true) => {
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
    }
    zones.roi.forEach((p) => drawPoly(p, COLORS.roi, false))
    zones.exclude.forEach((p) => drawPoly(p, COLORS.exclude, true))
    drawPoly(draft, COLORS.draft, false, false)
  }, [zones, draft, size])

  const point = (e: React.MouseEvent): Point => {
    const r = canvas.current!.getBoundingClientRect()
    return [clamp((e.clientX - r.left) / r.width), clamp((e.clientY - r.top) / r.height)]
  }

  const finish = (poly: Polygon) => {
    if (poly.length >= 3) onChange({ ...zones, [tool]: [...zones[tool], poly] })
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
    for (const kind of ['exclude', 'roi'] as const) {
      const idx = zones[kind].findIndex((poly) => inside(p, poly))
      if (idx >= 0) return onChange({ ...zones, [kind]: zones[kind].filter((_, i) => i !== idx) })
    }
  }

  return <canvas ref={canvas} className="zone-canvas" onClick={onClick} onDoubleClick={() => finish(draft)}
    onContextMenu={onContextMenu} />
}

/** Thanh công cụ vẽ vùng (đặt ngoài khung video). */
export function ZoneToolbar({ tool, onTool, onSave, onCancel, onClear }: {
  tool: ZoneTool; onTool: (t: ZoneTool) => void; onSave: () => void; onCancel: () => void; onClear: () => void
}) {
  return (
    <div className="zone-toolbar">
      <div className="segmented">
        <button className={tool === 'roi' ? 'active' : ''} onClick={() => onTool('roi')}>Vùng giám sát</button>
        <button className={tool === 'exclude' ? 'active' : ''} onClick={() => onTool('exclude')}>Vùng loại trừ</button>
      </div>
      <span className="muted hint">Click thêm điểm · double-click đóng vùng · Esc hủy · click phải xóa vùng</span>
      <button onClick={onClear}>Xóa hết</button>
      <button onClick={onCancel}>Hủy</button>
      <button className="primary" onClick={onSave}>Lưu vùng</button>
    </div>
  )
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
