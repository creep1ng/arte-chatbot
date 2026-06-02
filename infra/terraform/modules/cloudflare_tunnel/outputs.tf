output "tunnel_id" {
  description = "Cloudflare tunnel id."
  value       = cloudflare_zero_trust_tunnel_cloudflared.this.id
}

output "tunnel_name" {
  description = "Cloudflare tunnel name."
  value       = cloudflare_zero_trust_tunnel_cloudflared.this.name
}

output "hostnames" {
  description = "Hostnames routed by this tunnel."
  value       = [for route in var.public_hostnames : route.hostname]
}

output "tunnel_token" {
  description = "Sensitive cloudflared connector token for ECS sidecar secret injection."
  value       = data.cloudflare_zero_trust_tunnel_cloudflared_token.this.token
  sensitive   = true
}
