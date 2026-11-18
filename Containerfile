# okura-web を AlmaLinux 9 のコンテナで動かす。手順は ops/container/README.md。
#
#   git submodule update --init
#   podman build -t okura-web .          # docker build -f Containerfile -t okura-web . でも同じ
#
# - イメージに入るのは **コミットした内容だけ**（ビルドの中で git clone する）。手元の data/・.work/・コミットしていない書き換えは入らない。
# - vendor/okura-gov は、固定した版（サブモジュールの記録）と同じコミットでなければビルドを止める。
#   取り出すときの改行は Windows と同じ（core.autocrlf=true）にする。判定コアが読む表のデータ（CSV）の SHA-256 は
#   改行が CRLF の中身で記録してあり、LF で取り出すと照合が通らず、給与所得の計算が止まるため（ops/container/README.md §5）。
# - 仮想環境は tools/setup_env.py をそのまま使う（wheel だけ・okura_dev.pth・パスキーは版とハッシュを固定）。
# - 画面は npm ci --ignore-scripts → npm run build（版は package-lock.json のまま）。
# - 動かすときは root でないユーザー（UID 10001）。データは /var/lib/okura-web（ボリューム）。
#
# ベースのイメージは AlmaLinux 9（Python 3.11 と Node.js 22 が AppStream にある）。
# uv は setup_env.py を動かすためだけに使い、最後のイメージには入れない（版とダイジェストを固定。2026-11-03 公開の 0.13.7）。
ARG ALMALINUX_IMAGE=docker.io/library/almalinux:9
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490

FROM ${UV_IMAGE} AS uv

# ---------------------------------------------------------------------------- コミットした内容を取り出す
FROM ${ALMALINUX_IMAGE} AS source
RUN dnf -y install git-core && dnf clean all
COPY . /context
RUN set -eu; \
    if [ ! -e /context/.git ]; then \
        echo "ビルドの文脈に .git がない。リポジトリの根で、git clone したものからビルドする" >&2; exit 1; \
    fi; \
    if [ ! -e /context/vendor/okura-gov/.git ]; then \
        echo "vendor/okura-gov がない。git submodule update --init を先に" >&2; exit 1; \
    fi; \
    git config --global --add safe.directory '*'; \
    git clone --quiet --depth 1 file:///context /opt/okura-web; \
    pinned="$(git -C /opt/okura-web ls-files --stage vendor/okura-gov | awk '{print $2}')"; \
    rm -rf /opt/okura-web/vendor/okura-gov; \
    git clone --quiet --depth 1 -c core.autocrlf=true file:///context/vendor/okura-gov /opt/okura-web/vendor/okura-gov; \
    head="$(git -C /opt/okura-web/vendor/okura-gov rev-parse HEAD)"; \
    if [ "$head" != "$pinned" ]; then \
        echo "vendor/okura-gov（$head）が固定した版（$pinned）と違う。git submodule update を先に" >&2; exit 1; \
    fi

# ---------------------------------------------------------------------------- 画面をビルドする
FROM ${ALMALINUX_IMAGE} AS frontend
RUN dnf -y module enable nodejs:22 && dnf -y install nodejs npm && dnf clean all
WORKDIR /build
COPY --from=source /opt/okura-web/package.json /opt/okura-web/package-lock.json ./
RUN npm ci --ignore-scripts
COPY --from=source /opt/okura-web/frontend ./frontend
RUN npm run build

# ---------------------------------------------------------------------------- 仮想環境を作る
FROM ${ALMALINUX_IMAGE} AS venvs
RUN dnf -y install python3.11 && dnf clean all
COPY --from=uv /uv /usr/local/bin/uv
COPY --from=source /opt/okura-web /opt/okura-web
WORKDIR /opt/okura-web
# Python は AlmaLinux の python3.11 だけを使う（uv に取りに行かせない）。
# サブプロセスは -I で起動するたびに import するので、バイトコードを先に作っておく（動かすときは書き込めない）。
ENV UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1
RUN python3.11 -I -X utf8 tools/setup_env.py \
 && .work/venvs/web/bin/python -I -X utf8 -m compileall -q --invalidation-mode unchecked-hash \
        okura_web serve.py mcp_server.py \
        vendor/okura-gov/packages/ir/src vendor/okura-gov/packages/core/src vendor/okura-gov/packages/records/src

# ---------------------------------------------------------------------------- 動かすイメージ
FROM ${ALMALINUX_IMAGE}
# git は「設定 → 版」（固定した版と実際の版の一致・書き換えの有無）のために要る。
RUN dnf -y install python3.11 git-core && dnf clean all \
 && useradd --system --uid 10001 --user-group --home-dir /var/lib/okura-web --no-create-home --shell /sbin/nologin okura \
 && install -d -o okura -g okura -m 0700 /var/lib/okura-web
COPY --from=venvs /opt/okura-web /opt/okura-web
COPY --from=frontend /build/frontend/dist /opt/okura-web/frontend/dist
# リポジトリの持ち主（root）と動かすユーザーが違うので、git に読んでよい場所として教える。
RUN git config --system --add safe.directory /opt/okura-web \
 && git config --system --add safe.directory /opt/okura-web/vendor/okura-gov

# コンテナの中では全部のアドレスで待ち受ける。外に出す範囲は、公開するポートの側（compose.yaml の 127.0.0.1:8765）で決める。
ENV OKURA_WEB_HOST=0.0.0.0 \
    OKURA_WEB_PORT=8765 \
    OKURA_WEB_DATA=/var/lib/okura-web \
    HOME=/var/lib/okura-web \
    LANG=C.UTF-8
USER 10001:10001
WORKDIR /opt/okura-web
VOLUME /var/lib/okura-web
EXPOSE 8765
# Ctrl+C と同じ止め方（serve.py が後片付けをしてから終わる）。
STOPSIGNAL SIGINT
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["/opt/okura-web/.work/venvs/web/bin/python", "-I", "-X", "utf8", "-c", "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('OKURA_WEB_PORT', '8765') + '/api/status', timeout=4).read()"]
ENTRYPOINT ["/opt/okura-web/.work/venvs/web/bin/python", "-I", "-X", "utf8", "/opt/okura-web/serve.py"]
