#!/usr/bin/env bash
# コンテナ内で実行する (devユーザー + パスワードなしsudo)。何度流しても同じ結果になる。
#   Node.js / git / jj / Claude Code / Codex / DeepSeek Harness (ビルド・プラグイン・常駐) を整える。
# ログイン情報とAPIキーは扱わない (各コンテナ内で、利用者が初回に入力する)。
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=./versions.env
source "$DIR/versions.env"
# 任意: GIT_USER_NAME / GIT_USER_EMAIL を書くと、git と jj の既定の名前・メールにする
# shellcheck disable=SC1091
[ -f "$HOME/.config/dev/provision.env" ] && source "$HOME/.config/dev/provision.env"

log() { echo "[provision] $*"; }
sudo -n true 2>/dev/null || { echo "passwordless sudo is required" >&2; exit 1; }
[ "$(uname -m)" = x86_64 ] || { echo "only x86_64 is supported (got $(uname -m))" >&2; exit 1; }

node_ok() {
  command -v node >/dev/null 2>&1 && node -e 'const [a,b]=process.versions.node.split(".").map(Number); process.exit((a>=24||(a===22&&b>=19))?0:1)'
}

install_node() {
  if node_ok; then log "node $(node -v): ok"; return; fi
  local base="https://nodejs.org/dist/latest-v${NODE_MAJOR}.x" tmp f
  tmp="$(mktemp -d)"
  curl -fsSL "$base/SHASUMS256.txt" -o "$tmp/SHASUMS256.txt"
  f="$(grep -E "node-v[0-9.]+-linux-x64\.tar\.xz$" "$tmp/SHASUMS256.txt" | awk '{print $2}')"
  curl -fsSL "$base/$f" -o "$tmp/$f"
  (cd "$tmp" && grep " $f\$" SHASUMS256.txt | sha256sum -c -)
  sudo tar -xJf "$tmp/$f" -C /usr/local --strip-components=1 --no-same-owner
  rm -rf "$tmp"; hash -r
  log "node $(node -v): installed"
}

install_jj() {
  if command -v jj >/dev/null 2>&1 && [ "$(jj --version | awk '{print $2}' | cut -d- -f1)" = "$JJ_VERSION" ]; then
    log "jj $JJ_VERSION: ok"; return
  fi
  local f="jj-v${JJ_VERSION}-x86_64-unknown-linux-musl.tar.gz" tmp
  tmp="$(mktemp -d)"
  curl -fsSL "https://github.com/jj-vcs/jj/releases/download/v${JJ_VERSION}/$f" -o "$tmp/$f"
  echo "$JJ_SHA256  $tmp/$f" | sha256sum -c -
  tar -xzf "$tmp/$f" -C "$tmp" ./jj
  sudo install -m 755 "$tmp/jj" /usr/local/bin/jj
  rm -rf "$tmp"
  log "jj $(jj --version | awk '{print $2}'): installed"
}

configure_vcs() {
  if [ -n "${GIT_USER_NAME:-}" ] && [ -n "${GIT_USER_EMAIL:-}" ]; then
    git config --global user.name "$GIT_USER_NAME"
    git config --global user.email "$GIT_USER_EMAIL"
    jj config set --user user.name "$GIT_USER_NAME"
    jj config set --user user.email "$GIT_USER_EMAIL"
    log "git/jj identity set"
  else
    log "GIT_USER_NAME/GIT_USER_EMAIL not set (~/.config/dev/provision.env); skipping identity"
  fi
}

# Zedの拡張機能の転送 (SFTP/SCP) に必要。Debianのcloud imageのsshd_configにはSubsystemが無い
install_sftp() {
  if grep -q '^Subsystem' /etc/ssh/sshd_config; then log "sftp subsystem: ok"; return; fi
  echo 'Subsystem sftp /usr/lib/openssh/sftp-server' | sudo tee -a /etc/ssh/sshd_config >/dev/null
  sudo sshd -t && sudo systemctl reload ssh
  log "sftp subsystem: enabled"
}

# GPU: ホストのドライバと同じ版の libcuda1 / nvidia-smi を、同じDebianのAPTから入れる (カーネルモジュールは入れない)。
# CUDAツールキットは不要: PyTorch / TensorFlow / JAX のpipパッケージは、CUDAのランタイムを同梱していて、libcuda だけで動く。
install_gpu() {
  if [ ! -e /dev/nvidiactl ]; then
    log "gpu: no NVIDIA device in this container; skipping (host driver + tofu gpu device needed)"
    return
  fi
  local d822=/etc/apt/sources.list.d/debian.sources legacy=/etc/apt/sources.list
  if [ -f "$d822" ]; then
    grep -Eq '^Components:.*(^|[ :])non-free([ ]|$)' "$d822" || \
      sudo awk '/^Components:/ && !/(^|[ :])non-free([ ]|$)/ { $0 = $0 " non-free" } { print }' "$d822" | sudo tee "$d822.new" >/dev/null && sudo mv "$d822.new" "$d822"
  elif [ -f "$legacy" ]; then
    sudo awk '/^deb(-src)? / && /(deb\.debian\.org|security\.debian\.org)/ && !/ non-free( |$)/ { sub(/ main/, " main non-free") } { print }' "$legacy" | sudo tee "$legacy.new" >/dev/null && sudo mv "$legacy.new" "$legacy"
  fi
  if ! command -v nvidia-smi >/dev/null 2>&1 || ! dpkg -s libcuda1 >/dev/null 2>&1; then
    sudo apt-get update -qq >/dev/null 2>&1
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq libcuda1 nvidia-smi >/dev/null 2>&1 || { log "WARNING: could not install libcuda1/nvidia-smi"; return; }
    log "gpu: libcuda1 + nvidia-smi installed"
  fi
  # 自己点検: ホストのドライバとコンテナのライブラリの版が違うと、nvidia-smi が mismatch で失敗する
  local out; out="$(nvidia-smi -L 2>&1 || true)"
  case "$out" in
    *GPU*) log "gpu: $(printf '%s\n' "$out" | head -1 | cut -c1-80)" ;;
    *) log "WARNING: nvidia-smi failed: $(printf '%s' "$out" | head -1 | cut -c1-100) (ホストのドライバとコンテナの libcuda1 の版を揃える: provision/run)"; return ;;
  esac
  python3 - <<'PY' | sed 's/^/[provision] gpu: /'
import ctypes, sys
try:
    cuda = ctypes.CDLL("libcuda.so.1")
    r = cuda.cuInit(0)
    n = ctypes.c_int(0)
    cuda.cuDeviceGetCount(ctypes.byref(n))
    print(f"cuInit={r} devices={n.value}" + ("" if r == 0 else "  (WARNING: CUDA初期化に失敗)"))
except OSError as e:
    print(f"WARNING: libcuda を読み込めません: {e}")
PY
}

# スマホ用のQRコードを、Macに何も入れずに描画するため
install_qrencode() {
  command -v qrencode >/dev/null 2>&1 || { sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq qrencode >/dev/null 2>&1; log "qrencode: installed"; }
}

# グローバルnpmパッケージを入れる。UPDATE=1 (provision/run --update) のときは、入っていても最新にする
npm_global() {
  local pkg="$1" old new
  old="$(npm ls -g --depth=0 --json "$pkg" 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin).get("dependencies",{}).popitem()[1]["version"])' 2>/dev/null || true)"
  if [ -n "$old" ] && [ "${UPDATE:-}" != 1 ]; then log "$pkg: ok ($old)"; return; fi
  sudo npm install -g "$pkg@latest" >/dev/null 2>&1 || { log "$pkg: install FAILED"; return; }
  new="$(npm ls -g --depth=0 --json "$pkg" 2>/dev/null | python3 -c 'import sys,json; print(json.load(sys.stdin)["dependencies"].popitem()[1]["version"])' 2>/dev/null || true)"
  if [ -z "$old" ]; then log "$pkg: installed ($new)"
  elif [ "$old" = "$new" ]; then log "$pkg: up to date ($new)"
  else log "$pkg: updated $old -> $new"; fi
}

install_agent_clis() {
  npm_global @anthropic-ai/claude-code
  npm_global @openai/codex
}

# 利用者のファイルは上書きしない
# Codexのサンドボックスは bubblewrap を使う。コンテナで動くには security.nesting=true が要る (dotfile_infra の nesting)
install_sandbox() {
  command -v bwrap >/dev/null 2>&1 || { sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq bubblewrap >/dev/null 2>&1; log "bubblewrap: installed"; }
  if bwrap --ro-bind / / --dev /dev --proc /proc --unshare-user --unshare-pid --unshare-net -- true 2>/dev/null; then
    log "sandbox (bwrap): ok"
  else
    log "WARNING: bwrap sandbox cannot start; Codex delegation will fail. Set nesting = true for this instance in terraform.tfvars, apply, and restart it."
  fi
}

# Zedから使うACP: DeepSeek Harness用のラッパー(Web設定と同期)と、Claude Code / Codex のACPアダプタ
install_acp_tools() {
  # 旧版 (@zed-industries/codex-acp) は開発終了で、モデル一覧が古い。同名コマンドを持つので、先に外す
  if npm ls -g --depth=0 @zed-industries/codex-acp >/dev/null 2>&1; then
    sudo npm uninstall -g @zed-industries/codex-acp >/dev/null 2>&1; log "@zed-industries/codex-acp: removed (replaced)"
  fi
  npm_global @agentclientprotocol/claude-agent-acp
  npm_global @agentclientprotocol/codex-acp
  sudo install -m 755 "$DIR/files/dsh-acp" /usr/local/bin/dsh-acp
  log "dsh-acp: installed"
}

# DeepSeek Harness (Web UI) の既定設定 (Ollama Cloudのモデル一覧・既定モデルなど。APIキーは含まない) を、
# コンテナのWeb設定に「無い項目だけ」足す。既にある項目は上書きしない。Webプロファイルはライブで反映する。
seed_web_settings() {
  python3 "$DIR/files/seed-web-settings" "$DIR/files/web-defaults.yml" "$HOME/.dsh/profiles/web/cordis.patch.yml" \
    | sed 's/^/[provision] /'
}

# ACPプロファイルを(起動せずに)初期化しておく。dsh-acp が設定を書き込めるようにするため
init_acp_profile() {
  [ -d "$HOME/.dsh/profiles/acp" ] && return
  ( cd "$HOME/src/deepseek-harness" && pnpm -s dsh --profile acp --dump-config >/dev/null 2>&1 ) || true
  log "acp profile: initialized"
}

install_instruction_files() {
  mkdir -p "$HOME/.claude" "$HOME/.codex"
  [ -e "$HOME/.claude/CLAUDE.md" ] || { cp "$DIR/files/CLAUDE.md" "$HOME/.claude/CLAUDE.md"; log "~/.claude/CLAUDE.md created"; }
  [ -e "$HOME/.codex/AGENTS.md" ] || { cp "$DIR/files/AGENTS.md" "$HOME/.codex/AGENTS.md"; log "~/.codex/AGENTS.md created"; }
  # DeepSeek Harnessは、全セッションの最初のリクエストに ~/.dsh/AGENTS.md を読み込む
  mkdir -p "$HOME/.dsh"
  [ -e "$HOME/.dsh/AGENTS.md" ] || { cp "$DIR/files/DSH_AGENTS.md" "$HOME/.dsh/AGENTS.md"; log "~/.dsh/AGENTS.md created"; }
}

REBUILT=0
install_dsh() {
  local d="$HOME/src/deepseek-harness" stamp="$HOME/.dsh-build-stamp"
  mkdir -p "$HOME/src" "$HOME/.dsh"
  [ -d "$d/.git" ] || git clone --branch "$DSH_BRANCH" --single-branch "$DSH_REPO" "$d"
  cd "$d"
  if [ "$(git rev-parse HEAD)" != "$DSH_COMMIT" ]; then
    # フォークのブランチは履歴が書き換わることがある (固定したコミットがブランチから辿れなくなる)。まずSHAを直接取得する
    git fetch --quiet origin "$DSH_COMMIT" || git fetch --quiet origin "$DSH_BRANCH"
    git checkout --quiet "$DSH_COMMIT"
  fi
  if [ "$(cat "$stamp" 2>/dev/null || true)" != "$DSH_COMMIT" ]; then
    sudo corepack enable
    corepack prepare "$(node -p 'require("./package.json").packageManager')" --activate >/dev/null
    # ビルドは約6GiB以上のメモリを使う。足りないとOOMでKillされる (終了コード137)
    local mem_gib; mem_gib="$(awk '/^MemTotal:/ {printf "%d", $2/1048576}' /proc/meminfo)"
    if [ "$mem_gib" -lt 7 ]; then
      echo "[provision] ERROR: ${mem_gib}GiB of memory is not enough to build DeepSeek Harness (need >= 8GiB)." >&2
      echo "[provision]        Raise memory for this instance in terraform.tfvars (e.g. 8GiB), run tofu apply, then retry." >&2
      exit 1
    fi
    log "building DeepSeek Harness ${DSH_COMMIT:0:7} (several minutes)..."
    pnpm install --frozen-lockfile >/dev/null
    pnpm run build >/dev/null
    echo "$DSH_COMMIT" > "$stamp"
    REBUILT=1
  else
    log "deepseek-harness ${DSH_COMMIT:0:7}: already built"
  fi
}

# レジストリ版 (0.0.1-rc.1) は本体 (0.2.1-alpha.x) と非互換のため、同じチェックアウトのパッケージを link: で入れる
install_plugins() {
  local d="$HOME/src/deepseek-harness" pj="$HOME/.dsh/profiles/web/package.json" p
  cd "$d"
  for p in subagent-claude-code subagent-codex; do
    if [ -f "$pj" ] && grep -q "dsh-$p" "$pj"; then log "plugin $p: ok"; continue; fi
    pnpm dsh plugin --profile web add "link:$d/packages/subagent/$p" >/dev/null
    REBUILT=1
    log "plugin $p: installed"
  done
}

# 一般ユーザーのsystemd --user はSSH経由だと環境が不安定なため、systemのunitにUser=で動かす。
# URLのトークンは起動のたびに変わるので、ログを毎回作り直し (file: は起動時に切り詰める)、devコマンドが読む。
install_service() {
  local me d args unit; me="$(id -un)"; d="$HOME/src/deepseek-harness"
  args="--no-open"
  if [ -n "${MOBILE_HOST:-}" ] && [ -n "${MOBILE_PORT:-}" ]; then
    local pub="http://${MOBILE_HOST}:${MOBILE_PORT}"   # Tailnet内の通信はWireGuardで暗号化されている (HTTPS証明書は使わない)
    # authorityの表記(ホストのみ / ホスト:ポート)のどちらで照合されても通るよう、両方を許可する
    args="$args --trusted-host ${MOBILE_HOST}"
    args="$args --trusted-host ${MOBILE_HOST}:${MOBILE_PORT}"
    args="$args --public-url ${pub}/"
    echo "${pub}/" > "$HOME/.dsh/mobile-url"
  else
    rm -f "$HOME/.dsh/mobile-url"
  fi
  unit="$(mktemp)"
  cat > "$unit" <<UNIT
[Unit]
Description=DeepSeek Harness Web UI (127.0.0.1:3080)
After=network.target

[Service]
User=$me
WorkingDirectory=$d
Environment=HOME=$HOME
Environment=PATH=/usr/local/bin:/usr/bin:/bin
ExecStart=/usr/local/bin/pnpm dsh web $args
StandardOutput=file:$HOME/.dsh/web.log
StandardError=inherit
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
  # unitの内容(起動引数)が変わったときも再起動する
  if ! cmp -s "$unit" /etc/systemd/system/dsh-web.service 2>/dev/null; then REBUILT=1; fi
  sudo install -m 644 "$unit" /etc/systemd/system/dsh-web.service
  rm -f "$unit"
  sudo systemctl daemon-reload
  sudo systemctl enable dsh-web.service >/dev/null 2>&1
  if [ "$REBUILT" = 1 ] || ! systemctl is-active --quiet dsh-web.service; then
    sudo systemctl restart dsh-web.service
    log "dsh-web.service: (re)started"
  else
    log "dsh-web.service: running"
  fi
}

# lang-dev 専用: 言語処理系 (OCaml) の開発環境。opam で入れる
#   コンパイラ: OCAML_VERSION (versions.env) / dune, ocaml-lsp-server (Zed), ocamlformat, utop, alcotest, odoc, ppx_deriving
OCAML_PKGS=(dune ocaml-lsp-server ocamlformat utop alcotest odoc ppx_deriving)

install_ocaml() {
  if ! command -v opam >/dev/null 2>&1; then
    sudo apt-get update -qq >/dev/null 2>&1
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq opam build-essential m4 unzip pkg-config rsync >/dev/null 2>&1 \
      || { log "ocaml: apt install FAILED"; return; }
    log "opam + build tools: installed"
  fi
  # コンテナ自体が隔離されているので、opam自前のサンドボックス(bwrap)は使わない
  [ -d "$HOME/.opam" ] || opam init --bare --auto-setup --disable-sandboxing -y >/dev/null 2>&1 \
    || { log "opam init FAILED"; return; }
  if ! opam switch list --short 2>/dev/null | grep -qx default; then
    log "building OCaml $OCAML_VERSION (several minutes)..."
    opam switch create default "$OCAML_VERSION" -y >/dev/null 2>&1 || { log "ocaml $OCAML_VERSION: switch create FAILED"; return; }
  fi
  if [ "${UPDATE:-}" = 1 ]; then opam update -y >/dev/null 2>&1 || true; fi
  local missing=() p
  for p in "${OCAML_PKGS[@]}"; do opam list --installed --short --switch=default "$p" 2>/dev/null | grep -qx "$p" || missing+=("$p"); done
  if [ "${UPDATE:-}" = 1 ]; then
    opam upgrade -y --switch=default >/dev/null 2>&1 || log "opam upgrade FAILED"
  fi
  if [ "${#missing[@]}" -gt 0 ]; then
    log "opam install: ${missing[*]} (several minutes)..."
    opam install -y --switch=default "${missing[@]}" >/dev/null 2>&1 || { log "opam install FAILED (opam install ${missing[*]} で原因を確認)"; return; }
  fi
  # ssh経由の非対話シェル (Zed / Claude Code / Codex) でも dune などを使えるよう、PATH等を設定する。
  # ~/.bashrc は先頭が「非対話なら終了」なので、その前 (先頭) に入れる
  local marker="# >>> opam (provision) >>>" f
  for f in "$HOME/.profile" "$HOME/.bashrc"; do
    touch "$f"
    grep -qF "$marker" "$f" && continue
    { printf '%s\n[ -r "$HOME/.opam/opam-init/init.sh" ] && eval "$(opam env --switch=default --set-switch 2>/dev/null)"\n# <<< opam (provision) <<<\n' "$marker"; cat "$f"; } > "$f.new" && mv "$f.new" "$f"
  done
  log "ocaml $(opam exec --switch=default -- ocaml -vnum): ok (dune $(opam exec --switch=default -- dune --version))"
}

# lang-dev 専用: ドキュメント (言語仕様・設計メモ) 用の mdBook。公式のビルド済みバイナリをチェックサム検証して入れる
install_mdbook() {
  if command -v mdbook >/dev/null 2>&1 && [ "$(mdbook --version | awk '{print $2}')" = "v$MDBOOK_VERSION" ]; then
    log "mdbook v$MDBOOK_VERSION: ok"; return
  fi
  local f="mdbook-v${MDBOOK_VERSION}-x86_64-unknown-linux-musl.tar.gz" tmp
  tmp="$(mktemp -d)"
  curl -fsSL "https://github.com/rust-lang/mdBook/releases/download/v${MDBOOK_VERSION}/$f" -o "$tmp/$f"
  echo "$MDBOOK_SHA256  $tmp/$f" | sha256sum -c -
  tar -xzf "$tmp/$f" -C "$tmp" mdbook
  sudo install -m 755 "$tmp/mdbook" /usr/local/bin/mdbook
  rm -rf "$tmp"
  log "mdbook $(mdbook --version | awk '{print $2}'): installed"
}

# lang-dev 専用: Rust (比較・参照用に、Rustのborrow checkerの挙動を試す)。rustup-init は公式のチェックサムで検証する
#   ツールチェーン: RUST_VERSION (versions.env) / clippy, rustfmt, rust-analyzer, rust-src
install_rust() {
  export PATH="$HOME/.cargo/bin:$PATH"
  if ! command -v rustup >/dev/null 2>&1; then
    command -v cc >/dev/null 2>&1 || { sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq build-essential >/dev/null 2>&1 || { log "rust: build-essential FAILED"; return; }; }
    local base="https://static.rust-lang.org/rustup/dist/x86_64-unknown-linux-gnu" tmp
    tmp="$(mktemp -d)"
    curl -fsSL "$base/rustup-init" -o "$tmp/rustup-init"
    curl -fsSL "$base/rustup-init.sha256" -o "$tmp/rustup-init.sha256"
    (cd "$tmp" && sha256sum -c rustup-init.sha256 >/dev/null) || { log "rustup-init: checksum FAILED"; rm -rf "$tmp"; return; }
    chmod +x "$tmp/rustup-init"
    "$tmp/rustup-init" -y --no-modify-path --profile default --default-toolchain "$RUST_VERSION" -c rust-analyzer -c rust-src >/dev/null 2>&1 \
      || { log "rustup-init FAILED"; rm -rf "$tmp"; return; }
    rm -rf "$tmp"
    log "rustup: installed"
  fi
  if ! rustup toolchain list | grep -q "^${RUST_VERSION}-"; then
    rustup toolchain install "$RUST_VERSION" --profile default -c rust-analyzer -c rust-src >/dev/null 2>&1 || { log "rust $RUST_VERSION: install FAILED"; return; }
  fi
  rustup default "$RUST_VERSION" >/dev/null 2>&1
  # ssh経由の非対話シェルでも cargo などを使えるよう、~/.profile と ~/.bashrc の先頭でPATHを通す (opamと同じ理由)
  local marker="# >>> cargo (provision) >>>" f
  for f in "$HOME/.profile" "$HOME/.bashrc"; do
    touch "$f"
    grep -qF "$marker" "$f" && continue
    { printf '%s\n[ -r "$HOME/.cargo/env" ] && . "$HOME/.cargo/env"\n# <<< cargo (provision) <<<\n' "$marker"; cat "$f"; } > "$f.new" && mv "$f.new" "$f"
  done
  log "rust $(rustc --version | awk '{print $2}'): ok (cargo $(cargo --version | awk '{print $2}'))"
}

# uv: Pythonのインストーラ兼パッケージ管理。システムのPythonには pip install しない (Debian 13 はPEP 668で拒否する)。
#   Pythonの版とライブラリは、各プロジェクトの pyproject.toml / uv.lock で固定する。公式のビルド済みバイナリをチェックサム検証して入れる
install_uv() {
  if command -v uv >/dev/null 2>&1 && [ "$(uv --version | awk '{print $2}')" = "$UV_VERSION" ]; then
    log "uv $UV_VERSION: ok"; return
  fi
  local f="uv-x86_64-unknown-linux-gnu.tar.gz" tmp
  tmp="$(mktemp -d)"
  curl -fsSL "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/$f" -o "$tmp/$f"
  echo "$UV_SHA256  $tmp/$f" | sha256sum -c - || { log "uv: checksum FAILED"; rm -rf "$tmp"; return; }
  tar -xzf "$tmp/$f" -C "$tmp" --strip-components=1
  sudo install -m 755 "$tmp/uv" "$tmp/uvx" /usr/local/bin/
  rm -rf "$tmp"
  log "uv $(uv --version | awk '{print $2}'): installed"
}

# video-dev 専用: 動画制作 (Remotion + ffmpeg)。npmのライブラリはここでは入れず、プロジェクトの package.json / lockfile で固定する。
#   ffmpeg系: ffmpeg(ffprobe付き) / mediainfo / sox / imagemagick
#   Remotion(Chrome Headless Shell)の実行に要るライブラリと、日本語フォント (無いと字幕が豆腐になる)
VIDEO_PKGS=(ffmpeg mediainfo sox libsox-fmt-all imagemagick
  fonts-noto-cjk fonts-noto-color-emoji
  libnss3 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libasound2t64 libxrandr2 libxkbcommon0 libxfixes3
  libxcomposite1 libxdamage1 libpango-1.0-0 libcairo2 libcups2 libgbm1)

install_video() {
  local missing=() p
  for p in "${VIDEO_PKGS[@]}"; do dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p"); done
  if [ "${#missing[@]}" -gt 0 ]; then
    sudo apt-get update -qq >/dev/null 2>&1
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${missing[@]}" >/dev/null 2>&1 \
      || { log "video: apt install FAILED (${missing[*]})"; return; }
    log "video: installed ${missing[*]}"
  fi
  sudo corepack enable >/dev/null 2>&1 || true   # pnpm / yarn を、プロジェクトのpackageManagerの版で使えるようにする
  install_uv
  # GPUエンコード (ffmpeg の h264_nvenc): ホストのドライバと同じ版の libnvidia-encode1 を、同じDebianのAPTから入れる (libcuda1 と同じ理由)。
  #   失敗しても止めない (CPUの libx264 で書き出せる)。自己点検が失敗するときは、Incusの gpu デバイスに video capability が渡っていない可能性
  if [ -e /dev/nvidiactl ]; then
    if ! dpkg -s libnvidia-encode1 >/dev/null 2>&1; then
      sudo apt-get update -qq >/dev/null 2>&1
      sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq libnvidia-encode1 >/dev/null 2>&1 \
        || log "video: WARNING: could not install libnvidia-encode1 (non-free が有効か。ホストのドライバと同じ版が要る)"
    fi
    if ffmpeg -v error -f lavfi -i nullsrc=s=256x256:d=0.1 -c:v h264_nvenc -f null - >/dev/null 2>&1; then
      log "video: h264_nvenc: ok"
    else
      log "video: WARNING: h264_nvenc が使えない (CPUの libx264 は使える)。docs/gpu.md の「NVENC」を参照"
    fi
  fi
  # 共有ボリューム (tofu の media = "rw") があれば、受け渡し用のフォルダを作る
  [ -d /srv/media ] && [ -w /srv/media ] && mkdir -p /srv/media/audio /srv/media/renders /srv/media/out && log "video: /srv/media/{audio,renders,out}: ok"
  # voice-dev の VOICEVOX の場所。ssh経由の非対話シェル (Zed / Claude Code / Remotion) でも読めるよう、~/.profile と ~/.bashrc の先頭に入れる
  if [ -n "${VOICE_URL:-}" ]; then
    local marker="# >>> voice url (provision) >>>" f
    for f in "$HOME/.profile" "$HOME/.bashrc"; do
      touch "$f"
      grep -qF "$marker" "$f" && sed -i "/$marker/,/# <<< voice url (provision) <<</d" "$f"
      { printf '%s\nexport VOICE_URL=%q\n# <<< voice url (provision) <<<\n' "$marker" "$VOICE_URL"; cat "$f"; } > "$f.new" && mv "$f.new" "$f"
    done
    log "video: VOICE_URL=$VOICE_URL"
  fi
  log "video: ffmpeg $(ffmpeg -version | head -1 | awk '{print $3}'): ok"
}

# voice-dev 専用: VOICEVOX ENGINE (CPU版) を、systemdで常駐させる。公式の7zをチェックサム検証して /opt に展開する。
#   待ち受けは 0.0.0.0:50021 (コンテナ内)。認証が無いので、Incus proxy (web_port) でTailnetに出さない。video-dev などから、固定IPで呼ぶ。
#   ずんだもん等の音声は、キャラクターごとの利用規約 (クレジット表記など) に従うこと。
VOICEVOX_DIR=/opt/voicevox_engine

install_voicevox() {
  local ver_file="$VOICEVOX_DIR/.version"
  if [ -r "$ver_file" ] && [ "$(cat "$ver_file")" = "$VOICEVOX_VERSION" ]; then
    log "voicevox_engine $VOICEVOX_VERSION: ok"
  else
    local f="voicevox_engine-linux-cpu-x64-${VOICEVOX_VERSION}.7z.001" tmp sz
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq 7zip >/dev/null 2>&1 || { sudo apt-get update -qq >/dev/null 2>&1; sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq 7zip >/dev/null 2>&1; } \
      || { log "voicevox: 7zip install FAILED"; return; }
    sz="$(command -v 7zz || command -v 7z)" || { log "voicevox: 7z not found"; return; }
    tmp="$(mktemp -d)"
    log "downloading VOICEVOX ENGINE $VOICEVOX_VERSION (約1.8GB)..."
    curl -fsSL "https://github.com/VOICEVOX/voicevox_engine/releases/download/${VOICEVOX_VERSION}/$f" -o "$tmp/$f" \
      || { log "voicevox: download FAILED"; rm -rf "$tmp"; return; }
    echo "$VOICEVOX_SHA256  $tmp/$f" | sha256sum -c - || { log "voicevox: checksum FAILED"; rm -rf "$tmp"; return; }
    "$sz" x -y -o"$tmp/x" "$tmp/$f" >/dev/null || { log "voicevox: extract FAILED"; rm -rf "$tmp"; return; }
    sudo rm -rf "$VOICEVOX_DIR"
    sudo mkdir -p "$VOICEVOX_DIR"
    sudo mv "$tmp"/x/*/* "$VOICEVOX_DIR"/ 2>/dev/null || sudo mv "$tmp"/x/* "$VOICEVOX_DIR"/
    echo "$VOICEVOX_VERSION" | sudo tee "$ver_file" >/dev/null
    sudo chmod 755 "$VOICEVOX_DIR/run"
    rm -rf "$tmp"
    log "voicevox_engine $VOICEVOX_VERSION: installed"
  fi
  local unit; unit="$(mktemp)"
  cat > "$unit" <<UNIT
[Unit]
Description=VOICEVOX ENGINE (CPU)
After=network.target

[Service]
User=dev
ExecStart=$VOICEVOX_DIR/run --host 0.0.0.0 --port 50021
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
  sudo install -m 644 "$unit" /etc/systemd/system/voicevox-engine.service
  rm -f "$unit"
  sudo systemctl daemon-reload
  sudo systemctl enable voicevox-engine.service >/dev/null 2>&1
  sudo systemctl restart voicevox-engine.service
  local _
  for _ in $(seq 1 30); do
    curl -fsS http://127.0.0.1:50021/version >/dev/null 2>&1 && { log "voicevox: serving on :50021 (version $(curl -fsS http://127.0.0.1:50021/version))"; return; }
    sleep 2
  done
  log "voicevox: WARNING: API が応答しない (journalctl -u voicevox-engine で確認)"
}

# blender-dev 専用: Blender (ヘッドレスのレンダリング用)。公式のtarballをチェックサム検証して /opt に展開する。
#   .blend の作成やキャラの設定はGUIが要るので、手元のMacで行い、ここではレンダリング・変換だけを行う。
#   Rigify / Node Wrangler は同梱されているので、インストールではなく有効化する。VRM / MMD のアドオンは、必要になったらタグを固定して足す。
BLENDER_PKGS=(libx11-6 libxext6 libxi6 libxxf86vm1 libxfixes3 libxrender1 libxkbcommon0 libsm6 libgl1 libegl1)

install_blender() {
  local dir="/opt/blender-${BLENDER_VERSION}"
  if [ -x "$dir/blender" ]; then
    log "blender $BLENDER_VERSION: ok"
  else
    local f="blender-${BLENDER_VERSION}-linux-x64.tar.xz" series tmp
    series="${BLENDER_VERSION%.*}"
    sudo apt-get update -qq >/dev/null 2>&1
    sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "${BLENDER_PKGS[@]}" xz-utils >/dev/null 2>&1 \
      || { log "blender: apt install FAILED"; return; }
    tmp="$(mktemp -d)"
    log "downloading Blender $BLENDER_VERSION..."
    curl -fsSL "https://download.blender.org/release/Blender${series}/$f" -o "$tmp/$f" || { log "blender: download FAILED"; rm -rf "$tmp"; return; }
    echo "$BLENDER_SHA256  $tmp/$f" | sha256sum -c - || { log "blender: checksum FAILED"; rm -rf "$tmp"; return; }
    sudo mkdir -p "$dir"
    sudo tar -xJf "$tmp/$f" -C "$dir" --strip-components=1 --no-same-owner
    rm -rf "$tmp"
    log "blender $BLENDER_VERSION: installed"
  fi
  sudo ln -sfn "$dir/blender" /usr/local/bin/blender
  install_uv
  log "blender: $(blender -b --version 2>/dev/null | head -1)"
}

# インスタンス固有のツールチェーン。INSTANCE は provision/run が渡す
install_toolchains() {
  case "${INSTANCE:-}" in
    lang-dev) install_ocaml; install_rust; install_mdbook ;;
    video-dev) install_video ;;
    voice-dev) install_voicevox ;;
    blender-dev) install_blender ;;
    *) log "toolchain: none for '${INSTANCE:-?}'" ;;
  esac
}

install_sftp
install_qrencode
install_gpu
install_node
install_jj
configure_vcs
install_agent_clis
install_sandbox
install_instruction_files
install_dsh
install_plugins
seed_web_settings
init_acp_profile
install_acp_tools
install_toolchains
install_service

log "done. node=$(node -v) jj=$(jj --version | awk '{print $2}') claude=$(claude --version 2>/dev/null | head -1) codex=$(codex --version 2>/dev/null | head -1)"
