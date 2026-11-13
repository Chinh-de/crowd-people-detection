import { useEffect, useState } from 'react'
import type { Status } from '../types'

const RECONNECT_MS = 2000

/** Trạng thái hệ thống do backend đẩy qua WebSocket (~2 lần/giây); tự kết nối lại khi mất. */
export function useLiveStatus(): { status: Status | null; connected: boolean } {
  const [status, setStatus] = useState<Status | null>(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    let ws: WebSocket | null = null
    let timer: number | undefined
    let closed = false

    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/api/ws`)
      ws.onopen = () => setConnected(true)
      ws.onmessage = (e) => setStatus(JSON.parse(e.data) as Status)
      ws.onclose = () => {
        setConnected(false)
        if (!closed) timer = window.setTimeout(connect, RECONNECT_MS)
      }
    }
    connect()
    return () => {
      closed = true
      window.clearTimeout(timer)
      ws?.close()
    }
  }, [])

  return { status, connected }
}
