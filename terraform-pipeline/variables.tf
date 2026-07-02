# variables.tf
variable "do_token" {
  description = "DigitalOcean API Token"
  type        = string
  sensitive   = true
}

variable "ssh_key_fingerprints" {
  description = "Fingerprints of SSH keys authorized on all droplets"
  type        = list(string)
  default     = [
    "f5:2f:a7:15:03:72:53:9d:4b:13:a1:7d:d9:60:bf:dd",  # adarsh personal key
    "16:08:c2:3b:a4:4e:e3:4b:4b:0d:02:39:a9:a2:72:94",  # hpe-twin-deploy-key
  ]
}
