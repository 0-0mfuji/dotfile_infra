#!/usr/bin/env bash
# Incus本体の導入のみ。storage pool / network / profile / instance はOpenTofu(リポジトリ直下)が管理する。
# そのため `incus admin init` は実行しない。
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get install -y incus
adduser "$TARGET_USER" incus-admin

echo "incus: $(incus --version)"
echo "note: '$TARGET_USER' was added to incus-admin; log out and in again for it to take effect."
