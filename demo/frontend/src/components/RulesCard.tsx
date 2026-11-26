import { useEffect, useRef, useState, type ReactNode } from 'react'
import { api } from '../api'
import { RULE_LABELS, anomalyState, num } from '../format'
import type { RuleConfig, RuleName, Status } from '../types'
import { Icon } from './Icon'

const DEBOUNCE_MS = 400
// "Độ nhạy" là thời gian một tín hiệu phải kéo dài (bất thường) hoặc phần người đi ngược (ngược chiều)
const ANOMALY_SENSITIVITY = [
  { value: 1, label: 'Cao · bất thường 1 giây là báo' },
  { value: 2, label: 'Vừa · kéo dài 2 giây' },
  { value: 4, label: 'Thấp · kéo dài 4 giây' },
]
const DIRECTION_SENSITIVITY = [
  { value: 0.25, label: 'Cao · hơn 25% đi ngược' },
  { value: 0.4, label: 'Vừa · hơn 40% đi ngược' },
  { value: 0.6, label: 'Thấp · hơn 60% đi ngược' },
]

/** Cảnh báo của camera: mỗi khối trả lời một câu hỏi, kèm trạng thái hiện tại bằng câu dễ hiểu. */
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
  const active = new Set(status.active_alerts)
  const directed = status.zones.filter((z) => z.direction != null)

  const block = (rule: RuleName, question: string, body: ReactNode) => (
    <div className={`rule-block ${active.has(rule) ? 'firing' : ''}`}>
      <label className="switch">
        <input type="checkbox" disabled={!canEdit} checked={rules.enabled[rule] ?? true}
          onChange={(e) => update({ enabled: { ...rules.enabled, [rule]: e.target.checked } })} />
        <span className="track" aria-hidden="true" />
        <span className="rule-name">{RULE_LABELS[rule]}</span>
      </label>
      <p className="note">{question}</p>
      {body}
    </div>
  )

  const sensitivity = (label: string, value: number, options: { value: number; label: string }[],
    onChange: (v: number) => void) => (
    <label className="field">
      <span>{label}</span>
      <select value={value} disabled={!canEdit} onChange={(e) => onChange(Number(e.target.value))}>
        {!options.some((o) => o.value === value) && <option value={value}>Tùy chỉnh ({value})</option>}
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  )

  // giá trị ngoài khoảng (kể cả ô đang xóa trống) không được lưu
  const numberField = (label: string, value: number, min: number, max: number, onChange: (v: number) => void) => (
    <label className="field">
      <span>{label}</span>
      <input type="number" min={min} max={max} disabled={!canEdit} defaultValue={value}
        onChange={(e) => {
          const v = Number(e.target.value)
          if (e.target.value !== '' && v >= min && v <= max) onChange(v)
        }} />
    </label>
  )

  return (
    <section className="card" aria-labelledby="rules-title">
      <header className="card-head">
        <h2 id="rules-title"><Icon name="sliders" /> Cảnh báo</h2>
        {!canEdit && <span className="muted small">chỉ xem</span>}
      </header>

      {block('panic', 'Đám đông có hành xử khác thường không? Dùng mô hình chuyển động (giai đoạn 2), cần học mức bình thường.', (
        <>
          <p className="small">Hiện tại: <b>{anomalyState(status.anomaly).label}</b></p>
          {sensitivity('Độ nhạy', rules.panic_persist_s, ANOMALY_SENSITIVITY, (v) => update({ panic_persist_s: v }))}
        </>
      ))}

      {block('zone_limit', 'Chỗ này có quá đông không? Báo khi vượt sức chứa bạn đặt. Không cần học.', (
        <label className="field">
          <span>Sức chứa toàn khung (người)</span>
          <input type="number" disabled={!canEdit} min={0} placeholder="không giới hạn" value={rules.count_limit ?? ''}
            onChange={(e) => update({ count_limit: e.target.value === '' ? null : Number(e.target.value) })} />
          <span className="note">Sức chứa từng vùng đặt ở mục "Vùng".</span>
        </label>
      ))}

      {block('surge', 'Người có đang dồn đến nhanh không?', (
        <>
          <div className="grid-3">
            {numberField('Trong (giây)', rules.surge_window_s, 15, 600, (v) => update({ surge_window_s: v }))}
            {numberField('Tăng ít nhất (người)', rules.surge_abs, 1, 1000, (v) => update({ surge_abs: v }))}
            {numberField('Và ít nhất (%)', Math.round(rules.surge_rel * 100), 0, 1000, (v) => update({ surge_rel: v / 100 }))}
          </div>
          <p className="small muted">
            Báo khi trong {num(rules.surge_window_s)} giây số người tăng ít nhất {num(rules.surge_abs)} người
            và ít nhất {num(rules.surge_rel * 100)}% so với trước.
          </p>
        </>
      ))}

      {block('counterflow', 'Có người đi ngược chiều lối một chiều không? Chỉ xét vùng đã chọn chiều đi.', (
        <>
          {directed.length === 0 ? (
            <p className="small muted">Chưa vùng nào có chiều đi. Chọn ở mục "Vùng". Phố đi hai chiều thì để trống.</p>
          ) : (
            <ul className="direction-list small">
              {directed.map((z) => (
                <li key={z.name}>{z.name}: {z.wrong_share == null ? 'ít người di chuyển' : `${num(z.wrong_share * 100)}% đang đi ngược`}</li>
              ))}
            </ul>
          )}
          {sensitivity('Độ nhạy', rules.counterflow_share, DIRECTION_SENSITIVITY, (v) => update({ counterflow_share: v }))}
        </>
      ))}
    </section>
  )
}
