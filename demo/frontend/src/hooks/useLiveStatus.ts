import { useEffect, useState } from 'react'
import type { LiveMessage } from '../types'

const RECONNECT_MS = 2000

/** Trạng thái mọi camera đang chạy do backend đẩy qua WebSocket (~2 lần/giây); tự kết nối lại khi mất. */
export function useLive(enabled: boolean): { live: LiveMessage | null; connected: boolean } {
  const [live, setLive] = useState<LiveMessage | null>(null)
  const [connected, setConnected] = useState(false)

  useEffect(() => {
    if (!enabled) return
    let ws: WebSocket | null = null
    let timer: number | undefined
    let closed = false

    const connect = () => {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/api/ws`)
      ws.onopen = () => setConnected(true)
      ws.onmessage = (e) => setLive(JSON.parse(e.data) as LiveMessage)
      ws.onclose = (e) => {
        setConnected(false)
        if (e.code === 4401) window.dispatchEvent(new Event('crowd:unauthorized'))
        else if (!closed) timer = window.setTimeout(connect, RECONNECT_MS)
      }
    }
    connect()
    return () => {
      closed = true
      window.clearTimeout(timer)
      ws?.close()
    }
  }, [enabled])

  return { live, connected }
}
