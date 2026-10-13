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

# スマホ用のQRコードを、Macに何も入れずに描画するため
install_qrencode() {
  command -v qrencode >/dev/null 2>&1 || { sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq qrencode >/dev/null 2>&1; log "qrencode: installed"; }
}

install_agent_clis() {
  local pkg
  for pkg in @anthropic-ai/claude-code @openai/codex; do
    if npm ls -g --depth=0 "$pkg" >/dev/null 2>&1; then log "$pkg: ok"; else
      sudo npm install -g "$pkg" >/dev/null 2>&1; log "$pkg: installed"
    fi
  done
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
  local pkg
  for pkg in @agentclientprotocol/claude-agent-acp @zed-industries/codex-acp; do
    if npm ls -g --depth=0 "$pkg" >/dev/null 2>&1; then log "$pkg: ok"; else
      sudo npm install -g "$pkg" >/dev/null 2>&1; log "$pkg: installed"
    fi
  done
  sudo install -m 755 "$DIR/files/dsh-acp" /usr/local/bin/dsh-acp
  log "dsh-acp: installed"
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
    git fetch --quiet origin "$DSH_BRANCH"
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

install_sftp
install_qrencode
install_node
install_jj
configure_vcs
install_agent_clis
install_sandbox
install_instruction_files
install_dsh
install_plugins
init_acp_profile
install_acp_tools
install_service

log "done. node=$(node -v) jj=$(jj --version | awk '{print $2}') claude=$(claude --version 2>/dev/null | head -1) codex=$(codex --version 2>/dev/null | head -1)"
