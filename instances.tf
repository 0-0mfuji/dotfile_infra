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
    })
  }

  device {
    name = "root"
    type = "disk"
    properties = {
      pool = var.storage_pool
      path = "/"
      size = each.value.disk_size
    }
  }
}
