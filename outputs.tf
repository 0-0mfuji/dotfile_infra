output "instance_names" {
  description = "作成されたInstance名の一覧 (dotfiles_server の config/projects.conf の instance列と対応)"
  value       = [for k, v in incus_instance.dev : v.name]
}
