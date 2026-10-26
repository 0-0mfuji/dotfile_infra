# 名前は <target>-dev。専用resourceとprovisionで開発用ツールの導入を分離する。
variable "secretary" {
  description = "私用秘書。nullなら作成しない。IPとTailnet向け公開ポートはローカルtfvarsで指定する"
  type = object({
    ip            = string
    cpu           = optional(number, 2)
    memory        = optional(string, "4GiB")
    disk_size     = optional(string, "30GiB")
    notes_port    = optional(number)
    nanomuse_port = optional(number)
  })
  default = null
}

resource "incus_instance" "secretary" {
  for_each = var.secretary == null ? {} : { main = var.secretary }
  name     = "secretary-dev"
  image    = "images:debian/13/cloud"
  type     = "container"
  profiles = [incus_profile.dev_base.name]
  config = {
    "limits.cpu"          = tostring(each.value.cpu)
    "limits.memory"       = each.value.memory
    "security.privileged" = "false"
    "security.nesting"    = "false"
    "cloud-init.user-data" = templatefile("${path.module}/cloud-init/dev-base.yaml.tftpl", {
      ssh_public_key = var.ssh_public_key
      packages       = ["openssh-server", "ca-certificates", "curl", "git", "unzip", "python3", "python3-yaml"]
    })
  }
  device {
    name       = "root"
    type       = "disk"
    properties = { pool = incus_storage_pool.dev.name, path = "/", size = each.value.disk_size }
  }
  device {
    name       = "eth0"
    type       = "nic"
    properties = { network = incus_network.dev.name, "ipv4.address" = each.value.ip }
  }
  dynamic "device" {
    for_each = each.value.notes_port != null && var.mobile_bind_ip != null ? [each.value.notes_port] : []
    content {
      name = "notes"
      type = "proxy"
      properties = {
        listen  = "tcp:${var.mobile_bind_ip}:${device.value}"
        connect = "tcp:127.0.0.1:3000"
      }
    }
  }
  dynamic "device" {
    for_each = each.value.nanomuse_port != null && var.mobile_bind_ip != null ? [each.value.nanomuse_port] : []
    content {
      name = "nanomuse"
      type = "proxy"
      properties = {
        listen  = "tcp:${var.mobile_bind_ip}:${device.value}"
        connect = "tcp:127.0.0.1:8787"
      }
    }
  }

}
