// 画面の呼び名（1か所にまとめる）。呼び名は会計・申告アプリで一般的なものに合わせる（docs/household-ui-references.md）
export const NAV = {
  home: 'ホーム',
  book: '家計簿',
  txns: '入出金',
  accounts: '口座',
  upload: '書類',
  inbox: '確認待ち',
  records: '記録',
  family: '家族',
  tax: '確定申告',
  questions: '質問',
  forms: '申告書',
  settings: '設定',
  more: 'その他',
} as const;

export const TAGLINE = '書類を撮るだけで、家族の税金と扶養がわかる';

// 結果の値の状態（判定コアの「未確定」「対象外」を画面の言葉に）
export const STATE: Record<string, string> = { 未確定: '未確定', 対象外: '未対応', 予測: '見込み', 見積り: '見積り', 計画: '予定' };

// 境目（判定コアの概念 ID）→ 壁の呼び名
export const WALL_NAMES: Record<string, string> = {
  '所得税.扶養親族の所得要件': '扶養の壁',
  '所得税.特定親族の所得要件': '特定親族の壁',
  '所得税.特定親族特別控除の段階': '特定親族特別控除の壁',
  '所得税.勤労学生の所得要件': '勤労学生の壁',
  '所得税.基礎控除の段階': '基礎控除の壁',
  '健保.被扶養者の年間収入の基準': '社会保険の扶養の壁',
  '所得税.控除対象配偶者の所得要件': '配偶者控除の壁',
  '所得税.配偶者特別控除の段階': '配偶者特別控除の壁',
};
