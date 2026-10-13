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

install_agent_clis() {
  local pkg
  for pkg in @anthropic-ai/claude-code @openai/codex; do
    if npm ls -g --depth=0 "$pkg" >/dev/null 2>&1; then log "$pkg: ok"; else
      sudo npm install -g "$pkg" >/dev/null 2>&1; log "$pkg: installed"
    fi
  done
}

# 利用者のファイルは上書きしない
install_instruction_files() {
  mkdir -p "$HOME/.claude" "$HOME/.codex"
  [ -e "$HOME/.claude/CLAUDE.md" ] || { cp "$DIR/files/CLAUDE.md" "$HOME/.claude/CLAUDE.md"; log "~/.claude/CLAUDE.md created"; }
  [ -e "$HOME/.codex/AGENTS.md" ] || { cp "$DIR/files/AGENTS.md" "$HOME/.codex/AGENTS.md"; log "~/.codex/AGENTS.md created"; }
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
  local me d; me="$(id -un)"; d="$HOME/src/deepseek-harness"
  sudo tee /etc/systemd/system/dsh-web.service >/dev/null <<UNIT
[Unit]
Description=DeepSeek Harness Web UI (127.0.0.1:3080)
After=network.target

[Service]
User=$me
WorkingDirectory=$d
Environment=HOME=$HOME
Environment=PATH=/usr/local/bin:/usr/bin:/bin
ExecStart=/usr/local/bin/pnpm dsh web --no-open
StandardOutput=file:$HOME/.dsh/web.log
StandardError=inherit
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
  sudo systemctl daemon-reload
  sudo systemctl enable dsh-web.service >/dev/null 2>&1
  if [ "$REBUILT" = 1 ] || ! systemctl is-active --quiet dsh-web.service; then
    sudo systemctl restart dsh-web.service
    log "dsh-web.service: (re)started"
  else
    log "dsh-web.service: running"
  fi
}

install_node
install_jj
configure_vcs
install_agent_clis
install_instruction_files
install_dsh
install_plugins
install_service

log "done. node=$(node -v) jj=$(jj --version | awk '{print $2}') claude=$(claude --version 2>/dev/null | head -1) codex=$(codex --version 2>/dev/null | head -1)"
