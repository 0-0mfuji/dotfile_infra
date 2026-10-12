#!/usr/bin/env bash
# ZFSのパッケージ導入のみ。poolの作成(ディスク初期化)は storage-init で行う。
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

src=/etc/apt/sources.list.d/debian.sources
if [ -f "$src" ]; then
  if ! grep -Eq '^Components:.*\bcontrib\b' "$src"; then
    sed -i -E '/^Components:/ s/$/ contrib/' "$src"
  fi
else
  echo "warning: $src not found; make sure the 'contrib' component is enabled in your APT sources" >&2
fi

apt-get update
apt-get install -y linux-headers-amd64 zfs-dkms zfsutils-linux

if command -v mokutil >/dev/null 2>&1 && mokutil --sb-state 2>/dev/null | grep -qi enabled; then
  echo "warning: Secure Boot is enabled; the unsigned ZFS module may fail to load. Disable it or enroll a MOK." >&2
fi

modprobe zfs && echo "zfs module loaded: $(cat /sys/module/zfs/version)"
