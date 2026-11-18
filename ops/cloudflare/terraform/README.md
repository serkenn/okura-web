# Cloudflare を Terraform で管理する（トンネル・URL・GitHub でログイン）

okura-web を家の外から使うための Cloudflare の設定を、Terraform で作る・変える・消す。

| 管理するもの | リソース |
|---|---|
| cloudflared との接続 | トンネル（設定は Cloudflare 側に置く）と、流し先（`hostname` → `origin_service`） |
| URL | `hostname` の DNS（トンネルへの CNAME） |
| ログイン | GitHub をログインの方法として登録し、Access のアプリとポリシー（開いてよい人）を作る |
| リモートの MCP | `/mcp` だけ Access を通さないアプリ（`mcp_bypass`。アプリが `okt_…` のトークンで守る。README §8） |
| 手元のファイル | `.work/cf-access.json`（アプリが JWT を確かめる設定）・`.work/cloudflare.env`（公開のホスト名とトンネルのトークン） |

アプリのコードは Cloudflare を知らないまま（AGENTS.md 9）。アプリは `.work/cf-access.json` を読んで JWT を確かめるだけで、ここは運用の手順。
`ops/cloudflare/setup-access.ps1`（メールアドレスの許可だけ）と同じ Access のアプリを作るので、**どちらか一方**を使う（§5）。

## 1. 先に用意するもの（1回だけ）

1. **Zero Trust のチーム**：Cloudflare のダッシュボードで Zero Trust を一度開いて、チーム名を決める（Free プランでよい）。
   チームのドメインは `<チーム名>.cloudflareaccess.com`。
2. **GitHub の OAuth App**：GitHub → Settings → Developer settings → OAuth Apps → New OAuth App。

   | 欄 | 値 |
   |---|---|
   | Homepage URL | `https://<チーム名>.cloudflareaccess.com` |
   | Authorization callback URL | `https://<チーム名>.cloudflareaccess.com/cdn-cgi/access/callback` |

   Client ID と、作った Client secret を控える。Organization で絞るときは、その Organization の OAuth App にするか、Organization の側でこの App を承認する。
3. **Terraform** 1.9 以上。

## 2. API トークン

ダッシュボード → My Profile → API Tokens → Create Custom Token。権限：

| 範囲 | 権限 |
|---|---|
| Account | Cloudflare Tunnel：Edit |
| Account | Access: Apps and Policies：Edit |
| Account | Access: Organizations, Identity Providers, and Groups：Edit |
| Zone（使うドメインだけ） | Zone：Read、DNS：Edit |

秘密はファイルに書かず、環境変数で渡す：

```
export CLOUDFLARE_API_TOKEN=…
export TF_VAR_github_client_secret=…
```

## 3. 作る

```
cd ops/cloudflare/terraform
cp terraform.tfvars.example terraform.tfvars     # zone・hostname・github_client_id・allowed_emails を書く
terraform init
terraform plan
terraform apply
```

できたら、リポジトリの根でコンテナを起動する（`compose.yaml` に `compose.cloudflare.yaml` を重ねる）：

```
podman compose --env-file .work/cloudflare.env -f compose.yaml -f compose.cloudflare.yaml up -d --build
```

`https://<hostname>/` を開くと GitHub のログインに進み、許可した人だけが okura-web に届く。

- cloudflared は外（Cloudflare）へつなぎに行くだけで、ポートを開けない。okura-web のポートは `127.0.0.1:8765` のまま。
- okura-web は `--public-host <hostname>` で起動し、公開の URL から来たリクエストの Access の JWT を自分でも確かめる（二重の守り。README §14）。
- コンテナを使わない（同じ PC で直接動かす）ときは、`origin_service = "http://127.0.0.1:8765"` にして、cloudflared を
  `cloudflared tunnel --no-autoupdate run --token "$(terraform output -raw tunnel_token)"` で動かす。

## 4. 変える

`terraform.tfvars` を書き換えて `terraform apply`。

| したいこと | 変える値 |
|---|---|
| 開いてよい人を足す・外す | `allowed_emails`（GitHub のアカウントの**主のメールアドレス**。GitHub で公開していなくてもよい） |
| GitHub の Organization・Team で決める | `github_organization`・`github_teams`（メールアドレスと「どちらか」で通る） |
| URL を変える | `hostname`（DNS・流し先・Access のアプリが変わる。apply のあとコンテナを起動し直す） |
| ログインし直すまでの時間 | `session_duration` |
| `/mcp` も Access を通す | `mcp_bypass = false`（Cookie を持てない MCP のクライアントは使えなくなる） |

- ポリシーは「メールアドレスか Organization のどちらかに当てはまる」**かつ**「GitHub でログインした」。ほかのログインの方法（ワンタイム PIN など）では通らない。
- 人を外しても、その人のログイン済みのセッションは `session_duration` の間は残る。すぐ切るときは、ダッシュボードの Zero Trust → ユーザーからセッションを取り消す。
- 回答の依頼（招待リンク。README §15）でメールアドレスを入れた相手は、ここでも許可する（Access を通れないとリンクを開けない）。
- `hostname` を変えると `.work/cloudflare.env` が変わる。`podman compose … up -d` をやり直す。

## 5. すでに手で作ったものがあるとき

同じホスト名の Access のアプリ・DNS のレコード・トンネルがすでにあると、作るところでぶつかる。取り込むか、古いほうを消してから apply する：

```
terraform import cloudflare_zero_trust_access_application.okura 'accounts/<account_id>/<app_id>'
terraform import cloudflare_dns_record.okura '<zone_id>/<dns_record_id>'
```

`setup-access.ps1` で作ったアプリの ID は `.work/cf-access.json` の `app_id`。Terraform に移したあとは `setup-access.ps1` を使わない（次の apply で書き戻される）。

## 6. 秘密の置き場所

| もの | 中身 | 扱い |
|---|---|---|
| `terraform.tfstate` | トンネルのトークン・GitHub の Client secret が**平文で入る** | git に入れない（`.gitignore`）。バックアップするなら暗号化する。共有するなら暗号化できるバックエンドに置く |
| `.work/cloudflare.env` | トンネルのトークン | 持ち主だけが読める（0600）。git にもイメージにも入らない |
| `.work/cf-access.json` | チームのドメインと AUD（秘密ではない） | コンテナに読み取り専用でマウントする |
| `terraform.tfvars` | ドメイン・メールアドレス | git に入れない |

トンネルのトークンが漏れたら、トンネルを作り直す（`terraform apply -replace=cloudflare_zero_trust_tunnel_cloudflared.okura`。DNS と流し先も付け替わる）。

## 7. 消す

```
terraform destroy
```

トンネル・DNS・Access のアプリとポリシー・GitHub のログインの登録と、`.work/` の2つのファイルが消える。家族のデータ（コンテナのボリューム）には触れない。

## 8. 版

- プロバイダー：`cloudflare/cloudflare` 5.29 系（リソースの名前は v5 のもの）、`hashicorp/local` 2.9 系。
  最初の `terraform init` でできる `.terraform.lock.hcl` はコミットする（プロバイダーの版とハッシュが固定される）。
- cloudflared：`compose.cloudflare.yaml` で版とダイジェストを固定している。
