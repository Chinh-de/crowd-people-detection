import { useCallback, useEffect, useState } from 'react'
import { api } from './api'
import { Shell, routeFromHash, type Route } from './components/Shell'
import { useLive } from './hooks/useLiveStatus'
import { AuditPage } from './pages/AuditPage'
import { CamerasPage } from './pages/CamerasPage'
import { HistoryPage } from './pages/HistoryPage'
import { LoginPage } from './pages/LoginPage'
import { MonitorPage } from './pages/MonitorPage'
import { StatsPage } from './pages/StatsPage'
import type { CameraSummary, Me } from './types'

const CAMERA_POLL_MS = 5000

/** Kiểm tra đăng nhập, rồi hiện trang theo đường dẫn hash (#/giam-sat, #/lich-su, #/thong-ke, #/camera, #/nhat-ky). */
export default function App() {
  const [me, setMe] = useState<Me | null>(null)
  const [checked, setChecked] = useState(false)
  const [route, setRoute] = useState<Route>(() => routeFromHash(location.hash))
  const [cameras, setCameras] = useState<CameraSummary[]>([])
  const { live, connected } = useLive(!!me)

  useEffect(() => {
    api.me().then(setMe).catch(() => setMe(null)).finally(() => setChecked(true))
    const onUnauthorized = () => setMe(null)
    const onHash = () => setRoute(routeFromHash(location.hash))
    window.addEventListener('crowd:unauthorized', onUnauthorized)
    window.addEventListener('hashchange', onHash)
    return () => {
      window.removeEventListener('crowd:unauthorized', onUnauthorized)
      window.removeEventListener('hashchange', onHash)
    }
  }, [])

  const loadCameras = useCallback(() => {
    api.listCameras().then(setCameras).catch(() => undefined)
  }, [])

  // Danh sách camera: tải khi đăng nhập, khi số camera đang chạy đổi, và định kỳ
  const runningKey = Object.keys(live?.cameras ?? {}).join(',')
  useEffect(() => {
    if (!me) return
    loadCameras()
    const id = window.setInterval(loadCameras, CAMERA_POLL_MS)
    return () => window.clearInterval(id)
  }, [me, runningKey, loadCameras])

  if (!checked) return null
  if (!me) return <LoginPage onLogin={setMe} />

  const isAdmin = me.role === 'admin'
  const page = route === 'cameras' && isAdmin ? <CamerasPage cameras={cameras} live={live} onChanged={loadCameras} />
    : route === 'audit' && isAdmin ? <AuditPage />
    : route === 'history' ? <HistoryPage cameras={cameras} unacked={live?.unacked ?? 0} />
    : route === 'stats' ? <StatsPage cameras={cameras} />
    : <MonitorPage me={me} live={live} cameras={cameras} onCamerasChanged={loadCameras} />

  const logout = async () => {
    await api.logout().catch(() => undefined)
    setMe(null)
  }

  return (
    <Shell me={me} route={route} unacked={live?.unacked ?? 0} connected={connected}
      running={Object.keys(live?.cameras ?? {}).length} maxCameras={live?.max_cameras ?? 4} onLogout={logout}>
      {page}
    </Shell>
  )
}
