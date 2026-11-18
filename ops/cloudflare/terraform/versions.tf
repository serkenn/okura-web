# okura-web を Cloudflare トンネルと Cloudflare Access（GitHub でログイン）で公開する設定。手順は README.md。
terraform {
  required_version = ">= 1.9"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.29"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.9"
    }
  }
}

# API トークンは環境変数 CLOUDFLARE_API_TOKEN で渡す（ファイルに書かない）。権限は README.md §2。
provider "cloudflare" {}
