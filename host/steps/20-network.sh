#!/usr/bin/env bash
# Wake-on-LANの永続化とTailscaleの導入。
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

iface="${WOL_IFACE:-$(ip -o route get 1.1.1.1 | awk '{for(i=1;i<=NF;i++) if($i=="dev") print $(i+1)}')}"
[ -n "$iface" ] || { echo "cannot detect network interface; set WOL_IFACE" >&2; exit 1; }

cat > /etc/systemd/system/wol@.service <<'EOF'
[Unit]
Description=Enable Wake-on-LAN on %i
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/sbin/ethtool -s %i wol g

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now "wol@${iface}.service"

# USBコントローラ(PCIクラス0x0c03)のウェイクアップを無効にする。
# キーボード/マウス/USBカードのPMEで、Suspend直後に復帰してしまうのを防ぐ。
# WoLに使う有線NICは対象外 (PCIクラスが違う)。
cat > /usr/local/sbin/usb-wake-off <<'EOF2'
#!/bin/sh
for d in /sys/bus/pci/devices/*; do
  case "$(cat "$d/class" 2>/dev/null)" in
    0x0c03*) echo disabled > "$d/power/wakeup" 2>/dev/null || true ;;
  esac
done
EOF2
chmod 755 /usr/local/sbin/usb-wake-off

cat > /etc/systemd/system/usb-wake-off.service <<'EOF2'
[Unit]
Description=Disable wakeup from USB controllers (prevent instant resume after suspend)

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/usb-wake-off

[Install]
WantedBy=multi-user.target
EOF2
systemctl daemon-reload
systemctl enable --now usb-wake-off.service

# NOTE: 公式手順は変わりうるので https://tailscale.com/kb/1038/install-debian を確認すること
if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://pkgs.tailscale.com/stable/debian/trixie.noarmor.gpg \
    -o /usr/share/keyrings/tailscale-archive-keyring.gpg
  curl -fsSL https://pkgs.tailscale.com/stable/debian/trixie.tailscale-keyring.list \
    -o /etc/apt/sources.list.d/tailscale.list
  apt-get update
  apt-get install -y tailscale
fi

echo
echo "WoL interface : $iface"
echo "MAC address   : $(cat "/sys/class/net/$iface/address")  (-> DEV_SERVER_MAC in ~/.config/dev/local.env on the Mac)"
echo "WoL setting   : $(ethtool "$iface" 2>/dev/null | awk '/Wake-on:/ {print $2}')"
echo "Next          : run 'sudo tailscale up' to log in (interactive)."
echo "Note          : Suspend(S3)からのWoLにはBIOSのPCIE/LAN Wake設定も必要。"
