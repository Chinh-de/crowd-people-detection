import { Fragment, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { RULE_LABELS, num } from '../format'
import type { RuleConfig, RuleName, Status } from '../types'
import { InfoButton, RulesHelp, ruleDetail } from './RuleInfo'

const DEBOUNCE_MS = 300

/** Bật/tắt luật, chỉnh ngưỡng, học mức bình thường. */
export function RulesPanel({ status }: { status: Status }) {
  const [rules, setRules] = useState<RuleConfig | null>(null)
  const [calibSeconds, setCalibSeconds] = useState(300)
  const [help, setHelp] = useState(false)
  const [openRule, setOpenRule] = useState<RuleName | null>(null)
  const timer = useRef<number | undefined>(undefined)

  useEffect(() => {
    api.getRules().then(setRules)
  }, [])

  const update = (patch: Partial<RuleConfig>) => {
    if (!rules) return
    const next = { ...rules, ...patch }
    setRules(next)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => api.putRules(next), DEBOUNCE_MS)
  }

  if (!rules) return null
  const { calibration: cal, thresholds: th, active_alerts: active } = status
  const crowdLimit = th.overcrowd ?? th.count_limit
  const limitFor: Record<RuleName, string> = {
    overcrowd: crowdLimit == null ? 'chờ học' : `> ${num(crowdLimit)} người`,
    hot_cell: `> ${num(th.hot_cell, 1)} người/ô`,
    surge: `+${num(rules.surge_abs)} người và +${num(rules.surge_rel * 100)}% / ${num(rules.surge_window_s)} s`,
    panic: `tốc độ > ${num(th.panic_speed)} px/s và hỗn loạn > ${num(th.panic_entropy, 2)}`,
    counterflow: `> ${num((th.counterflow ?? 0) * 100)}%`,
  }

  return (
    <section className="panel">
      <header>
        <h2>Luật cảnh báo</h2>
        <InfoButton open={help} onClick={() => setHelp(!help)} title="Luật hoạt động thế nào" />
      </header>
      {help && <RulesHelp rules={rules} />}

      <div className="calibration">
        {cal.done
          ? <span className="ok">Đã học mức bình thường</span>
          : cal.need > 0
            ? <progress max={cal.need} value={cal.have} title={`${cal.have}/${cal.need} mẫu`} />
            : <span className="muted">Chưa học mức bình thường</span>}
        {!cal.done && cal.need > 0 && <span className="muted mono">đang học {cal.have}/{cal.need} mẫu</span>}
        <label className="inline">
          <input type="number" min={10} max={600} value={calibSeconds} onChange={(e) => setCalibSeconds(Number(e.target.value))} /> giây
        </label>
        <button onClick={() => api.calibrate(calibSeconds)}>Học mức bình thường</button>
      </div>

      <table className="rules">
        <tbody>
          {(Object.keys(RULE_LABELS) as RuleName[]).map((r) => (
            <Fragment key={r}>
            <tr className={active.includes(r) ? 'firing' : ''}>
              <td>
                <label className="inline">
                  <input type="checkbox" checked={rules.enabled[r]}
                    onChange={(e) => update({ enabled: { ...rules.enabled, [r]: e.target.checked } })} />
                  {RULE_LABELS[r]}
                </label>
              </td>
              <td className="muted mono">{cal.done || r === 'overcrowd' || r === 'surge' ? limitFor[r] : 'chờ học'}</td>
              <td className="info-cell">
                <InfoButton open={openRule === r} onClick={() => setOpenRule(openRule === r ? null : r)} title={`Chi tiết luật ${RULE_LABELS[r]}`} />
              </td>
            </tr>
            {openRule === r && <RuleDetailRow rule={r} rules={rules} status={status} />}
            </Fragment>
          ))}
        </tbody>
      </table>

      <div className="sliders">
        <Slider label="Độ nhạy (k × độ lệch)" min={1} max={6} step={0.5} value={rules.k_sigma} onChange={(v) => update({ k_sigma: v })} />
        <Slider label="Duy trì trước khi báo" min={0} max={30} step={1} value={rules.persist_s} onChange={(v) => update({ persist_s: v })} format={(v) => `${v} s`} />
        <Slider label="Nghỉ giữa hai cảnh báo cùng loại" min={0} max={300} step={10} value={rules.cooldown_s} onChange={(v) => update({ cooldown_s: v })} format={(v) => `${v} s`} />
        <Slider label="Tăng đột ngột: tối thiểu (người)" min={5} max={60} step={1} value={rules.surge_abs} onChange={(v) => update({ surge_abs: v })} />
        <Slider label="Tăng đột ngột: tối thiểu (%)" min={0.1} max={2} step={0.1} value={rules.surge_rel} onChange={(v) => update({ surge_rel: v })} format={(v) => `${Math.round(v * 100)}%`} />
        <label className="field">
          <span>Sức chứa tối đa (người, để trống = theo thống kê)</span>
          <input type="number" min={0} value={rules.count_limit ?? ''}
            onChange={(e) => update({ count_limit: e.target.value === '' ? null : Number(e.target.value) })} />
        </label>
      </div>
    </section>
  )
}

function RuleDetailRow({ rule, rules, status }: { rule: RuleName; rules: RuleConfig; status: Status }) {
  const d = ruleDetail(rule, rules, status)
  return (
    <tr className="rule-detail">
      <td colSpan={3}>
        <p>{d.what}</p>
        <p><b>Cách tính:</b> {d.how}</p>
        <p className="mono">{d.now}</p>
        {d.note && <p className="muted"><b>Với phố này:</b> {d.note}</p>}
      </td>
    </tr>
  )
}

function Slider({ label, value, min, max, step, onChange, format }: {
  label: string; value: number; min: number; max: number; step: number; onChange: (v: number) => void; format?: (v: number) => string
}) {
  return (
    <label className="field">
      <span>{label}: <b>{format ? format(value) : value}</b></span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </label>
  )
}
