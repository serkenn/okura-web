# コンテナで動かす（AlmaLinux 9）

okura-web を AlmaLinux 9 のコンテナで動かす手順。podman でも docker でも同じファイルを使う。

| ファイル | 中身 |
|---|---|
| `Containerfile` | イメージの作り方（リポジトリの根） |
| `.dockerignore` | ビルドに渡さないもの（`data/`・`.work/` など） |
| `compose.yaml` | 動かし方（ポート・データのボリューム・書き込めない根） |

アプリのコードは変えていない。

## 1. 始め方

```
git submodule update --init          # okura-gov（固定した版）
podman compose up -d --build         # docker compose up -d --build でも同じ
```

http://127.0.0.1:8765/ を開くと、最初の設定（世帯・あなたのアカウント）になる。

compose を使わないとき：

```
podman build -t okura-web .
podman volume create okura-web-data
podman run -d --name okura-web -p 127.0.0.1:8765:8765 -v okura-web-data:/var/lib/okura-web \
  --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges okura-web
```

docker で `docker build` を使うときは `-f Containerfile` を付ける。

- **イメージに入るのはコミットした内容だけ。** ビルドの中でリポジトリを `git clone` するので、手元の `data/`・`.work/`・コミットしていない書き換えは入らない。
  直したものを試すときは、コミットしてからビルドする。
- `vendor/okura-gov` が固定した版（サブモジュールの記録）と違うコミットだと、ビルドが止まる。`git submodule update` で合わせる。
- ビルドには `.git` が要る（`git clone` したディレクトリの根でビルドする。zip で取った写しではできない）。

## 2. 開ける範囲

| 使い方 | 設定 |
|---|---|
| このコンピューターだけ（既定） | `compose.yaml` のまま。ポートは `127.0.0.1:8765` にだけ出る |
| 家の LAN から | `ports` を `"8765:8765"` にして、`command: ["--allow-host", "192.168.x.x:8765"]`（ブラウザに打つアドレスとポート）。HTTP は暗号化されないので家の LAN の中だけで |
| 手前の認証つきで公開 | `command: ["--public-host", "okura.example.com"]` と、`.work/proxy-auth.json` か `.work/cf-access.json` を `/opt/okura-web/.work/` に読み取り専用でマウント（README §14）。設定がない間は、公開の URL からのリクエストを全部 403 で断る |

コンテナの中では `0.0.0.0` で待ち受ける（`OKURA_WEB_HOST`）。外に出す範囲を決めるのは、公開するポートの側。
起動のときに「127.0.0.1 以外で待ち受けている」の注意が出るのはこのため。Host のヘッダーの検査（`--allow-host`）はコンテナでも同じに効く。

ポートを変えるときは、外側だけを変える（例 `"127.0.0.1:9000:8765"`）と Host のヘッダーが合わなくなる。
`OKURA_WEB_PORT=9000` と `"127.0.0.1:9000:9000"` のように、中と外を同じにする。

## 3. データ

- 家族のデータ（SQLite・台帳・写真・結果）は `/var/lib/okura-web`（`OKURA_WEB_DATA`）。名前つきのボリューム `okura-web-data` に置く。イメージには入らない。
- コンテナの中のユーザーは UID 10001（root ではない）。ホストのディレクトリをマウントするときは、そのディレクトリを UID 10001 が書けるようにする
  （rootless の podman なら `podman unshare chown 10001:10001 <ディレクトリ>`。SELinux が有効なら `:Z` を付ける）。
- バックアップは、コンテナを止めてからボリュームを写す：

```
podman compose stop
podman run --rm -v okura-web-data:/data:ro -v "$PWD":/backup:Z docker.io/library/almalinux:9 \
  tar -C /data -czf /backup/okura-web-data.tar.gz .
podman compose start
```

  写したファイルは家族のデータそのもの。置き場所に気をつける。
- 根のファイルシステムは書き込めない（`read_only`）。書けるのはデータのボリュームと `/tmp`（メモリ上）だけ。

## 4. コンテナの中から外へ

- **アプリ内の AI**：既定の `http://127.0.0.1:11434/v1` は、コンテナの中ではコンテナ自身を指す。ホストで動く Ollama などを使うときは、
  設定 → AI の URL を `http://host.containers.internal:11434/v1`（podman）・`http://host.docker.internal:11434/v1`（docker）にする
  （Linux の docker は `extra_hosts: ["host.docker.internal:host-gateway"]` が要る。Ollama 側もその経路で待ち受けていること）。
- **MCP**：リモートの MCP（`/mcp`）と HTTP の道具（`/api/v1/tools`）はそのまま使える。stdio の `mcp_server.py` はホストの Python で動かして、公開したポートへつなぐ。
- **パスキー**：`--public-host` で渡した公開のアドレスで開いたときだけ使える（README §17 と同じ）。

## 5. イメージの中身

| 段 | すること |
|---|---|
| `source` | ビルドの文脈から `git clone --depth 1`（アプリと `vendor/okura-gov`）。固定した版と一致するかを確かめる |
| `frontend` | AlmaLinux の Node.js 22 で `npm ci --ignore-scripts` → `npm run build` |
| `venvs` | AlmaLinux の Python 3.11 と uv で `tools/setup_env.py`（core・records・web・auth。wheel だけ）。バイトコードを先に作る |
| 最後 | `python3.11`・`git-core` と、上の成果物だけ。uv・Node.js・`node_modules` は入らない |

- `vendor/okura-gov` は、改行を Windows と同じ（`core.autocrlf=true`）にして取り出す。判定コアが読む表のデータ（`rules/kyuyo/data/*.csv`・`rules/tax/data/*.csv`）の
  SHA-256 は改行が CRLF の中身で記録してあり、Linux の既定（LF）で取り出すと照合が通らず、給与所得・源泉徴収税額表を使う計算が止まるため。
  okura-gov の中身（コミット）は変えていない。設定 → 版 でも「書き換えなし」のまま。okura-gov 側で改行を固定したあとも、この設定は害がない。
- 置き場所は `/opt/okura-web`（`okura_dev.pth` と仮想環境が絶対パスを持つので、動かさない）。
- `git` を入れているのは、設定 → 版（固定した版と実際の版の一致・書き換えの有無）が git を呼ぶため。
- uv は版とダイジェストを固定している（`Containerfile` の `UV_IMAGE`）。上げるときは安全性を確かめ直す。
- AlmaLinux は `almalinux:9` のタグ（OS の修正を取り込むため、ダイジェストでは固定していない）。固定したいときは `--build-arg ALMALINUX_IMAGE=…@sha256:…`。
- パスキーの依存（`tools/auth-requirements.txt`）は、Linux の wheel（x86_64・aarch64）のハッシュも固定してある。

## 6. 確かめる・止める

```
podman compose ps                                    # 状態（healthy）
curl -s http://127.0.0.1:8765/api/status             # okura_gov.commit と pinned_commit が同じこと
podman compose logs -f                               # ログ（方法とパスだけ）
podman compose down                                  # 止める（データのボリュームは残る）
```

テスト（ユニットテストだけ。架空の家庭）をイメージの中で動かす：

```
podman run --rm --entrypoint /opt/okura-web/.work/venvs/web/bin/python okura-web \
  -I -X utf8 -m unittest discover -s tests -t .
```

okura-gov の版を上げたとき・アプリを直したときは、コミットしてから `podman compose up -d --build`。データのボリュームはそのまま使われる。
