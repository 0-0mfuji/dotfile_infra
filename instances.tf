locals {
  base_packages = ["openssh-server", "git", "gh", "curl", "ca-certificates", "build-essential", "bubblewrap", "qrencode"]
}

resource "incus_instance" "dev" {
  for_each = var.dev_instances

  name  = "${each.key}-dev"
  image = each.value.image
  type  = each.value.type

  profiles = concat(
    [incus_profile.dev_base.name],
    each.value.gpu ? [incus_profile.gpu_passthrough.name] : [],
  )

  config = {
    "limits.cpu"            = tostring(each.value.cpu)
    "limits.memory"         = each.value.memory
    "security.nesting"      = tostring(each.value.nesting)
    "cloud-init.user-data"  = templatefile("${path.module}/cloud-init/dev-base.yaml.tftpl", {
      ssh_public_key = var.ssh_public_key
      packages       = concat(local.base_packages, each.value.packages)
    })
  }

  dynamic "device" {
    for_each = each.value.ip == null ? [] : [each.value.ip]
    content {
      name = "eth0"
      type = "nic"
      properties = {
        network        = incus_network.dev.name
        "ipv4.address" = device.value
      }
    }
  }

  dynamic "device" {
    for_each = (each.value.web_port == null || var.mobile_bind_ip == null) ? [] : [each.value.web_port]
    content {
      name = "web"
      type = "proxy"
      properties = {
        listen  = "tcp:${var.mobile_bind_ip}:${device.value}"
        connect = "tcp:127.0.0.1:3080"
      }
    }
  }

  # 動画制作の共有ボリューム。shift=true で、コンテナ内の dev ユーザー (uid 1000) が読み書きできるようにする
  dynamic "device" {
    for_each = each.value.media == null ? [] : [each.value.media]
    content {
      name = "media"
      type = "disk"
      properties = {
        source   = var.media_path
        path     = var.media_path
        shift    = "true"
        readonly = tostring(device.value == "ro")
      }
    }
  }

  device {
    name = "root"
    type = "disk"
    properties = {
      pool = incus_storage_pool.dev.name
      path = "/"
      size = each.value.disk_size
    }
  }
}
