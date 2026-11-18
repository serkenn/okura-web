locals {
  account_id  = data.cloudflare_zone.this.account.id
  zone_id     = data.cloudflare_zone.this.id
  team_domain = data.cloudflare_zero_trust_organization.this.auth_domain
  work_dir    = var.work_dir != "" ? var.work_dir : abspath("${path.module}/../../../.work")

  # GitHub の Organization：Team の指定がなければ全員、あれば Team ごと
  github_org_whole = var.github_organization != "" && length(var.github_teams) == 0 ? [var.github_organization] : []
  github_org_teams = var.github_organization != "" ? sort(var.github_teams) : []
}

data "cloudflare_zone" "this" {
  filter = {
    name = var.zone
  }
}

# Zero Trust のチーム（ダッシュボードで一度開いてチーム名を決めておく。Free プランでよい）
data "cloudflare_zero_trust_organization" "this" {
  account_id = local.account_id
}

# ---------------------------------------------------------------------------- トンネル（cloudflared との接続）

# 設定（どのホスト名をどこへ流すか）を Cloudflare 側に置くトンネル。cloudflared はトークンだけで動く。
resource "cloudflare_zero_trust_tunnel_cloudflared" "okura" {
  account_id = local.account_id
  name       = var.tunnel_name
  config_src = "cloudflare"
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "okura" {
  account_id = local.account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.okura.id

  config = {
    ingress = [
      {
        hostname = var.hostname
        service  = var.origin_service
      },
      {
        # ほかのホスト名で来たものは流さない
        service = "http_status:404"
      },
    ]
  }
}

data "cloudflare_zero_trust_tunnel_cloudflared_token" "okura" {
  account_id = local.account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.okura.id
}

# ---------------------------------------------------------------------------- URL（DNS）

resource "cloudflare_dns_record" "okura" {
  zone_id = local.zone_id
  name    = var.hostname
  type    = "CNAME"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.okura.id}.cfargotunnel.com"
  proxied = true
  ttl     = 1
  comment = "okura-web（Cloudflare トンネル）。Terraform が管理する"
}

# ---------------------------------------------------------------------------- ログイン（GitHub）

resource "cloudflare_zero_trust_access_identity_provider" "github" {
  account_id = local.account_id
  name       = "GitHub"
  type       = "github"

  config = {
    client_id     = var.github_client_id
    client_secret = var.github_client_secret
  }
}

# 開いてよい人：メールアドレスか GitHub の Organization（どちらか）。そのうえで、GitHub でログインしていること（必ず）。
resource "cloudflare_zero_trust_access_policy" "family" {
  account_id       = local.account_id
  name             = "${var.app_name} 家族"
  decision         = "allow"
  session_duration = var.session_duration

  include = concat(
    [for e in sort(var.allowed_emails) : { email = { email = e } }],
    [for o in local.github_org_whole : {
      github_organization = {
        name                 = o
        identity_provider_id = cloudflare_zero_trust_access_identity_provider.github.id
      }
    }],
    [for t in local.github_org_teams : {
      github_organization = {
        name                 = var.github_organization
        team                 = t
        identity_provider_id = cloudflare_zero_trust_access_identity_provider.github.id
      }
    }],
  )

  require = [
    {
      login_method = {
        id = cloudflare_zero_trust_access_identity_provider.github.id
      }
    },
  ]

  lifecycle {
    precondition {
      condition     = length(var.allowed_emails) > 0 || var.github_organization != ""
      error_message = "allowed_emails か github_organization のどちらかを決める（だれも開けないアプリになる）。"
    }
    precondition {
      condition     = length(var.github_teams) == 0 || var.github_organization != ""
      error_message = "github_teams を使うときは github_organization も決める。"
    }
  }
}

resource "cloudflare_zero_trust_access_application" "okura" {
  account_id       = local.account_id
  name             = var.app_name
  type             = "self_hosted"
  domain           = var.hostname
  session_duration = var.session_duration

  # ログインの方法は GitHub だけ。選ぶ画面を出さずに GitHub へ進む
  allowed_idps              = [cloudflare_zero_trust_access_identity_provider.github.id]
  auto_redirect_to_identity = true
  app_launcher_visible      = false

  policies = [
    {
      id         = cloudflare_zero_trust_access_policy.family.id
      precedence = 1
    },
  ]
}

# ---------------------------------------------------------------------------- リモートの MCP（/mcp だけ Access を通さない）

# /mcp は Access の Cookie を持てないクライアント（Claude・ChatGPT など）が使う。アプリが okt_… のトークンで守る。
resource "cloudflare_zero_trust_access_policy" "mcp_bypass" {
  count = var.mcp_bypass ? 1 : 0

  account_id = local.account_id
  name       = "${var.app_name} MCP（Access を通さない）"
  decision   = "bypass"

  include = [
    {
      everyone = {}
    },
  ]
}

resource "cloudflare_zero_trust_access_application" "mcp" {
  count = var.mcp_bypass ? 1 : 0

  account_id           = local.account_id
  name                 = "${var.app_name}-mcp"
  type                 = "self_hosted"
  domain               = "${var.hostname}/mcp"
  app_launcher_visible = false

  policies = [
    {
      id         = cloudflare_zero_trust_access_policy.mcp_bypass[0].id
      precedence = 1
    },
  ]
}

# ---------------------------------------------------------------------------- 手元に書くファイル（git に入らない .work/）

# okura-web が Access の JWT を確かめるための設定（秘密ではない：チームのドメインとアプリの AUD）。okura_web/proxyauth.py が読む
resource "local_file" "cf_access" {
  count = var.write_local_files ? 1 : 0

  filename        = "${local.work_dir}/cf-access.json"
  file_permission = "0644"
  content = jsonencode({
    team_domain = local.team_domain
    aud         = cloudflare_zero_trust_access_application.okura.aud
    app_id      = cloudflare_zero_trust_access_application.okura.id
    hostname    = var.hostname
  })
}

# compose.cloudflare.yaml が読む値。トンネルのトークンは秘密（これがあればトンネルになりすませる）
resource "local_sensitive_file" "cloudflare_env" {
  count = var.write_local_files ? 1 : 0

  filename        = "${local.work_dir}/cloudflare.env"
  file_permission = "0600"
  content         = <<-EOT
    OKURA_PUBLIC_HOST=${var.hostname}
    TUNNEL_TOKEN=${data.cloudflare_zero_trust_tunnel_cloudflared_token.okura.token}
  EOT
}
