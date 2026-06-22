variable "account_id" {
  description = "Cloudflare account identifier."
  type        = string
}

variable "zone_id" {
  description = "Cloudflare zone identifier for public DNS records."
  type        = string
}

variable "tunnel_name" {
  description = "Cloudflare tunnel name."
  type        = string
}

variable "tunnel_secret" {
  description = "Base64-encoded cloudflared tunnel secret. Must be provided from a secure source."
  type        = string
  sensitive   = true

  validation {
    condition     = length(trimspace(var.tunnel_secret)) > 0
    error_message = "tunnel_secret is required and must come from a secure source."
  }
}

variable "public_hostnames" {
  description = "Public hostnames routed by this scoped tunnel."
  type = list(object({
    hostname         = string
    local_origin_url = string
  }))

  validation {
    condition     = length(var.public_hostnames) > 0
    error_message = "At least one public hostname is required."
  }

  validation {
    condition = var.central_connector_mode || length(distinct([
      for route in var.public_hostnames : route.local_origin_url
    ])) == 1
    error_message = "A same-task localhost tunnel cannot mix unreachable local origins unless central_connector_mode is explicitly enabled."
  }
}

variable "central_connector_mode" {
  description = "Allow mixed origins only when all connectors can reach every configured origin."
  type        = bool
  default     = false
}

variable "tags" {
  description = "Reserved for future Cloudflare metadata. DNS record tags are intentionally not applied because some zones have a tag quota of zero."
  type        = list(string)
  default     = []
}
