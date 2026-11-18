output "url" {
  description = "公開の URL"
  value       = "https://${var.hostname}/"
}

output "github_oauth_callback_url" {
  description = "GitHub の OAuth App の Authorization callback URL に入れる値"
  value       = "https://${local.team_domain}/cdn-cgi/access/callback"
}

output "team_domain" {
  description = "Zero Trust のチームのドメイン"
  value       = local.team_domain
}

output "access_aud" {
  description = "Access のアプリの AUD（okura-web が JWT の宛先として確かめる）"
  value       = cloudflare_zero_trust_access_application.okura.aud
}

output "tunnel_id" {
  description = "トンネルの ID"
  value       = cloudflare_zero_trust_tunnel_cloudflared.okura.id
}

output "tunnel_token" {
  description = "cloudflared に渡すトークン（秘密）。terraform output -raw tunnel_token"
  value       = data.cloudflare_zero_trust_tunnel_cloudflared_token.okura.token
  sensitive   = true
}
