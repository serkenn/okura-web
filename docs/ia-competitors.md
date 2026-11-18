# 情報設計の比較：長く使われている家計簿・会計・申告のアプリ（2026-11-18 調査）

「自分で作らず、長く使われている構造を真似る」ための調べもの。見たのは **全体の構造**（何が一覧・詳細の画面を持つ「もの」か、ナビに何を何個置くか、作業をどこに置くか、家族をどう表すか、年に一度の申告をどう組むか）だけ。
家計簿の画面の呼び名と型は `docs/household-ui-references.md` にあるので、ここでは繰り返さない。

- 借りるのは構造と一般の言葉だけ。各社の機能の名前（Tax Home・Smart Check・Shared Views・自動で経理・スマート取引取込・シェアボード など）、ロゴ・画像は使わない（`docs/ui-references.md` と同じ）。
- 記号：**名**＝もの（名詞。一覧と詳細の画面がある）、**作**＝作業（動詞・手順・ウィザード）、**見**＝見るだけの画面（集計・レポート・ホーム）。（未確認）＝公式の文書で確かめられなかったもの（コミュニティの投稿・レビュー・検索結果の抜粋に拠る）。
- 調べ方：公式のヘルプ・マニュアル、OSS はソース（ナビを定義しているファイル）。ソフトは入れていない・動かしていない。

## 0. いまの okura-web（比べる元）

| ナビ（`frontend/src/Shell.tsx` の NAV） | 種類 |
|---|---|
| ホーム | 見 |
| 家計簿 › 家計簿・入出金・口座 | 見・名・名 |
| 記録 › 書類・要確認・記録・家族 | 名（＋撮る＝作）・作（受信箱）・名・名 |
| 確定申告 › 質問・計算結果・申告書 | 作・見・見（1つの流れの段を3つの項目に） |
| その他 › 設定（タブ9：共有設定・メンバー・依頼・カテゴリ・ログイン・AI・AI連携・市区町村・保険・計算の対象） | — |
| スマホの下のタブ：ホーム・家計簿・書類・質問・その他 | |

左のナビは 12 項目。申告の「質問 → 計算結果 → 申告書」という **1つの流れの段** が、ナビでは横並びの3項目になっている。家族は「家族」の一覧と、家計簿の持ち主・共有で表している。

## 1. 比べた表

| アプリ | 主なナビ（数） | 名／作の割合 | 家族・人の表し方 | 申告の流れの形 |
|---|---|---|---|---|
| GnuCash | 横のタブ（口座の木が土台。台帳・レポートをタブで開く）＋メニュー9 | タブは名。作業はメニュー（取込・照合・定期の取引） | 1つのファイル＝1つの帳簿。人ごとにファイルを分けるか、口座の木を並べる（未確認） | 口座に「税に関係」と様式の行の印 → 税のレポート・書き出し。申告そのものはしない |
| KMyMoney | 左のビュー13：ホーム・金融機関・口座・定期の取引・カテゴリ・タグ・取引先・台帳・投資・レポート・予算・予測・送信待ち | ホーム以外は全部 名 | 1つのファイル。持ち主の欄なし | カテゴリに「税のレポートに含める」の印 → レポート |
| HomeBank | 1つの画面（口座の一覧・グラフ・定期の取引）＋メニュー8。もの（口座・取引先・カテゴリ・タグ・ルール・予算）は「管理」メニューの窓 | 名は窓、作は手順（取込は4段のウィザード） | 1つのファイル。持ち主なし | なし |
| Firefly III | 左に約20（ダッシュボード、予算・定期の支払い・積立、取引（支出・収入・振替・全部）、自動化（ルール・繰り返し）、口座（資産・支出先・収入元・負債）、分類（カテゴリ・タグ・グループ）、レポート ほか） | ほぼ全部 名。取込は別のアプリ、照合は口座の中 | 人ごとに別のアカウント・別の帳簿。共有はまだできない | なし。添付はほぼ全部のものに付く |
| Actual Budget | 左：予算・レポート・定期の取引（＋隠し：取引先・タグ・ルール・銀行の連携）・設定、その下に口座の一覧 | 全部 名。取込・照合は口座の画面の中のボタン | 予算のファイルごとに持ち主と使える人の一覧 | なし |
| Fava | 左15：損益・貸借・試算表・仕訳・クエリ／保有・商品・**書類**・出来事・統計／**編集・エラー・取込**・オプション・ヘルプ | 見が中心＋作（取込・編集・エラー）を独立の項目に | ファイルを切り替える。人はタグ・口座の名前・絞り込みで | なし。書類は口座ごとのフォルダー（`document`） |
| Quicken（Windows・Mac） | 上のタブ：ホーム・支出・請求と収入・計画・投資・資産と負債（・事業・賃貸）＋左の口座の帯 | 領域（名の集まり）。取込の確認は台帳の下のタブ | 1つのファイルを勧める。家族の口座は隠すか集計から外す。分けたいものは別ファイル | カテゴリごとに税の行 → 税のレポート・書き出し。税の見積りは「計画」の中 |
| Quicken Simplifi | 左：取引・純資産・**領収書**・支出の計画・目標・請求と収入・計画の道具・投資・ウォッチ・レポート | 名が中心。領収書は「要確認」の受信箱 | 1人だけ招いて共有（未確認） | なし（上位のプランに税の見積り） |
| YNAB | 左：予算・全口座＋口座の一覧（種類別）。スマホ5：ホーム・予算・支出（取引）・口座・振り返り | 名3＋見2。確認は帯と絞り込み | 1つの契約で2〜6人。予算は人ごと（持ち主＝その人）で、ほかの人に共有する | なし（書き出しだけ） |
| Monarch Money | 左（全体は未確認）：ダッシュボード・口座・取引・収支・レポート・予算・定期・目標・投資・領収書 ほか。スマホは下5（入れ替えできる） | 名が中心＋見。確認は取引の状態（「要確認」）と帯 | 1つの世帯に人（役割：管理者・メンバー）。口座・取引に **持ち主**（共有 or 1人）、取引は口座から受け継ぐ。「持ち主」の絞り込みは口座・取引・レポート・収支だけ。人ごとに「確認する人」を指定できる | 「税の控除」のタグとレポート。事業の印 → 事業の様式向けのレポート |
| マネーフォワード ME | アプリ下5：ホーム・入出金・家計簿・口座・資産（＋入力のボタン）。Web 上のタブ：家計簿・資産・口座・レポート・設定 ほか（並びは未確認） | 名3＋見2＋作1（入力） | 「グループ」＝口座の絞り込み（人ではない）。2人の共有は金融機関ごとに選ぶ | 取引ごとの「確定申告」の印・医療費のカテゴリ → 別の申告アプリへ渡す |
| freee 会計／確定申告 | 左14（業務の名前：請求・入金、発注・経費・支払、取引入力、会計帳簿、分析・レポート、決算申告、確定申告 ほか＋マスタ・口座、設定） | 作（業務）が中心。ものは「マスタ・口座」の下 | 1人の申告の中に配偶者・扶養親族の項目。事業所は増やせるが、料金も帳簿も別 | 段の帯4（基本 → 収支 → 確認 → 提出）。収支の後半は一問一答（○×） |
| マネーフォワード クラウド確定申告 | 左（全体は未確認）：ホーム・データ連携・自動で仕訳・手動で仕訳・取引管理・会計帳簿・レポート・決算・申告・各種設定 | 作が中心 | 自分の申告の中に「配偶者」「家族や親族」。事業者は別契約 | STEP1〜4（初期設定 → 経費・収入 → 申告書の作成 → 確認・提出）。中は様式どおり（第一表・第二表…）＋右に申告書の写し。ホームに To Do の一覧 |
| やよいの青色／白色申告 オンライン | 左8：ホーム・かんたん取引入力・スマート取引取込・仕訳の入力・レポート・帳簿・確定申告・設定・高度な機能 | 作が中心（ものはレポート・帳簿と設定の中） | 申告の中に家族の項目。家族の分を作れるかは未確認 | 「確定申告の手順」Step1〜4（減価償却 → 決算書 → 申告書 → 電子申告）。申告書の中も段の帯（基本情報 → 所得 → 所得控除 → … → 最終確認） |
| 国税庁 確定申告書等作成コーナー | ナビなし。上に段の帯（申告準備 → 収入等 → 控除等 → その他 → 印刷 → データ保存） | 全部 作（1本の手順） | **1人に1つの申告書・1つの保存ファイル**。家族は申告者の中の控除の項目。家族の分は別に作る | 所得・控除の **一覧のハブ**：各行に「入力あり」「確認してください」（自動で入った値）、［＞］で入る。結果の確認から各項目へ戻れる。途中の保存と再開 |
| TurboTax | 「ホーム」（年ごとの申告と書類）＋申告の中の左：ホーム・私の情報・連邦・州・書類・道具・確認・提出（一部は未確認） | 名（ホーム・私の情報・書類）＋段（連邦・州・確認・提出） | **1アカウント＝1年1申告**。配偶者は合算の申告の中、扶養家族は「私の情報」の項目。扶養になるかは、人が事実に答えてソフトが規則で判定。扶養される人の申告には「ほかの人に扶養される」の印。家族をまたぐつながりはない | 段＋**話題の一覧のハブ**（話題ごとに「始める」「見直す」「更新」）。最後にエラーの点検。書類は話題の中で取り込む（写真・PDF・勤め先から） |
| H&R Block | 個人情報・収入・控除・税額控除・税・仕上げ（レビューに拠る。数は未確認）＋「概要」 | 段が中心 | 1アカウント＝1申告。別の申告は別のアカウント | 段の手順＋最後に正確さの点検（「直す」の一覧）。デスクトップは様式の一覧（状態の列） |

## 2. アプリごとのメモ

### OSS

- **GnuCash**：もの＝帳簿（ファイル）・口座の木・取引（分割）・定期の取引・予算・価格。取引先・タグは独立のものでない。ナビは横のタブで、口座の木がいつも土台。取込は「ファイル › 取り込み」（12種類）→ 別の窓「取込の照合」で行ごとに 追加／更新／照合済み を選ぶ。照合は「操作 › 照合」で専用の窓。ダッシュボードはない。書類は取引の右クリックで「ファイル・URL をつなぐ」、一覧は「道具 › 取引につないだ書類」。
- **KMyMoney**：ナビ＝もののビュー13（ホームだけが見）。取込の確認は台帳のビューの中で「受け入れる／照合を外す」（別の画面なし）。照合はウィザード。カテゴリに税の印。
- **HomeBank**：もの（取引先・カテゴリ・タグ・ルール・定期・予算）は全部「管理」メニューの窓で、メインの画面は口座の一覧だけ。取込は4段の手順（ファイル → 口座ごとに取り込むものを選ぶ（重複は外しておく） → 確認（ルールを走らせる・保留で入れる））。
- **Firefly III**：ナビはほぼ全部が名（約20）で、見出しで4つにまとめる（お金の管理・帳簿・整理・その他）。取引先は「支出先・収入元の口座」として表す。取込は別のアプリ。人ごとに完全に分かれた帳簿で、共有はまだない。添付は口座・請求・予算・カテゴリ・積立・タグ・取引・繰り返しに付く。
- **Actual Budget**：ナビは名だけ（予算・レポート・定期）＋口座の一覧（全口座・予算に入れる・入れない・閉じた）。取引先・ルール・タグは既定で隠し、設定から。取込・照合は口座の画面のボタン（作業はものの中）。複数の人は予算のファイルごとの持ち主と使える人の一覧。添付はない。
- **Fava**：ナビは3つのまとまり（レポート／分析／作業）。**作業（編集・エラー・取込）を独立の項目に置く** 珍しい型。「書類」は口座ごとに日付つきのファイルを並べる見る画面で、書類を口座の名前に落とすと口座のフォルダーへ、仕訳の行に落とすとその取引に `document:` が付く。取込は「取り出す → 見直して保存・とばす」と「書類のフォルダーへ移す」。人という考えはない（タグ・口座の名前で分ける）。

### 家計簿（商用）

- **Quicken（Windows・Mac）**：上のタブは領域（支出・請求と収入・計画・投資・資産と負債）、左は口座の帯（グループごと、取り込み待ちの印、下に純資産）。取り込んだ取引は台帳の下の「取り込んだ取引」タブで受け入れる。税は **カテゴリごとの税の行** → 税のレポート・書き出し、税の見積りは「計画 › 税」の中。家族は1つのファイルの中で、口座を隠す・集計から外す。添付は取引と口座（領収書・請求書・保証書）。
- **Quicken Simplifi**：左の一覧に「領収書」があり、上げた領収書は「要確認」に入り、取引につなぐ・取引を作る・消すまで残る（書類の受信箱）。右上に AI・お知らせ・設定。取引の確認は「確認済み」の丸と絞り込み（未確認・未分類・今月）。
- **YNAB**：スマホの5つは ホーム・予算・取引・口座・振り返り。確認はトップ・台帳の帯「○件の新しい取引」→ 絞り込み・カードで1件ずつ。照合は口座ごと。家族は契約を共にするだけで、予算は人ごとの持ち物（共有すると全員が編集）。持ち主の欄はなく、誰が動かしたかを顔の印で出すだけ。
- **Monarch Money**：1つの世帯に人を招く（役割あり）。**口座と取引に持ち主（共有 or 1人）**、取引は口座から受け継ぎ、上書きできる。持ち主の絞り込みは口座・取引・レポート・収支だけで、予算・定期・目標・投資はいつも世帯全体。取引の「要確認」に **確認する人** を指定でき、ルールでも付く。人を足すとその人の名前のタグができる。領収書はアプリで撮る・メールで送る → 取引につなぐ（金額は上書きしない）。税は「控除」のタグ＋保存したレポート、事業の印 → 事業の様式向けのレポート（公式の書類ではないと明記）。
- **マネーフォワード ME**：アプリの下は ホーム・入出金・家計簿・口座・資産（2026-08 に6→5）、入力は別のボタン。取込の確認の状態はなく、新着として出るだけ。「グループ」は口座の絞り込みで人ではない。2人の共有は金融機関ごとに選び、選ばない口座（お小遣いなど）は自分だけ。申告は、取引ごとの「確定申告」の印と医療費のカテゴリを別の申告アプリへ渡すだけ（同じ ID のときだけ）。レシートは読み取るだけで画像を残さない。

### 日本の会計・申告

- **freee 会計／確定申告**：ナビは **業務の名前**（作）が中心で、ものは「マスタ・口座」にまとめる。ホームに口座ごとの未登録の明細の件数と「やること」。明細は件数のバッジ → 確認の画面で［登録］。申告は「確定申告」→ 段の帯 **基本 → 収支 → 確認 → 提出**。収支の後半は一問一答（「給与を受け取りましたか」「病院に行きましたか」「養っている配偶者はいますか」「扶養家族はいますか」に○×）で、○の話題だけ入力の画面が出る。マイナポータルから取ったものは欄にそのまま入る。家族は申告者の中の「配偶者」「扶養親族」の項目。事業所は増やせるが別の帳簿・別の料金で、合算はできない。
- **マネーフォワード クラウド確定申告**：ナビは作業の名前（データ連携・自動で仕訳・手動で仕訳・取引管理・帳簿・レポート・決算・申告・各種設定）。ホームに連携ごとの未仕訳の件数、個人のホームに **To Do の一覧**（［完了にする］、明細を1件登録すると自動で完了するものもある）。明細の確認は［登録］／［対象外］・まとめて。残高の照合は口座ごとに「一致／不一致」。申告は STEP1〜4。申告書の画面は **様式どおり**（第一表・第二表 › 収入・所得／所得から差し引かれる金額／税金の計算／住民税・事業税）で、右に申告書の写し。入口は3つ（連携で自動の入力／よくある申告から／様式から）。
- **やよいの青色・白色申告 オンライン**：ナビ8は作業の名前が中心（かんたん取引入力・取引の取込・仕訳の入力・レポート・帳簿・確定申告・設定）。取り込んだ取引は「未確定の取引」で 登録する／未定／しない を選び、「確定済みの取引」で見返す。申告は「確定申告の手順」で年と方法を選んでから Step1〜4（印刷で出すなら Step4 は出ない＝選んだ方法で段が変わる）。申告書の中も段の帯（基本情報 → 源泉徴収税 → 所得 → 所得控除（まず「有無を選ぶ」→ 入力）→ 所得税 → その他（一緒に働く家族）→ 住民税・事業税 → 最終確認）。
- **国税庁 確定申告書等作成コーナー**：ナビはなく、1本の手順。最初に「作る（新しく）」か「保存したデータで作る」。事前確認（提出の方法を はい／いいえ で、作る申告書の種類、マイナポータル連携を使うか）→ 申告する所得にチェック（給与なら源泉徴収票の枚数・年末調整済みかを聞く）→ **収入・所得の一覧**（行ごとに「入力あり」、自動で入った行は「確認してください」）→ 控除（支出に関するもの → 家族・本人に関するもの）→ 計算結果の確認（項目ごとに［訂正する］で戻る）→ 還付・納付 → 住民税等の事項 → 基本情報 → 送信。どの画面でも途中で保存でき、ファイルは **1人に1つ**。家族の控除証明書はマイナポータルの代理人の設定で取れる。世帯という考えはない。

### 米国の申告

- **TurboTax**：アカウントの「ホーム」に年ごとの申告と書類（PDF）。申告の中の左は ホーム・私の情報・連邦・州・書類・道具・確認・提出（全体は未確認）。連邦の中は 収入・控除と税額控除・ほかの事情・確認。**話題の一覧**（「始める」「見直す」「更新」）がハブで、上の検索から話題へ飛べる。書類（給与の源泉の票など）は話題の中で、勤め先からの取込・PDF・写真（スマホへ受け渡し）・手入力。扶養家族は「私の情報」で人を足し、続く質問に人が事実を答え、ソフトが規則で判定する。扶養される人が自分で出す申告には「ほかの人に扶養される」の印。**1アカウント＝1申告** で、家族の申告どうしはつながらない。デスクトップは「様式で入れる」と「段で入れる」を切り替えられる。専門家に頼むプランだけ、答えから作る「必要な書類のチェックリスト」がある。
- **H&R Block**：段（個人情報 → 収入 → 控除 → 税額控除 → 税 → 仕上げ）と、連邦・州のあとに「正確さの点検」（直すべきものの一覧。無視もできるが電子申告できないことがある）。デスクトップに様式の一覧（状態の列）。1アカウント＝1申告で、別のアカウントからは前の年の取り込みもできない。

## 3. ほとんどのアプリがしていること

1. **ナビは「もの」の名前を並べる。作業はものの画面の中に置く。** 取込・照合は口座の画面のボタン（Actual・Firefly・YNAB・Quicken）、確認は件数の帯と絞り込み（YNAB・Monarch・Simplifi・MF ME）。作業を独立のナビにするのは Fava（取込・編集・エラー）と、業務の名前でナビを作る日本の会計（freee・MF・やよい）だけ。
2. **確認待ちは「ものの状態」。** 「要確認」「登録待ち」「未仕訳」は取引の状態で、ホームの件数・帯から絞り込んだ一覧へ入る。確認のためだけの受信箱をナビに置くのは、書類（領収書）の受信箱（Simplifi・Monarch）くらい。
3. **ホームは「今やること＋件数」。** freee「やること」・MF の To Do の一覧・Monarch／YNAB の帯・Simplifi の「注意が要るもの」。数字の要約は2番目。
4. **年に一度の申告は、ナビの1項目から入る1本の流れ。** 中は4〜6の **段の帯**（基本 → 収入 → 控除 → 確認 → 提出）。段そのものをナビに並べるアプリはない（TurboTax の左の「連邦・確認・提出」は申告の中に入ってからのナビ）。
5. **段の中は「話題の一覧＋状態」がハブ。** 作成コーナー（入力あり／確認してください）・TurboTax（始める／見直す／更新）・MF（To Do）。入口は「はい／いいえ の質問で話題を選ぶ」（freee・作成コーナー・やよいの有無の選択）。最後に **点検**（エラー・確かめること）と、項目ごとに **戻って直す** リンク。
6. **書類は話題に流れ込む。** 源泉徴収票・控除証明書は、取込・写真・連携で話題の欄に入り、自動で入った値には「確かめて」の印（作成コーナー）。書類を単独のものとして持つのは、会計の証憑の置き場（freee・MF）・Fava の書類・Simplifi／Monarch の領収書。
7. **申告は1人に1つ。** 家族（配偶者・扶養親族）は申告者の申告の中の項目。家族それぞれの申告は別のファイル・別のアカウントで、つながらない（作成コーナー・TurboTax・H&R Block・freee・MF）。**世帯を単位にした申告のアプリはない。**
8. **家計簿の家族は「持ち主の印＋絞り込み」か「別の帳簿」。** 口座に持ち主（共有／1人）を付け、取引が受け継ぐ（Monarch・MF ME の共有）か、人ごとに別の帳簿（YNAB・Firefly・Actual・GnuCash）。予算・目標は世帯全体（Monarch）。
9. **年（年分・会計期間）は申告と帳簿の上の切替え。** 全体のナビにはしない（MF 事業者・年度、TurboTax の年ごとの申告）。
10. **AI・検索は上のバーの右。** Monarch・Simplifi は右上（ナビの項目にしない）。

## 4. okura-web が真似るべき構造

### 4.1 上の階層の「もの」（7つ）

| もの | 中身 | 真似る元 |
|---|---|---|
| **人**（家族） | 世帯の人。人の詳細に：その人の申告（年分ごと）・結果（所得税・住民税・国保・国年・扶養）・書類・記録・共有の同意 | Monarch の世帯の人、TurboTax の「私の情報」 |
| **申告**（人 × 年分） | 1人の1年分の確定申告（申告しない・対象外も状態として持つ）。段と話題の状態を持つ | 作成コーナー・TurboTax・freee（1人に1つ） |
| **書類** | 原本（写真・PDF）。状態：未登録 → 登録済み（記録につながる） | 会計の証憑の置き場、Simplifi の領収書、Fava の書類 |
| **記録** | 申告に使う事実（台帳の行）。状態：AI・未確認／確かめた、提案（確認待ち） | 帳簿の取引、作成コーナーの「確認してください」 |
| **決めること**（判断） | 生計・扶養先などの人が決めること。決める人・決めた人・日時・見直し | Monarch の「確認する人」の指定、TurboTax の扶養の質問 |
| **入出金** | 家計簿の取引。状態：登録待ち | 全部の家計簿アプリ |
| **口座** | 持ち主（人）と 共有／自分だけ | Monarch・MF ME の共有、Quicken の口座の帯 |

- 「計算結果」「申告書（様式の欄）」は **もの** でなく、申告と人の中の見る画面（段）にする。
- 「要確認」（AI の提案）は独立のものでなく、提案先のものの **状態**（記録の「確認待ち」・入出金の「登録待ち」・決めることの「答え待ち」）にし、ホームで件数をまとめる（§3-2）。提案を消さずに印を付ける決まり（AGENTS.md 6）はそのまま。

### 4.2 ナビ

**パソコン（左、8項目）**

| 並び | 項目 | 種類 | 中のタブ・段 | バッジ |
|---|---|---|---|---|
| 1 | ホーム | 見 | やること（決めること・確認待ち・登録待ち・未登録の書類を件数つきで1列）＋人ごとの壁 | — |
| — | 見出し「家計簿」 | | | |
| 2 | 家計簿 | 見 | 収支・予算・推移 | — |
| 3 | 入出金 | 名 | 絞り込み：登録待ち・未分類・人 | 登録待ち |
| 4 | 口座 | 名 | — | — |
| — | 見出し「税金・扶養」 | | | |
| 5 | 確定申告 | 名（ハブ） | 年分の切替え → 人 × 段 の表 → 1人の申告：①書類と記録 → ②決めること → ③結果 → ④申告書 | 決めること（自分あて） |
| 6 | 書類 | 名（＋撮る） | 未登録・登録済み・人で絞り込み | 未登録 |
| 7 | 家族 | 名 | 人の一覧 → 人の詳細（申告の状況・結果・書類・記録・共有） | — |
| — | | | | |
| 8 | 設定 | — | 世帯（メンバー・共有・依頼）／家計簿（カテゴリ・分類ルール）／計算（市区町村・保険者の値・計算の対象）／AI（AI・AI連携）／ログイン | — |

- 「記録」はナビから外し、確定申告の段①・人の詳細・書類の詳細から入る（記録は書類か話題からたどるもの。単独で開く人は少ない）。全部の一覧は ⌘K の検索と、確定申告の中の「記録の一覧」のリンクに残す。
- 「質問」「計算結果」「申告書」は確定申告の中の段にする（§3-4。段をナビに並べるアプリはない）。
- 「AI に聞く」は今のまま上のバーの右（§3-10）。

**スマホ（下の5つ）**

| ホーム | 家計簿 | 書類（撮る） | 確定申告 | その他 |
|---|---|---|---|---|

- 今の「質問」のタブを **確定申告** に替え、バッジ（決めること）をこのタブに付ける。質問はホームのやることと確定申告の段②から入る。
- 入出金は家計簿の中（カテゴリを押す → 入出金）とホームの「登録待ち ○件」の帯から。口座・家族・設定は「その他」。
- 下のタブの数は5（YNAB・MF ME・Monarch と同じ）。

### 4.3 年に一度の申告の置き場所と形

1. **入口はナビの「確定申告」1つ。** 開くと年分の切替え（既定は今申告する年分）と、**人 × 段 の表**（世帯のハブ。どのアプリにもないが、TurboTax の「年ごとの申告」と作成コーナーの「一覧＋状態」を人の分だけ並べたもの）。
   - 行＝人（申告する人・申告しない人・扶養に入る人）。列＝段①〜④の状態（未着手／確認してください／済み）。押すとその人の申告へ。
   - 扶養など **人をまたぐ決めること** は表の上に1列で出す（誰の申告に効くかを添える）。
2. **1人の申告の中は段の帯4つ**（freee・MF・やよい・作成コーナーと同じ形）：
   - ① **書類と記録**：話題の一覧（給与・年金・事業・医療費・社会保険料・生命保険料・寄附金・住宅ローン…）。行ごとに「入力あり」「確認してください」（AI・未確認）「なし」。行から書類を足す・記録を見る（作成コーナー・TurboTax の話題の一覧）。どの話題を出すかは、最初の はい／いいえ の質問（freee・作成コーナー）。
   - ② **決めること**：その人に関わる判断（生計・扶養先・還付申告をするか）。答えごとに何が変わるかを見せる（既存）。人をまたぐものは世帯のハブと同じものを出す。
   - ③ **結果**：所得税・住民税・国保・国年・扶養の値と根拠・境目・未確定・対象外（丸めない）。最後に「確かめること」の一覧（H&R Block・TurboTax の点検にあたる）。各行から①②へ戻る（作成コーナーの［訂正する］）。
   - ④ **申告書**：様式の欄ごとの値（第一表・第二表の並び、MF の様式どおりの画面）・コピー・「写した」の印。提出は作成コーナーで人が行う（e-Tax への送信はしない）。
3. **書類は2つの入口から同じところへ。** 書類（撮る）から入れたものも、話題の行から足したものも、同じ書類と記録になり、話題の状態に反映する。自動で入った値は「確認してください」（作成コーナー）。
4. **申告しない人も行に出す。** 扶養に入るだけの人・住民税だけの人も、表の行で状態（申告しない・住民税の申告が要る など判定コアの値）を見せる。決めるのは人、値は判定コアのまま（AGENTS.md 4・5）。

### 4.4 家族の出し方

| 場所 | 出し方 | 真似る元 |
|---|---|---|
| 家計簿（家計簿・入出金・口座） | 口座に持ち主と 共有／自分だけ、入出金は受け継ぐ。上に 全員／人 のチップ。予算は世帯全体 | Monarch・MF ME の共有（詳しくは `household-ui-references.md` §3.7） |
| 確定申告 | **人ごとに1つの申告**（1人1年分）。世帯のハブで全員を1つの表に。扶養される人は扶養する人の申告の中の項目として出し、その人の行にも「○○さんの扶養」と出す | 作成コーナー・TurboTax（1人1申告・扶養家族は申告の中）＋世帯の表（okura-web の追加） |
| 決めること | 決める人（宛先）を持ち、ホーム・招待リンクにその人あてだけ出す。決めた人と日時を残す | Monarch の「確認する人」 |
| 書類・記録 | 「誰の」書類か（人）の印と絞り込み。見える範囲は本人の同意 | Monarch の持ち主の絞り込み |
| 人の詳細 | 1人のまとめ：その年の申告の状況・結果・壁・書類・共有の同意 | TurboTax の「私の情報」、Monarch のメンバー |

- 「今は誰として見ているか」の **全体の切替え（人のモード）は作らない**。人は絞り込みのチップと、表の行で出す（どのアプリも世帯の中で人を切り替えるモードを持たない。別の人は別のアカウント・ファイルで、それが家族をつなげない原因になっている）。
- 年分は確定申告と結果の上の切替えだけ（全体のナビにしない）。

### 4.5 やらないこと

| やらないこと | 理由 |
|---|---|
| 申告の段（質問・結果・申告書）をナビに並べる | 段は申告の中の帯（§3-4） |
| 確認待ちのためだけのナビの項目を増やす | 状態と件数で出す（§3-2）。ホームのやることにまとめる |
| 業務の名前でナビを作る（freee・MF・やよいの型） | 会計の仕事の人向け。家族は「もの」で探す（家計簿のアプリの型） |
| 人ごとに別の帳簿・別のアカウントにする | 扶養の判定に全員の記録が要る。見え方は同意で分ける（README §3） |
| 様式で直接入れる画面（作成コーナー・デスクトップの様式の入力） | 法令の計算はアプリでしない。様式の欄は結果を写す画面だけ（AGENTS.md 5） |

## 5. 出典

### OSS
- GnuCash：https://code.gnucash.org/docs/C/gnucash-manual/ ・ https://code.gnucash.org/docs/C/gnucash-manual/gui-acct-tree.html ・ https://code.gnucash.org/docs/C/gnucash-manual/trans-import.html ・ https://code.gnucash.org/docs/C/gnucash-manual/set-tax-options.html ・ https://code.gnucash.org/docs/C/gnucash-manual/trans-assoc.html ・ https://lists.gnucash.org/pipermail/gnucash-user/2012-February/043016.html ・ https://svn.gnucash.org/pipermail/gnucash-user/2008-April/024694.html
- KMyMoney：https://invent.kde.org/office/kmymoney/-/raw/master/kmymoney/views/viewenums.h ・ https://invent.kde.org/office/kmymoney/-/raw/master/kmymoney/views/kmymoneyview.cpp ・ https://invent.kde.org/office/kmymoney/-/raw/master/doc/details-ledgers.docbook ・ https://invent.kde.org/office/kmymoney/-/raw/master/doc/details-impexp.docbook ・ https://invent.kde.org/office/kmymoney/-/raw/master/doc/details-reconciliation.docbook ・ https://invent.kde.org/office/kmymoney/-/raw/master/doc/details-categories.docbook ・ https://bugs.kde.org/show_bug.cgi?id=464905
- HomeBank：https://gethomebank.org/help/00-lexicon.html ・ https://gethomebank.org/help/win-main.html ・ https://gethomebank.org/help/menu-main.html ・ https://www.gethomebank.org/help/use-import.html
- Firefly III：https://github.com/firefly-iii/firefly-iii/blob/v6.7.9/resources/views/components/layout/sidebar.blade.php ・ https://github.com/firefly-iii/firefly-iii/blob/v6.7.9/config/firefly.php ・ https://github.com/firefly-iii/docs/blob/main/docs/docs/explanation/data-importer/introduction.md ・ https://github.com/firefly-iii/docs/blob/main/docs/docs/how-to/firefly-iii/finances/reconcile.md ・ https://github.com/firefly-iii/docs/blob/main/docs/docs/how-to/firefly-iii/features/multi-user.md ・ https://github.com/firefly-iii/docs/blob/main/docs/docs/explanation/financial-concepts/administrations.md
- Actual Budget：https://github.com/actualbudget/actual/blob/v26.11.0/packages/desktop-client/src/components/sidebar/sidebarMenu.ts ・ https://github.com/actualbudget/actual/tree/v26.11.0/packages/desktop-client/src/components/sidebar ・ https://actualbudget.org/docs/transactions/importing/ ・ https://actualbudget.org/docs/budgeting/rules/ ・ https://actualbudget.org/docs/accounts/reconciliation/ ・ https://actualbudget.org/docs/config/multi-user/ ・ https://github.com/actualbudget/actual/issues/8575
- Fava・beancount：https://github.com/beancount/fava/blob/main/frontend/src/sidebar/AsideContents.svelte ・ https://github.com/beancount/fava/blob/main/src/fava/help/import.md ・ https://github.com/beancount/fava/blob/main/src/fava/help/features.md ・ https://github.com/beancount/fava/blob/main/src/fava/help/filters.md ・ https://beancount.github.io/docs/beancount_language_syntax/

### 家計簿（商用）
- Monarch：https://help.monarch.com/hc/en-us/articles/360048393272-Getting-Started-with-Monarch ・ https://help.monarch.com/hc/en-us/articles/360048393532-Editing-Transactions ・ https://help.monarch.com/hc/en-us/articles/44244210547860-Importing-Receipts-into-Monarch ・ https://help.monarch.com/hc/en-us/articles/16116906962452-About-Monarch-s-AI-Features ・ https://www.monarch.com/ipad-support-budget-enhancements-and-more ・ https://www.monarchmoney.com/new-mobile-navigation ・ https://help.monarch.com/hc/en-us/articles/5528707082516-Reviewing-Transactions ・ https://help.monarch.com/hc/en-us/articles/360048393372-Transaction-Rules ・ https://help.monarch.com/hc/en-us/articles/21846787088916-Using-Reports ・ https://help.monarch.com/hc/en-us/articles/48344411171092-Business-Tracking ・ https://help.monarch.com/hc/en-us/articles/20926382202004-Monarch-for-Couples-and-Households ・ https://help.monarch.com/hc/en-us/articles/42228648365076-Shared-Views-in-Monarch ・ https://www.monarch.com/blog/shared-views ・ https://help.monarch.com/hc/en-us/articles/4409690120596-Organizing-Transactions-with-Tags ・ https://help.monarch.com/hc/en-us/articles/360056422791-Adding-Notes-and-Attachments-to-a-Transaction
- YNAB：https://support.ynab.com/en_us/account-types-an-overview-BkmGM0qCq.md ・ https://support.ynab.com/en_us/navigating-multiple-plans-r1qeOvbC5.md ・ https://support.ynab.com/en_us/approving-and-matching-transactions-a-guide-ByYNZaQ1i.md ・ https://support.ynab.com/en_us/spaces-in-the-mobile-app-S1iIZQoqgg.md ・ https://support.ynab.com/en_us/reconciling-accounts-a-guide-BJFE3fHys.md ・ https://support.ynab.com/en_us/tax-season-with-ynab-rkGAspIrT.md ・ https://support.ynab.com/en_us/ynab-together-B1nS78Cki.md ・ https://support.ynab.com/en_us/add-context-to-transactions-HyCpTR4bg.md
- Quicken：https://info.quicken.com/win/using-tabs ・ https://info.quicken.com/win/about-the-account-bar ・ https://info.quicken.com/mac/the-quicken-sidebar ・ https://www.quicken.com/support/handling-downloaded-transactions ・ https://info.quicken.com/win/taxes ・ https://info.quicken.com/win/about-using-the-tax-planner-to-estimate-taxes ・ https://info.quicken.com/win/managing-quicken-files ・ https://info.quicken.com/win/attaching-images-to-transactions-and-accounts ・ https://community.quicken.com/discussion/comment/20384488
- Quicken Simplifi：https://info.quicken.com/sim/navigating-your-dashboard ・ https://support.simplifi.quicken.com/en/articles/6098227-getting-started-on-the-mobile-app ・ https://info.quicken.com/sim/reviewing-transactions ・ https://info.quicken.com/sim/managing-expense-receipts ・ https://info.quicken.com/sim/attaching-receipts-to-transactions ・ https://community.simplifimoney.com/discussion/10091/merged-share-space-with-multiple-people
- マネーフォワード ME（`https://support.me.moneyforward.com/hc/ja/articles/<id>`）：4406430145049・24226189541401・900003528186・900003480266・4406436477081・24478005732889・60075157394201・900003501426・900004194866・900005145123・50601549876889・900004380863・48106653876761・4407236518425・4407836867737 ／ https://www.appbank.net/2026/08/19/iphone-news/3081407.php

### 日本の会計・申告
- freee：https://support.freee.co.jp/hc/ja/articles/40849745400857 ・ https://support.freee.co.jp/hc/ja/articles/900004316703 ・ https://support.freee.co.jp/hc/ja/articles/12582680429593 ・ https://support.freee.co.jp/hc/ja/articles/204087130 ・ https://support.freee.co.jp/hc/ja/articles/900004218706 ・ https://support.freee.co.jp/hc/ja/articles/202848320
- マネーフォワード クラウド確定申告：https://biz.moneyforward.com/support/tax-return/tax-return-guide/bs2/bs225.html ・ https://biz.moneyforward.com/support/tax-return/guide/comparison/comparison_balance.html ・ https://biz.moneyforward.com/support/account/guide/journal02/jo02.html ・ https://biz.moneyforward.com/support/tax-return/guide/others/ot06.html ・ https://biz.moneyforward.com/support/tax-return/guide/journal02/jo01.html ・ https://biz.moneyforward.com/support/tax-return/tax-return-guide/flow/first_step_guide.html ・ https://biz.moneyforward.com/support/tax-return/tax-return-guide/bs2/taxreturn-form.html ・ https://biz.moneyforward.com/support/tax-return/tax-return-guide/bs2/bs201.html ・ https://biz.moneyforward.com/support/account/faq/price/p04.html
- やよい：https://support.yayoi-kk.co.jp/product/aoiro_ol/home_m.html ・ https://support.yayoi-kk.co.jp/product/shiroiro_ol/home_m.html ・ https://support.yayoi-kk.co.jp/product/aoiro_ol/smart_m_03.html ・ https://support.yayoi-kk.co.jp/subcontents.html?page_id=27084 ・ https://support.yayoi-kk.co.jp/subcontents.html?page_id=27167 ・ https://support.yayoi-kk.co.jp/faq_Subcontents.html?page_id=30812 ・ https://support.yayoi-kk.co.jp/faq_Subcontents.html?page_id=30852
- 国税庁 確定申告書等作成コーナー：https://www.nta.go.jp/taxes/shiraberu/shinkoku/kakutei/pdf/r07/sakukonatebiki/pc.pdf （令和7年分 パソコンご利用ガイド p.3〜32）・ https://www.keisan.nta.go.jp/r7yokuaru_sp/r7myna_sp/myna1/scid0226.html ・ https://www.keisan.nta.go.jp/r6yokuaru_sp/cat1/cat16/cat162/index.html ・ https://www.e-tax.nta.go.jp/toiawase/faq/gaiyo/03_1.pdf （検索結果の抜粋）

### 米国の申告
- TurboTax：https://ttlc.intuit.com/turbotax-support/en-us/help-article/prior-year-tax-return/find-returns-prior-years/L0BkZFwVJ_US_en_US ・ https://ttlc.intuit.com/turbotax-support/en-us/help-article/printers/print-copy-turbotax-online-return-file/L5tOKFAdV_US_en_US ・ https://ttlc.intuit.com/turbotax-support/en-us/help-article/small-business-processes/add-remove-dependent/L5MKscASB_US_en_US ・ https://ttlc.intuit.com/turbotax-support/en-us/help-article/review-tax-return/fix-looping-federal-review-turbotax-online/L9m8omBKl_US_en_US ・ https://ttlc.intuit.com/turbotax-support/en-us/help-article/small-business-processes/switch-forms-mode-turbotax-windows-software/L8KBHZThl_US_en_US ・ https://ttlc.intuit.com/turbotax-support/en-us/help-article/customer-full-service-product/send-documents-tax-expert/L2RftrFOJ_US_en_US ・ https://ttlc.intuit.com/turbotax-support/en-us/help-article/import-export-data-files/transfer-last-year-return-turbotax-online/L279eUvY2_US_en_US ・ https://ttlc.intuit.com/turbotax-support/en-us/help-article/tax-return/indicate-claimed-dependent-someone-elses-return/L2RsKfiEG_US_en_US ・ https://ttlc.intuit.com/turbotax-support/en-us/help-article/import-export-data-files/import-enter-w-2/L55HzdeDr_US_en_US ・ https://ttlc.intuit.com/community/credits-and-deductions/help/who-can-i-claim-as-my-dependent/00/26781 ・ コミュニティ（未確認の点）：https://ttlc.intuit.com/community/taxes/discussion/where-is-the-left-menu-i-am-on-the-turbotax-welcome-to-turbotax-page-help-bot-said-to-go-to-left/00/2808554 ・ https://ttlc.intuit.com/community/taxes/discussion/where-is-finish-and-file/01/3875335 ・ https://ttlc.intuit.com/community/taxes/discussion/when-i-go-to-wages-and-income-i-need-a-start-box-on-the-right-for-my-first-w2/00/768777 ・ https://ttlc.intuit.com/community/taxes/discussion/can-you-file-a-second-return-for-my-daughter-on-the-same-turbo-tax/00/2699148
- H&R Block：https://www.hrblock.com/tax-center/support/online/technical-issues-online/copy-of-previous-tax-returns/ ・ https://www.hrblock.com/tax-center/support/online/online-tax-filing/prepare-to-file-taxes-online/deluxe-filing-for-multiple-returns/ ・ https://www.hrblock.com/tax-center/support/online/while-filing-online-return/filing-state-taxes/ ・ https://www.hrblock.com/tax-center/support/online/online-tax-filing/prepare-to-file-taxes-online/accuracy-guarantee/ ・ https://www.hrblock.com/tax-center/support/online/online-tax-filing/prepare-to-file-taxes-online/supported-forms/ ・ https://www.hrblock.com/tax-center/support/software/software-tax-filing/while-filing-software-return/determining-final-tax-forms/ ・ https://www.hrblock.com/tax-center/support/online/online-tax-filing/while-filing-online-return/start-return-over/ ・ https://www.hrblock.com/tax-center/support/software/software-tax-filing/while-filing-software-return/photo-capture/ ・ レビュー：https://moneydoneright.com/hr-block-review ・ https://financebuzz.com/hr-block-tax-software-review ・ https://clubthrifty.com/hr-block-online-review/

調査の範囲：公開のページだけ。freee・MF ME のヘルプは各ヘルプセンターの公開の読み取り API で本文を読んだ。H&R Block のヘルプは自動の取得を断られたため、公式のページの検索結果の抜粋とレビューに拠る（ナビの項目と数は未確認）。Monarch の Web の左の全体、MF クラウド確定申告の左の並び、YNAB の Web の振り返りの位置も公式の文書では確かめられなかった。ラベルは年・版・プランで変わる。
