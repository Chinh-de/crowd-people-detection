import { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { RULE_HINTS, RULE_LABELS, num } from '../format'
import type { RuleConfig, RuleName, Status } from '../types'
import { Icon } from './Icon'

const DEBOUNCE_MS = 400
const ORDER: RuleName[] = ['panic', 'zone_limit', 'overcrowd', 'surge', 'hot_cell', 'counterflow']

/** Bật/tắt luật cảnh báo và chỉnh các tham số chính. */
export function RulesCard({ status, canEdit }: { status: Status; canEdit: boolean }) {
  const [rules, setRules] = useState<RuleConfig | null>(null)
  const timer = useRef<number | undefined>(undefined)

  const cid = status.camera_id
  useEffect(() => {
    api.getRules(cid).then(setRules)
  }, [cid])

  const update = (patch: Partial<RuleConfig>) => {
    if (!rules || !canEdit) return
    const next = { ...rules, ...patch }
    setRules(next)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => api.putRules(cid, next), DEBOUNCE_MS)
  }

  if (!rules) return null
  const th = status?.thresholds
  const active = new Set(status?.active_alerts ?? [])
  const limitText: Record<RuleName, string> = {
    panic: th?.panic_score == null ? 'chờ học' : `điểm > ${num(th.panic_score, 3)}`,
    zone_limit: 'theo từng vùng',
    overcrowd: th?.overcrowd ?? th?.count_limit ? `> ${num(th?.overcrowd ?? th?.count_limit)} người` : 'chờ học',
    surge: `+${num(rules.surge_abs)} người / ${num(rules.surge_window_s)} s`,
    hot_cell: th?.hot_cell == null ? 'chờ học' : `> ${num(th.hot_cell, 1)} người/ô`,
    counterflow: th?.counterflow == null ? 'chờ học' : `> ${num(th.counterflow * 100)}%`,
  }

  return (
    <section className="card" aria-labelledby="rules-title">
      <header className="card-head">
        <h2 id="rules-title"><Icon name="sliders" /> Luật cảnh báo</h2>
        {!canEdit && <span className="muted small">chỉ xem</span>}
      </header>
      <ul className="rule-list">
        {ORDER.map((r) => (
          <li key={r} className={active.has(r) ? 'firing' : ''}>
            <label className="switch" title={RULE_HINTS[r]}>
              <input type="checkbox" disabled={!canEdit} checked={rules.enabled[r] ?? true}
                onChange={(e) => update({ enabled: { ...rules.enabled, [r]: e.target.checked } })} />
              <span className="track" aria-hidden="true" />
              <span className="rule-name">{RULE_LABELS[r]}</span>
            </label>
            <span className="mono small muted">{limitText[r]}</span>
          </li>
        ))}
      </ul>

      <div className="grid-2">
        <label className="field">
          <span>Sức chứa toàn khung</span>
          <input type="number" disabled={!canEdit} min={0} placeholder="không giới hạn" value={rules.count_limit ?? ''}
            onChange={(e) => update({ count_limit: e.target.value === '' ? null : Number(e.target.value) })} />
        </label>
        <label className="field">
          <span>Nghỉ giữa 2 cảnh báo (s)</span>
          <input type="number" disabled={!canEdit} min={0} value={rules.cooldown_s} onChange={(e) => update({ cooldown_s: Number(e.target.value) })} />
        </label>
        <label className="field">
          <span>Duy trì: luật mật độ (s)</span>
          <input type="number" disabled={!canEdit} min={0} value={rules.persist_s} onChange={(e) => update({ persist_s: Number(e.target.value) })} />
        </label>
        <label className="field">
          <span>Duy trì: bất thường (s)</span>
          <input type="number" disabled={!canEdit} min={0} step={0.5} value={rules.panic_persist_s}
            onChange={(e) => update({ panic_persist_s: Number(e.target.value) })} />
        </label>
      </div>
      <p className="note">Sức chứa từng vùng đặt ở bảng "Vùng giám sát" bên phải.</p>
    </section>
  )
}
