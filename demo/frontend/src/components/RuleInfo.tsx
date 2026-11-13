import { num } from '../format'
import type { RuleConfig, RuleName, Status } from '../types'

/** Nút "i" tròn nhỏ, bấm để bật/tắt phần giải thích. */
export function InfoButton({ open, onClick, title }: { open: boolean; onClick: () => void; title: string }) {
  return (
    <button type="button" className={`info-btn${open ? ' on' : ''}`} onClick={onClick} title={title} aria-expanded={open}>
      i
    </button>
  )
}

interface Detail {
  what: string
  how: string
  now: string
  note?: string
}

const pct = (v: number | null | undefined) => (v == null ? '—' : `${num(v * 100)}%`)

/** Nội dung chi tiết của từng luật, gồm công thức với tham số và ngưỡng đang dùng. */
export function ruleDetail(rule: RuleName, rules: RuleConfig, status: Status): Detail {
  const th = status.thresholds
  const { counts: c, motion: m } = status
  switch (rule) {
    case 'overcrowd':
      return {
        what: 'Số người trong vùng theo dõi cao bất thường so với mức thường ngày của chính camera này.',
        how: `Ngưỡng = mức nền + max(${num(rules.k_sigma, 1)} × độ lệch; ${num(rules.count_margin_rel * 100)}% mức nền; ${num(rules.count_margin_abs)} người). `
          + 'Nếu đặt "Sức chứa tối đa" thì lấy giá trị nhỏ hơn; sức chứa được áp dụng ngay cả khi chưa học xong.',
        now: `Hiện ${num(c.roi)} người · ngưỡng ${th.overcrowd == null && th.count_limit == null ? 'chờ học' : num(th.overcrowd ?? th.count_limit)}`,
        note: 'Phố đi bộ đông dần lên vào buổi tối: mức nền cập nhật theo các phút gần nhất nên không báo cả buổi. '
          + 'Muốn giữ một giới hạn cứng, hãy đặt "Sức chứa tối đa".',
      }
    case 'hot_cell':
      return {
        what: 'Một ô 64×64 px chứa quá nhiều người: điểm tụ tập, chen lấn cục bộ dù tổng số chưa cao.',
        how: `Ngưỡng = max(${num(rules.min_cell_limit, 1)} người; ${num(rules.cell_factor, 1)} × phân vị 95% của ô đông nhất lúc bình thường).`,
        now: `Ô đông nhất ${num(c.max_cell, 1)} người · ngưỡng ${th.hot_cell == null ? 'chờ học' : num(th.hot_cell, 1)}`,
        note: 'Đèn trang trí và biển hiệu hay bị đếm thành người, tạo ô "dày" giả: hãy vẽ vùng loại trừ lên chúng.',
      }
    case 'surge':
      return {
        what: 'Số người tăng nhanh trong thời gian ngắn: một đám đông đổ về.',
        how: `Số hiện tại − trung vị của khoảng ${num(rules.surge_window_s)}–${num(rules.surge_window_s / 3)} s trước `
          + `> max(${num(rules.surge_abs)} người; ${num(rules.surge_rel * 100)}%). Không cần học mức bình thường.`,
        now: `Hiện ${num(c.roi)} người`,
      }
    case 'panic':
      return {
        what: 'Người chạy tán loạn: chuyển động vừa nhanh hơn hẳn bình thường vừa nhiều hướng cùng lúc.',
        how: `Tốc độ > mức nền + ${num(rules.panic_k, 1)} × độ lệch VÀ độ hỗn loạn hướng (entropy 0–1) > mức nền + ${num(rules.panic_k, 1)} × độ lệch. `
          + 'Chỉ tính các điểm có người (theo mask của model) trong vùng theo dõi.',
        now: `Tốc độ ${num(m.speed)} px/s (ngưỡng ${num(th.panic_speed)}) · hỗn loạn ${num(m.entropy, 2)} (ngưỡng ${num(th.panic_entropy, 2)})`,
        note: 'Cần cả hai điều kiện: một người chạy bộ (nhanh, một hướng) hay đám đông đi lại thong thả (nhiều hướng, chậm) đều không báo.',
      }
    case 'counterflow':
      return {
        what: 'Một phần đáng kể đám đông di chuyển ngược hướng chính (lệch hơn 120°).',
        how: `Ngưỡng = max(${pct(rules.min_counterflow)}; mức nền + ${num(rules.counterflow_k, 1)} × độ lệch), tính theo độ dài vector chuyển động.`,
        now: `Hiện ${pct(m.counterflow)} · ngưỡng ${th.counterflow == null ? 'chờ học' : pct(th.counterflow)}`,
        note: 'Phố hai chiều như Temple Bar vốn có người đi ngược nhau, nên luật này chỉ báo khi tỉ lệ cao hơn hẳn mức thường ngày. '
          + 'Ở lối ra, cầu thang, cổng soát vé (một chiều) luật này mới phát huy hết tác dụng.',
      }
  }
}

/** Giải thích chung: luật hoạt động thế nào và các vùng có ý nghĩa gì. */
export function RulesHelp({ rules }: { rules: RuleConfig }) {
  return (
    <div className="rule-help">
      <p><b>Học mức bình thường.</b> Trong vài phút đầu (hoặc khi bấm nút), hệ thống ghi lại số người, ô đông nhất, tốc độ,
        độ hỗn loạn, tỉ lệ ngược chiều rồi lấy <i>mức nền</i> = trung vị và <i>độ lệch</i> = 1,4826 × MAD. Sau đó mức nền tự cập nhật
        mỗi 30 s theo {num(rules.baseline_window_s / 60)} phút gần nhất, nên theo kịp nhịp phố thay đổi trong ngày.</p>
      <p><b>Chống báo nhầm.</b> Một luật phải đúng liên tục <b>{num(rules.persist_s)} s</b> mới báo; mỗi đợt chỉ báo một lần;
        hai cảnh báo cùng loại cách nhau ít nhất <b>{num(rules.cooldown_s)} s</b>. Mọi ngưỡng đều có mức sàn để lúc phố vắng
        (độ lệch ≈ 0) không bị báo vì một thay đổi nhỏ.</p>
      <p><b>Vùng theo dõi</b> (viền xanh lá): chỗ cần canh. Mọi luật chỉ tính trong vùng này; không vẽ = cả khung hình.
        <br /><b>Vùng loại trừ</b> (viền đỏ, hình tối đi): chỗ đừng tin, như đèn, biển hiệu, poster, kính phản chiếu, làn xe. Không tính vào luật nào,
        kể cả khi nằm trong vùng theo dõi.</p>
    </div>
  )
}
