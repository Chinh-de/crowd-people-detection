import { api } from '../api'
import type { ViewMode } from '../types'

const MODES: { value: ViewMode; label: string }[] = [
  { value: 'video', label: 'Chỉ video' },
  { value: 'overlay', label: 'Video + nhận diện' },
  { value: 'overlay_only', label: 'Chỉ nhận diện' },
  { value: 'gray', label: 'Nền xám + nhận diện' },
]

/** Bốn chế độ hiển thị; đổi ngay trên luồng video đang phát. */
export function ModeSwitch({ mode }: { mode: ViewMode | undefined }) {
  return (
    <div className="segmented" role="radiogroup" aria-label="Chế độ hiển thị">
      {MODES.map((m) => (
        <button key={m.value} role="radio" aria-checked={mode === m.value}
          className={mode === m.value ? 'active' : ''} onClick={() => api.setMode(m.value)}>
          {m.label}
        </button>
      ))}
    </div>
  )
}
