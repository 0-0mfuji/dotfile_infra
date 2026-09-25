# OpenTofuを使う想定 (HCL文法・providerスキーマはTerraform互換のため
# ブロック名は "terraform" のまま)。CLIは `tofu` を使う。
terraform {
  required_version = ">= 1.6"

  required_providers {
    incus = {
      source  = "lxc/incus"
      version = "~> 0.3"
    }
  }
}
