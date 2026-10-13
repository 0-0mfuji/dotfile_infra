variable "storage_pool" {
  description = "Incus上のstorage pool名 (任意)"
  type        = string
  default     = "dev"
}

variable "zfs_source" {
  description = "storage poolの実体となる既存ZFS dataset (host/storage-init が作る <pool>/incus)"
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

variable "mobile_bind_ip" {
  description = "スマホ用: サーバーのTailscale IP (tailscale ip -4)。web_port を設定したコンテナが、このIPだけで待ち受ける (LANには出ない)"
  type        = string
  default     = null
}

variable "gpu_vendor_ids" {
  description = "コンテナへ渡すGPUのPCIベンダーID。1枚に固定せず、このベンダーのGPUを全て渡す (NVIDIA=10de, AMD=1002, Intel=8086)。ASPEED(1a03)のBMC用VGAは含めない"
  type        = list(string)
  default     = ["10de"]
}

variable "dev_instances" {
  description = <<-EOT
    作成する開発用Instanceの定義。keyがそのままInstance名の接頭辞になり、
    dotfiles_server の config/projects.conf の instance列 ("<key>-dev") と対応させる。
  EOT
  type = map(object({
    image     = optional(string, "images:debian/13/cloud")
    type      = optional(string, "container") # "container" | "virtual-machine"
    cpu       = optional(number, 4)
    memory    = optional(string, "4GiB")
    disk_size = optional(string, "50GiB")
    gpu       = optional(bool, true) # false にすると、このコンテナにはGPUを渡さない
    nesting   = optional(bool, true) # Codexのサンドボックス(bubblewrap)に必要。コンテナ内でprocを再マウントできるようにする
    packages  = optional(list(string), []) # 基本パッケージに加えてこのInstanceに入れるaptパッケージ
    web_port  = optional(number) # サーバーのTailscale IPで待ち受ける、Web UI(コンテナの3080)への転送ポート。スマホ用
    ip        = optional(string) # Development Network内の固定IPv4 (例: "10.10.0.11")
  }))
}
