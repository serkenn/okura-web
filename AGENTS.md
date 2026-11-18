# AGENTS.md（okura-web）

okura-web は okura-gov（`vendor/okura-gov`、サブモジュール）の外側（保存・画面・アカウント・AI・エージェント連携）を作るアプリ。
最初に README.md と、okura-gov の AGENTS.md・HANDOFF.md・SCOPE.md・packages/core/README.md を読む。

## 守ること

1. **okura-gov の中にアプリのコードを入れない。書き換えない。** 版（コミット）を固定して使う。計算の不具合は okura-gov 側で（okura-gov の AGENTS.md の手順で）直し、
   `vendor/okura-gov` の版を上げてコミットする。`okura_web/bridge/*.py` はアプリのコードで、okura-gov の仮想環境で動かすだけ。
2. **プロセスを分ける。** Web のサーバー（`okura_web/`）は okura_core・okura_records・openfisca・beancount を import しない。呼ぶのは `okura_web/engine.py` の
   サブプロセスだけ。Python は必ず `-I -X utf8` で起動する。仮想環境は `tools/setup_env.py`（wheel だけ、okura_dev.pth）。
3. **家族の機微な情報。** 実際の家族のデータ（data/ の中身・台帳・中間表現・結果・写真）を、ログ・エラー・テスト・issue・外部のサービスに出さない。
   テストのデータは架空の家庭だけ。マイナンバーの欄を作らない。外部の LLM・MCP に渡すものは `access.redact_record` と同意（external_ai）を通す。
   クラウドに置く・外部に送る範囲を広げる変更は、ユーザーに確認してから。
4. **人が決めることを AI に決めさせない。** 道具（`okura_web/tools.py`）に確定（台帳への書き込み）を足さない。書き込みの API は画面のセッション（人）だけ
   （`server.py` の token_ok を付けない）。判断・選択には決めた人と日時を入れ、見直しは `replaces` で追記する。
   招待リンクの端末（guest）は本人あての「選んで答える」判断だけ（`guest_ok` の経路。ほかの API は 403）。
5. **結果を黙って丸めない。** 判定コアの値をそのまま出す。未確定・対象外・幅・状態（予測など）を消さない。アプリで法令の計算をしない
   （境目を収入に直すなどの法令の換算をしない。法令の知識は okura-gov にだけ置く）。
6. **追記のみ。** 台帳の訂正・取消しは op: correct・delete と理由。原本（evidence/）は書き換えない。同意・注入データ・提案も消さずに印を付ける。
7. **新しいサードパーティの依存を足さない**（Web のサーバー・MCP のサーバーは標準ライブラリだけ。画面は下の例外の React 一式だけ）。足すならユーザーに確認し、使う前に安全性を確かめる（ユーザーのグローバルの指示）。
   いまの例外（2026-11-17 に確かめた）：パスキーの `webauthn` 一式は専用の仮想環境 `.work/venvs/auth` に版とハッシュを固定して入れ（`tools/auth-requirements.txt`）、
   `okura_web/bridge/passkey.py` をサブプロセスで動かす（Web のサーバーは import しない）。画面（2026-11-18 に確かめた）：`react`・`react-dom`・`react-router`（ブラウザに入る）と、ビルドと型の確認だけの `vite`・`@vitejs/plugin-react`・`typescript`・`@types/*`。
   版は `package.json` に固定（範囲指定にしない）、中身は `package-lock.json`。入れるときは必ず `npm ci --ignore-scripts`（インストール時のスクリプトを動かさない）。
   Vite の開発サーバーは 127.0.0.1 だけで使い、外に出さない。既知の警告：vite が使う picomatch の ReDoS（GHSA-fc5q-39xc-vjpf。修正版なし。ビルドのときに自分のパターンでしか使わないので受け入れた）。
   版を上げるときは安全性を確かめ直す（cbor2・pyasn1 は古い版にサーバーを落とせる穴がある。npm は `npm audit`・`npm audit signatures`・公開から日の浅い版を避ける）。
8. **画面にシステムの中の名前（英字の欄名・ID・JSON）を出さない。** 欄と選択肢の日本語名は `tools/labels_vocab.json`（`tools/build_labels.py` で `frontend/src/lib/labels_vocab.js` を作る）。
   okura-gov の版を上げたら `node tools/check_labels.mjs <meta_records.json>` で足りない名前がないか確かめる（中身は check_labels.mjs の先頭）。
9. **公開の仕方（Cloudflare など）に依存しない。** アプリは手前の認証を `proxyauth.py`（JWKS の URL・発行元・宛先・ヘッダーの設定）でしか知らない。
   特定の会社の API をアプリから呼ばない（Access の許可リストの変更などは運用の手順 `ops/` に置く）。

## 地図

| 場所 | 中身 |
|---|---|
| `okura_web/engine.py` | okura-gov の窓口（サブプロセス）：build-ir・append・transactions・evaluate・語彙と注入点・版 |
| `okura_web/ledgers.py` | 世帯の台帳の置き場所と書き込み（写しで検査してから置き換える）、証憑の保存 |
| `okura_web/app.py` | 組み立て、計算のジョブ（バックグラウンド・キャッシュ） |
| `okura_web/api.py` | 画面の API（人のセッション）。`api_agent.py`：エージェントの API・アプリ内の AI・読み取り |
| `okura_web/api_invite.py` | 回答の依頼（招待リンク・その人の端末・本人の回答） |
| `okura_web/api_passkey.py`・`bridge/passkey.py` | パスキーでのログイン（webauthn は .work/venvs/auth のサブプロセス） |
| `okura_web/book.py`・`api_book.py` | 家計簿（出来事の記録 book.jsonl → beancount の写し。取り込みの API・取り込み待ち・月の収支）。`docs/import-api.md` |
| `okura_web/proxyauth.py` | 手前の認証の JWT の検証（汎用。Cloudflare Access の設定も読める） |
| `okura_web/access.py` | 同意・見える範囲・伏せ字 |
| `okura_web/results.py` | 結果のまとめ（質問・境目・対象外・様式）。丸めない |
| `okura_web/tools.py` | エージェントの道具（読む・計算する・説明する・提案する） |
| `okura_web/agent.py` | OpenAI 互換の API の会話（添付・カード）と写真の読み取り。画面は `frontend/src/views/Chat.tsx`、設計は `docs/chat.md` |
| `okura_web/sheets.py` | Excel・CSV を AI に渡す表の文字にする（標準ライブラリだけ） |
| `mcp_server.py` | MCP のサーバー（stdio → /api/v1/tools） |
| `frontend/` | 画面（Vite + React + React Router + TypeScript）。`src/main.tsx`（起動と経路）・`src/Shell.tsx`（枠組み）・`src/views/`（画面）・`src/lib/`（通信 `api.ts`・読み取りのフック `useApi.ts`・共有の状態 `store.ts`・入力フォーム `forms.tsx`）・`src/ui/`（部品・ダイアログ）。ビルドの出力 `frontend/dist/` をサーバーが配る（git に入れない）。情報設計（もの・ナビ）は `docs/ia-model.md`（根拠：`docs/ia-methods.md`・`docs/ia-competitors.md`）。確定申告の世帯の表・1人の申告は `frontend/src/views/Tax.tsx` |
| `Containerfile`・`compose.yaml`・`.dockerignore` | AlmaLinux 9 のコンテナで動かす（コミットした内容だけをイメージに入れる）。手順は `ops/container/README.md` |
| `tests/` | ユニットテスト（架空の家庭） |

## テスト

```
.work/venvs/web/Scripts/python.exe -I -X utf8 -m unittest discover -s tests -t .
```

ユニットテストだけ。サブプロセス・ネットワーク・okura-gov の計算を通すテストは作らない。

画面（初回は `npm ci --ignore-scripts`）。**画面を直したら、型を確かめてビルドする**（サーバーは `frontend/dist/` を配る。ビルドしないと反映されない）：

```
npm run check    # 型の確かめ
npm run build    # frontend/dist/ を作る
npm run dev      # 開発（127.0.0.1:5173。API は OKURA_API のサーバーへ中継。既定は 127.0.0.1:8799）
```

画面の決まり：読み取りは `useApi(path)`（書き込みのあと自動で取り直す）。API の値を書き換えない。重ねて出すものは `ui/overlay`（`modal`・`openDrawer`・`openSheet`・`toast`）。
`dangerouslySetInnerHTML` を使わない。画面の中のリンクは `<Link to="/…">`（道は `src/main.tsx`）。古いリンク（`#/…`）は起動のときに新しい道へ直す。
