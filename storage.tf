# 物理構成のZFS mirror (2TB NVMe x2) は事前にホスト側で `zpool create` 済みとし、
# ここではその既存poolをIncusのstorage poolとして登録するだけを扱う。
resource "incus_storage_pool" "dev" {
  name   = var.storage_pool
  driver = "zfs"

  config = {
    source = var.storage_pool
  }

  # 誤って `terraform destroy` した際に開発データ・プロジェクトデータが
  # 消えることを防ぐ
  lifecycle {
    prevent_destroy = true
  }
}
