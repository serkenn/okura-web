// コンポーネントの外（ダイアログの中の処理など）から画面を移る。コンポーネントの中では useNavigate を使う
type Nav = (to: string, opts?: { replace?: boolean }) => void;
let nav: Nav = (to) => { location.href = to; };

export function setNavigate(fn: Nav) { nav = fn; }

/** 例：go('/tax/2026') */
export function go(to: string, opts?: { replace?: boolean }) { nav(to, opts); }
