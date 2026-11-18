# ---------------------------------------------------------------------------- URL

variable "zone" {
  description = "Cloudflare に置いているドメイン（例 example.com）"
  type        = string
}

variable "hostname" {
  description = "公開するホスト名（例 okura.example.com）。zone の中の名前"
  type        = string

  validation {
    condition     = var.hostname == lower(var.hostname) && !strcontains(var.hostname, "/")
    error_message = "ホスト名だけを小文字で書く（https:// やパスを付けない）。"
  }
}

# ---------------------------------------------------------------------------- トンネル（cloudflared）

variable "tunnel_name" {
  description = "トンネルの名前"
  type        = string
  default     = "okura"
}

variable "origin_service" {
  description = "cloudflared から見た okura-web の場所。コンテナ（compose.cloudflare.yaml）は http://okura-web:8765、同じ PC で直接動かすなら http://127.0.0.1:8765"
  type        = string
  default     = "http://okura-web:8765"
}

# ---------------------------------------------------------------------------- ログイン（Cloudflare Access + GitHub）

variable "github_client_id" {
  description = "GitHub の OAuth App の Client ID（README.md §1）"
  type        = string
}

variable "github_client_secret" {
  description = "GitHub の OAuth App の Client secret。terraform.tfvars に書かず、環境変数 TF_VAR_github_client_secret で渡す"
  type        = string
  sensitive   = true
}

variable "allowed_emails" {
  description = "開いてよい人のメールアドレス（GitHub のアカウントの主のメールアドレス）"
  type        = set(string)
  default     = []
}

variable "github_organization" {
  description = "開いてよい GitHub の Organization（任意）。allowed_emails と「どちらか」で通る"
  type        = string
  default     = ""
}

variable "github_teams" {
  description = "github_organization の中の Team に絞るとき（任意。空なら Organization の全員）"
  type        = set(string)
  default     = []
}

variable "session_duration" {
  description = "ログインし直すまでの時間"
  type        = string
  default     = "720h"
}

variable "app_name" {
  description = "Cloudflare Access のアプリの名前"
  type        = string
  default     = "okura-web"
}

variable "mcp_bypass" {
  description = "リモートの MCP（/mcp）だけ Access を通さない（アプリが okt_… のトークンで守る。okura-web の README §8）"
  type        = bool
  default     = true
}

# ---------------------------------------------------------------------------- 手元に書くファイル

variable "write_local_files" {
  description = "okura-web と cloudflared が読むファイル（cf-access.json・cloudflare.env）を work_dir に書く"
  type        = bool
  default     = true
}

variable "work_dir" {
  description = "上のファイルを書く場所。空ならリポジトリの .work/（git に入らない）"
  type        = string
  default     = ""
}
