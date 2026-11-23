import type { ReactNode } from 'react'
import type { Me } from '../types'
import { Icon, type IconName } from './Icon'

export type Route = 'monitor' | 'history' | 'stats' | 'cameras' | 'audit'

export const ROUTES: { id: Route; hash: string; label: string; icon: IconName; admin?: boolean }[] = [
  { id: 'monitor', hash: '#/giam-sat', label: 'Giám sát', icon: 'eye' },
  { id: 'history', hash: '#/lich-su', label: 'Lịch sử cảnh báo', icon: 'alert' },
  { id: 'stats', hash: '#/thong-ke', label: 'Thống kê', icon: 'chart' },
  { id: 'cameras', hash: '#/camera', label: 'Camera', icon: 'video', admin: true },
  { id: 'audit', hash: '#/nhat-ky', label: 'Nhật ký', icon: 'list', admin: true },
]

export function routeFromHash(hash: string): Route {
  return ROUTES.find((r) => r.hash === hash)?.id ?? 'monitor'
}

/** Khung ứng dụng: thanh điều hướng trên cùng và nội dung trang. */
export function Shell({ me, route, unacked, connected, running, maxCameras, onLogout, children }: {
  me: Me; route: Route; unacked: number; connected: boolean; running: number; maxCameras: number
  onLogout: () => void; children: ReactNode
}) {
  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand">
          <Icon name="shield" size={20} />
          <div>
            <h1>Giám sát đám đông</h1>
            <span className="sub">Đếm người · Khoanh vùng · Phát hiện bất thường</span>
          </div>
        </div>

        <nav className="nav" aria-label="Trang">
          {ROUTES.filter((r) => !r.admin || me.role === 'admin').map((r) => (
            <a key={r.id} href={r.hash} className={route === r.id ? 'on' : ''} aria-current={route === r.id ? 'page' : undefined}>
              <Icon name={r.icon} size={15} /> {r.label}
              {r.id === 'history' && unacked > 0 && <span className="nav-badge mono" title="Cảnh báo chưa xử lý">{unacked}</span>}
            </a>
          ))}
        </nav>

        <div className="topbar-right">
          <span className="mono muted small" title="Số camera đang chạy / tối đa (giới hạn phần cứng CPU)">
            <Icon name="cpu" size={14} /> {running}/{maxCameras} camera
          </span>
          <span className={`conn ${connected ? 'on' : ''}`} role="status"
            title={connected ? 'Đã kết nối máy chủ' : 'Mất kết nối máy chủ, đang thử lại'}>
            <span className="dot" />{connected ? 'Kết nối' : 'Mất kết nối'}
          </span>
          <span className="user">
            <Icon name="user" size={14} /> {me.name}
            <span className="role">{me.role === 'admin' ? 'quản trị' : 'chỉ xem'}</span>
          </span>
          <button className="btn btn-ghost btn-sm" onClick={onLogout}><Icon name="logout" size={14} /> Đăng xuất</button>
        </div>
      </header>
      {me.default_credentials && (
        <div className="banner" role="alert">
          <Icon name="alert" size={14} /> Đang dùng tài khoản mặc định admin/admin. Hãy đặt CROWD_ADMIN_USER và CROWD_ADMIN_PASSWORD
          trong demo/backend/.env rồi khởi động lại.
        </div>
      )}
      {children}
    </div>
  )
}
