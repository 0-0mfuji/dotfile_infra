#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y \
  ca-certificates curl git gnupg tar unzip xz-utils polkitd \
  build-essential ethtool rsync vim

# SSH経由のセッションでは、一般ユーザーのsystemd-inhibitがpolkitの対話認証を求められて失敗する。
# sudoグループには、sleepを「ブロックする」操作だけを許可する (再起動等の権限は増やさない)。
# 長時間ジョブが自動Suspendを止めるために使う。
mkdir -p /etc/polkit-1/rules.d
cat > /etc/polkit-1/rules.d/50-dev-inhibit-sleep.rules <<'EOF2'
polkit.addRule(function(action, subject) {
  if (action.id == "org.freedesktop.login1.inhibit-block-sleep" && subject.isInGroup("sudo")) {
    return polkit.Result.YES;
  }
});
EOF2
