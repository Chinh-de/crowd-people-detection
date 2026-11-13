import type { ReactNode } from 'react'
import type { Status } from '../types'

/**
 * Luồng MJPEG đã vẽ lớp nhận diện ở backend. `children` (ví dụ ZoneEditor) được đặt chồng lên ảnh,
 * cùng kích thước, để vẽ vùng bằng tọa độ chuẩn hóa.
 */
export function VideoStage({ status, children }: { status: Status | null; children?: ReactNode }) {
  const source = status?.source
  const alerting = (status?.active_alerts.length ?? 0) > 0

  if (!source) {
    return (
      <div className="stage empty">
        <p>Chọn video có sẵn hoặc dán link livestream để bắt đầu.</p>
      </div>
    )
  }
  return (
    <div className={`stage ${alerting ? 'alerting' : ''}`} style={{ aspectRatio: `${source.size[0]} / ${source.size[1]}` }}>
      {/* đổi key khi đổi lần chạy để trình duyệt mở lại luồng */}
      <img key={source.run} src={`/api/stream.mjpg?run=${source.run}`} alt="Video giám sát" draggable={false} />
      {children}
    </div>
  )
}
