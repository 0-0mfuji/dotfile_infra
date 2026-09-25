# 全開発用Instance共通のベース設定。
# root disk / nic はここでデフォルトを与え、Instance側で必要な部分だけ上書きする。
resource "incus_profile" "dev_base" {
  name = "dev-base"

  device {
    name = "root"
    type = "disk"
    properties = {
      pool = var.storage_pool
      path = "/"
      size = "50GiB"
    }
  }

  device {
    name = "eth0"
    type = "nic"
    properties = {
      network = var.dev_network
    }
  }
}

# CUDA/AI/Blender/FFmpeg等でGPUが必要なInstanceにのみ付与するprofile。
resource "incus_profile" "gpu_passthrough" {
  name = "gpu-passthrough"

  device {
    name = "gpu0"
    type = "gpu"
    properties = {
      gputype = "physical"
    }
  }
}
