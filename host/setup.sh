#!/usr/bin/env bash
# Development Server (Debian 13) のホスト構築。一般ユーザーからsudoで実行する。
# 各stepは冪等。ディスクを消す操作は含まない (それは storage-init を使う)。
#
# Usage: sudo ./setup.sh [step-number ...]
#   sudo ./setup.sh          # 全step
#   sudo ./setup.sh 00 40    # 指定したstepだけ
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "run with sudo: sudo $0 [step ...]" >&2; exit 1; }
export TARGET_USER="${SUDO_USER:?run via sudo from a normal user, not as root directly}"
[ "$TARGET_USER" != root ] || { echo "run 'sudo ./setup.sh' from your normal user (mfujimak), not from a root shell" >&2; exit 1; }

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

steps=()
if [ "$#" -eq 0 ]; then
  steps=("$DIR"/steps/*.sh)
else
  for n in "$@"; do steps+=("$DIR"/steps/"$n"-*.sh); done
fi

for s in "${steps[@]}"; do
  [ -f "$s" ] || { echo "no such step: $s" >&2; exit 1; }
  echo "==> $(basename "$s")"
  bash "$s"
done

echo "done."
