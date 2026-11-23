import { useEffect, useState } from 'react'
import { api } from '../api'
import { clock } from '../format'
import type { AuditRow } from '../types'

const PAGE = 50
const LOCAL_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone

const ACTIONS: Record<string, string> = {
  login: 'Đăng nhập', login_failed: 'Đăng nhập sai', logout: 'Đăng xuất',
  create_camera: 'Thêm camera', update_camera: 'Sửa camera', delete_camera: 'Xóa camera',
  start_camera: 'Bật camera', stop_camera: 'Tắt camera', upload_video: 'Tải video lên',
  set_zones: 'Sửa vùng', set_rules: 'Sửa luật', set_model: 'Đổi mô hình đếm', set_anomaly_model: 'Đổi mô hình bất thường',
  calibrate: 'Học lại mức bình thường', ack_event: 'Xác nhận cảnh báo',
}

/** Trang Nhật ký thao tác (quản trị): ai làm gì, lúc nào. */
export function AuditPage() {
  const [rows, setRows] = useState<AuditRow[]>([])
  const [page, setPage] = useState(0)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.audit(PAGE, page * PAGE).then(setRows).catch((e: Error) => setError(e.message))
  }, [page])

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <h2>Nhật ký thao tác</h2>
          <p className="muted small">Giờ theo máy đang xem ({LOCAL_TZ}).</p>
        </div>
      </header>
      {error && <p className="error" role="alert">{error}</p>}
      <section className="card table-card">
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th scope="col">Thời điểm</th><th scope="col">Người dùng</th><th scope="col">Thao tác</th><th scope="col">Chi tiết</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td className="mono nowrap">{clock(r.t, LOCAL_TZ, true)}</td>
                  <td>{r.user}</td>
                  <td className={r.action === 'login_failed' ? 'status-new' : ''}>{ACTIONS[r.action] ?? r.action}</td>
                  <td className="small break">{r.detail}</td>
                </tr>
              ))}
              {rows.length === 0 && <tr><td colSpan={4} className="muted center">Chưa có thao tác nào.</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="pager">
          <button className="btn btn-sm" disabled={page === 0} onClick={() => setPage(page - 1)}>Mới hơn</button>
          <span className="mono small">Trang {page + 1}</span>
          <button className="btn btn-sm" disabled={rows.length < PAGE} onClick={() => setPage(page + 1)}>Cũ hơn</button>
        </div>
      </section>
    </div>
  )
}
