# ============================================================
# main.tf — HPE Digital Twin
# Reads infrastructure.yaml and creates DigitalOcean resources
# ============================================================

terraform {
  required_providers {
    digitalocean = {
      source  = "digitalocean/digitalocean"
      version = "~> 2.0"
    }
  }
}

provider "digitalocean" {
  token = var.do_token
}

# Read source of truth YAML
locals {
  infra = yamldecode(file("infrastructure.yaml"))

  # Build a flat map of subnet name → cidr for easy lookup
  subnet_map = {
    for subnet in local.infra.network.subnets :
    subnet.name => subnet
  }

  # Build a flat map of droplet name → subnet cidr
  droplet_subnet_map = {
    for droplet in local.infra.droplets :
    droplet.name => droplet.subnet
  }

  # Map each droplet name to its cloud-init file
  cloud_init_map = {
    "droplet-1-tor1" = file("${path.module}/cloud-init/cloud-init-tor1.yaml")
    "droplet-2-tor2" = file("${path.module}/cloud-init/cloud-init-tor2.yaml")
    "droplet-3-mgmt" = file("${path.module}/cloud-init/cloud-init-mgmt.yaml")
  }
}

# ── Create ONE VPC for entire infrastructure
resource "digitalocean_vpc" "main" {
  name     = local.infra.network.vpc.name
  region   = local.infra.network.vpc.region
  ip_range = "10.10.0.0/16"
}

# ── Create Droplets from YAML
resource "digitalocean_droplet" "droplets" {
  for_each = {
    for droplet in local.infra.droplets :
    droplet.name => droplet
  }

  name     = each.value.name
  size     = each.value.size
  image    = each.value.image
  region   = each.value.region
  vpc_uuid = digitalocean_vpc.main.id
  tags     = each.value.tags

  user_data = local.cloud_init_map[each.value.name]
}

# ── Firewall for Compute Droplets (subnet-1 and subnet-2)
resource "digitalocean_firewall" "compute_firewall" {
  name = "hpe-twin-compute-firewall"
  tags = ["compute"]

  # SSH
  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = ["0.0.0.0/0"]
  }

  # Internal VPC traffic
  inbound_rule {
    protocol         = "tcp"
    port_range       = "1-65535"
    source_addresses = ["10.10.0.0/16"]
  }

  inbound_rule {
    protocol         = "icmp"
    source_addresses = ["10.10.0.0/16"]
  }

  # All outbound
  outbound_rule {
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0"]
  }

  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0"]
  }

  outbound_rule {
    protocol              = "udp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0"]
  }
}

# ── Firewall for Management Droplet (subnet-3)
resource "digitalocean_firewall" "mgmt_firewall" {
  name = "hpe-twin-mgmt-firewall"
  tags = ["management"]

  # SSH
  inbound_rule {
    protocol         = "tcp"
    port_range       = "22"
    source_addresses = ["0.0.0.0/0"]
  }

  # NetBox UI
  inbound_rule {
    protocol         = "tcp"
    port_range       = "8080"
    source_addresses = ["0.0.0.0/0"]
  }

  # Neo4j UI
  inbound_rule {
    protocol         = "tcp"
    port_range       = "7474"
    source_addresses = ["0.0.0.0/0"]
  }

  # Python middleware
  inbound_rule {
    protocol         = "tcp"
    port_range       = "5000"
    source_addresses = ["0.0.0.0/0"]
  }

  # Prometheus UI
  inbound_rule {
    protocol         = "tcp"
    port_range       = "9090"
    source_addresses = ["0.0.0.0/0"]
  }

  # Grafana UI
  inbound_rule {
    protocol         = "tcp"
    port_range       = "3000"
    source_addresses = ["0.0.0.0/0"]
  }

  # node-exporter — VPC only
  inbound_rule {
    protocol         = "tcp"
    port_range       = "9100"
    source_addresses = ["10.10.0.0/16"]
  }

  # cadvisor — VPC only
  inbound_rule {
    protocol         = "tcp"
    port_range       = "8080"
    source_addresses = ["10.10.0.0/16"]
  }

  # Internal VPC traffic
  inbound_rule {
    protocol         = "tcp"
    port_range       = "1-65535"
    source_addresses = ["10.10.0.0/16"]
  }

  inbound_rule {
    protocol         = "icmp"
    source_addresses = ["10.10.0.0/16"]
  }

  # All outbound
  outbound_rule {
    protocol              = "tcp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0"]
  }

  outbound_rule {
    protocol              = "icmp"
    destination_addresses = ["0.0.0.0/0"]
  }

  outbound_rule {
    protocol              = "udp"
    port_range            = "1-65535"
    destination_addresses = ["0.0.0.0/0"]
  }
}

# ── Outputs
output "droplet_ips" {
  description = "Public IPs of all Droplets"
  value = {
    for name, droplet in digitalocean_droplet.droplets :
    name => {
      public_ip   = droplet.ipv4_address
      private_ip  = droplet.ipv4_address_private
      tags        = droplet.tags
    }
  }
}

output "vpc_id" {
  description = "VPC ID"
  value       = digitalocean_vpc.main.id
}
