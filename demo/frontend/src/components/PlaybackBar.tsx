import { api } from '../api'
import { duration } from '../format'
import type { SourceInfo } from '../types'

/** Phát / tạm dừng / tua, chỉ với video có sẵn. */
export function PlaybackBar({ source }: { source: SourceInfo }) {
  const pos = source.position_s ?? 0
  const total = source.duration_s ?? 0
  return (
    <div className="playback">
      <button onClick={() => api.playback(source.paused ? 'play' : 'pause')}>
        {source.paused ? '▶ Phát' : '❚❚ Tạm dừng'}
      </button>
      <input type="range" min={0} max={Math.max(total, 1)} step={0.5} value={pos}
        onChange={(e) => api.playback('seek', Number(e.target.value))} aria-label="Tua video" />
      <span className="muted mono">{duration(pos)} / {duration(total)}</span>
    </div>
  )
}
