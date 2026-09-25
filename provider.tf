# このTerraformはDevelopment Server上で(SSHでログインして)実行する前提。
# MacBookには何もインストールしない、という dotfiles_server の設計方針に合わせるため、
# ここではリモートIncus APIへのTLS接続は行わず、ローカルのIncus daemon
# (unixソケット) へ接続するデフォルト設定のみを使う。
#
# NOTE: terraform-provider-incus (lxc/incus) の設定スキーマはバージョンにより
# 変わることがあるため、実際に使うバージョンの公式ドキュメントで確認すること。
# OpenTofu Registry: https://search.opentofu.org/provider/lxc/incus/latest
# (providerはTerraform Registry由来のものをそのまま参照できる)
provider "incus" {}
