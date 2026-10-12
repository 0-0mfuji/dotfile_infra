#!/usr/bin/env bash
# SSHを公開鍵認証のみにする。鍵が未登録ならロックアウトを避けるため中断する。
set -euo pipefail

home="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
keys="$home/.ssh/authorized_keys"

if [ ! -s "$keys" ]; then
  echo "refusing: $keys is empty or missing; register a public key first (ssh-copy-id)" >&2
  exit 1
fi

cat > /etc/ssh/sshd_config.d/10-hardening.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin no
EOF

sshd -t
systemctl reload ssh
echo "sshd: password authentication disabled (keep your current session open and test a new login)"
