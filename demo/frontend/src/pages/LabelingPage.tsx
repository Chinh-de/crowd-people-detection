/** Gắn nhãn đầu người: công cụ canvas riêng (backend phục vụ ở /labeling), cùng phiên đăng nhập và cùng giao diện. */
export function LabelingPage() {
  return <iframe className="label-frame" src="/labeling" title="Gắn nhãn đầu người"
    onLoad={(e) => e.currentTarget.contentWindow?.focus()} />
}
