#!/usr/bin/env bash
# 動画制作用の共有ボリューム (ZFS dataset $POOL/media -> /srv/media) を作る。冪等。
# video / voice / blender のコンテナが、素材と成果物を受け渡す場所。Incus storage pool ($POOL/incus) の外に置くので、
# コンテナや Incus を作り直しても残る。コンテナへは tofu の dev_instances の `media` で渡す (instances.tf)。
#
# poolが無いとき (初回: storage-init の前) は何もしない。storage-init が、最後にこのstepを呼ぶ。
# 環境変数: POOL (既定 dev-tank) / MEDIA_QUOTA (作成時だけ使う。既定 500G。後からは `sudo zfs set quota=1T $POOL/media`)
set -euo pipefail

POOL="${POOL:-dev-tank}"
MEDIA_QUOTA="${MEDIA_QUOTA:-500G}"

command -v zpool >/dev/null 2>&1 || { echo "media: zfs not installed yet; run step 30 first. skipping."; exit 0; }
if ! zpool list -H -o name 2>/dev/null | grep -qx "$POOL"; then
  echo "media: pool '$POOL' does not exist yet; run storage-init, then: sudo ./setup.sh 45. skipping."
  exit 0
fi

if zfs list -H -o name "$POOL/media" >/dev/null 2>&1; then
  echo "media: $POOL/media already exists (quota=$(zfs get -H -o value quota "$POOL/media"))"
else
  # 動画は大きな連続ファイルなので recordsize=1M。圧縮は pool の既定 (zstd) のまま (圧縮済みの動画は、ZFSが自動で諦める)
  zfs create -o mountpoint=/srv/media -o recordsize=1M -o quota="$MEDIA_QUOTA" "$POOL/media"
  echo "media: created $POOL/media -> /srv/media (quota=$MEDIA_QUOTA)"
fi
