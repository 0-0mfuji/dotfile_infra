resource "incus_network" "dev" {
  name = var.dev_network
  type = "bridge"

  config = {
    "ipv4.address" = "10.10.0.1/24"
    "ipv4.nat"     = "true"
  }

  lifecycle {
    prevent_destroy = true
  }
}
