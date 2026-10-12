locals {
  base_packages = ["openssh-server", "git", "curl", "ca-certificates", "build-essential"]
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
