import { useEffect, useState } from 'react'
import { api } from '../api'
import type { ModelInfo } from '../types'

/** Chọn model đếm người. Đổi model thì hệ thống học lại mức bình thường. */
export function ModelSwitch({ active }: { active: string | undefined }) {
  const [models, setModels] = useState<ModelInfo[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.listModels().then(setModels)
  }, [active])

  const choose = async (name: string) => {
    setBusy(true)
    setError(null)
    try {
      setModels(await api.setModel(name))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="model-switch">
      <span className="muted">Model</span>
      <div className="segmented" role="radiogroup" aria-label="Model đếm người">
        {models.map((m) => (
          <button key={m.name} role="radio" aria-checked={m.name === active} disabled={busy || !m.available}
            className={m.name === active ? 'active' : ''} onClick={() => choose(m.name)}
            title={m.available ? undefined : 'Chưa có file model'}>
            {m.label}
          </button>
        ))}
      </div>
      {error && <span className="error">{error}</span>}
    </div>
  )
}
