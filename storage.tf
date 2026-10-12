# ZFS pool/datasetは事前にホスト側 (host/storage-init) で作成済みとし、
# ここではその既存datasetをIncusのstorage poolとして登録するだけを扱う。
resource "incus_storage_pool" "dev" {
  name   = var.storage_pool
  driver = "zfs"

  config = {
    source = var.zfs_source
  }

  # 誤って `terraform destroy` した際に開発データ・プロジェクトデータが
  # 消えることを防ぐ
  lifecycle {
    prevent_destroy = true
  }
}
