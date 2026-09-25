variable "storage_pool" {
  description = "開発/プロジェクトデータ用ZFS storage pool名 (Incusへ登録済みの既存pool)"
  type        = string
}

variable "dev_network" {
  description = "Development Network用のIncus network (bridge) 名"
  type        = string
}

variable "ssh_public_key" {
  description = "MacBookからSSH接続するための公開鍵 (dotfiles_server側のSSH configのHostに対応させる)"
  type        = string
}

variable "dev_instances" {
  description = <<-EOT
    作成する開発用Instanceの定義。keyがそのままInstance名の接頭辞になり、
    dotfiles_server の config/projects.conf の instance列 ("<key>-dev") と対応させる。
  EOT
  type = map(object({
    image     = optional(string, "images:debian/13")
    type      = optional(string, "container") # "container" | "virtual-machine"
    cpu       = optional(number, 4)
    memory    = optional(string, "4GiB")
    disk_size = optional(string, "50GiB")
    gpu       = optional(bool, false)
  }))
}
