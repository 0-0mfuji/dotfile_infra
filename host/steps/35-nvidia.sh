#!/usr/bin/env bash
# NVIDIA公式ドライバ (Debian 13のnon-free、カーネルモジュールはDKMS) を導入する。
# nouveauは、nvidia-kernel-dkms が自動で無効化する。ドライバを有効にするには、再起動が要る。
# コンテナ側は、同じAPTの libcuda1 / nvidia-smi を使う (provision/agents.sh)。版が必ず揃う。
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

# non-free を有効化 (nvidia-kernel-dkms / nvidia-smi / libcuda1)。non-free-firmware とは別のcomponent
deb822=/etc/apt/sources.list.d/debian.sources
legacy=/etc/apt/sources.list
if [ -f "$deb822" ]; then
  awk '/^Components:/ && !/(^|[ :])non-free([ ]|$)/ { $0 = $0 " non-free" } { print }' "$deb822" > "$deb822.new" && cat "$deb822.new" > "$deb822" && rm -f "$deb822.new"
elif [ -f "$legacy" ]; then
  awk '/^deb(-src)? / && /(deb\.debian\.org|security\.debian\.org)/ && !/ non-free( |$)/ { sub(/ main/, " main non-free") } { print }' "$legacy" > "$legacy.new" && cat "$legacy.new" > "$legacy" && rm -f "$legacy.new"
else
  echo "error: no Debian APT sources found" >&2; exit 1
fi

apt-get update
apt-get install -y linux-headers-amd64 nvidia-kernel-dkms nvidia-smi libcuda1 nvidia-persistenced nvidia-suspend-common

# nouveauが残っているとnvidiaモジュールが読めない。念のため明示的にも無効化する
cat > /etc/modprobe.d/blacklist-nouveau-dev.conf <<'EOF2'
blacklist nouveau
options nouveau modeset=0
EOF2

# S3 Suspend/Resume: GPUのメモリ(VRAM)の内容を保存・復元する。これが無いと、復帰後にCUDAが壊れることがある
cat > /etc/modprobe.d/nvidia-power-dev.conf <<'EOF2'
options nvidia NVreg_PreserveVideoMemoryAllocations=1 NVreg_TemporaryFilePath=/var/tmp
EOF2
for u in nvidia-suspend.service nvidia-resume.service nvidia-hibernate.service; do
  systemctl list-unit-files "$u" >/dev/null 2>&1 && systemctl enable "$u" >/dev/null 2>&1 || true
done
# CUDAに要る /dev/nvidia-uvm は、nvidia_uvm モジュールが読まれて初めて作られる。再起動後に誰もCUDAを使っていないと無く、
# その状態で起動したコンテナにはGPUのデバイスが半端にしか渡らない (cuInit=999)。起動時に必ず読み込んでおく
echo nvidia-uvm > /etc/modules-load.d/nvidia-uvm-dev.conf
# モジュールを読むだけではデバイスファイルは作られない。nvidia-modprobe で作る。コンテナ (incus) より先に済ませる
cat > /etc/systemd/system/nvidia-uvm-dev.service <<'EOF2'
[Unit]
Description=Create /dev/nvidia-uvm for CUDA before containers start
After=systemd-modules-load.service nvidia-persistenced.service
Before=incus.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/bin/nvidia-modprobe -u -c=0

[Install]
WantedBy=multi-user.target
EOF2
systemctl daemon-reload
systemctl enable --now nvidia-uvm-dev.service
# /dev/nvidia* を起動時に用意し、コンテナへ渡せるようにする
systemctl enable nvidia-persistenced.service >/dev/null 2>&1 || true

update-initramfs -u

echo
echo "driver: $(dpkg-query -W -f='${Version}' nvidia-kernel-dkms 2>/dev/null)"
echo "再起動してください。再起動後に確認: nvidia-smi  (GPU名とドライバの版が出ればOK)"
