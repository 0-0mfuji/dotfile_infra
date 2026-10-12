#!/usr/bin/env bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y \
  ca-certificates curl git gnupg tar unzip xz-utils \
  build-essential ethtool rsync vim
