#!/usr/bin/env bash
# Development Server (Debian) に OpenTofu CLI をインストールする。
# Incus自体のインストール・構築はこのリポジトリの責務外 (既に導入済みの前提)。
set -euo pipefail

if command -v tofu >/dev/null 2>&1; then
  echo "tofu is already installed: $(tofu version | head -n1)"
  exit 0
fi

# NOTE: 公式インストール手順・スクリプトのURLはバージョンにより変わることが
# あるため、実行前に https://opentofu.org/docs/intro/install/ を確認すること。
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

curl --proto '=https' --tlsv1.2 -fsSL \
  https://get.opentofu.org/install-opentofu.sh -o "$TMP/install-opentofu.sh"
chmod +x "$TMP/install-opentofu.sh"

# Debian/UbuntuなのでAPT経由でインストールし、以後は `apt upgrade` で更新できるようにする
sudo "$TMP/install-opentofu.sh" --install-method deb

echo "installed: $(tofu version | head -n1)"
