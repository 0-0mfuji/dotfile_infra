# 全開発用Instance共通のベース設定。
# root disk / nic はここでデフォルトを与え、Instance側で必要な部分だけ上書きする。
resource "incus_profile" "dev_base" {
  name = "dev-base"

  device {
    name = "root"
    type = "disk"
    properties = {
      pool = incus_storage_pool.dev.name
      path = "/"
      size = "50GiB"
    }
  }

  device {
    name = "eth0"
    type = "nic"
    properties = {
      network = incus_network.dev.name
    }
  }
}

# GPUを使うコンテナに付与するprofile (既定は全コンテナ。dev_instances の gpu = false で外せる)。
# GPUは、PCIの番地ではなくベンダーIDで指定する。NVIDIAのGPUを増設すると、コンテナを再起動するだけで見える。
# 複数のコンテナが、同じGPUを同時に使える (VRAMの隔離は無い)。
resource "incus_profile" "gpu_passthrough" {
  name = "gpu-passthrough"

  dynamic "device" {
    for_each = toset(var.gpu_vendor_ids)
    content {
      name = "gpu-${device.value}"
      type = "gpu"
      properties = {
        gputype  = "physical"
        vendorid = device.value
      }
    }
  }
}
