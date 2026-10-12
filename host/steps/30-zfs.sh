#!/usr/bin/env bash
# ZFSのパッケージ導入のみ。poolの作成(ディスク初期化)は storage-init で行う。
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# deb822形式 (debian.sources) と従来形式 (sources.list) の両方に対応する
deb822=/etc/apt/sources.list.d/debian.sources
legacy=/etc/apt/sources.list
if [ -f "$deb822" ]; then
  grep -Eq '^Components:.*\bcontrib\b' "$deb822" || sed -i -E '/^Components:/ s/$/ contrib/' "$deb822"
elif [ -f "$legacy" ]; then
  tmp="$(mktemp)"
  awk '/^deb(-src)? / && /(deb\.debian\.org|security\.debian\.org)/ && !/contrib/ { sub(/ main/, " main contrib") } { print }' "$legacy" > "$tmp"
  cat "$tmp" > "$legacy"
  rm -f "$tmp"
else
  echo "error: no Debian APT sources found" >&2; exit 1
fi

apt-get update
apt-get install -y linux-headers-amd64 zfs-dkms zfsutils-linux

if command -v mokutil >/dev/null 2>&1 && mokutil --sb-state 2>/dev/null | grep -qi enabled; then
  echo "warning: Secure Boot is enabled; the unsigned ZFS module may fail to load. Disable it or enroll a MOK." >&2
fi

modprobe zfs && echo "zfs module loaded: $(cat /sys/module/zfs/version)"
