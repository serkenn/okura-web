# Cloudflare Access で、公開するホスト名（例 https://okura.example.com）を保護する（許可したメールアドレスだけが開ける）。
# 何度実行してもよい。メールアドレスを足すときは -Emails に全員を並べて実行し直す。
#
#   powershell -ExecutionPolicy Bypass -File ops\cloudflare\setup-access.ps1 -Hostname okura.example.com -Zone example.com -Emails you@example.com,parent@example.com
#
# API トークン（ダッシュボード → My Profile → API Tokens → Create Custom Token）の権限：
#   Account / Access: Apps and Policies / Edit
#   Account / Access: Organizations, Identity Providers, and Groups / Read
#   Zone / Zone / Read
# トークンはプロンプトに貼る（環境変数 CF_API_TOKEN でもよい）。ファイルにもログにも残さない。
param(
  [Parameter(Mandatory = $true)][string[]]$Emails,
  [Parameter(Mandatory = $true)][string]$Hostname,
  [Parameter(Mandatory = $true)][string]$Zone,
  [string]$AppName = 'okura-web',
  [string]$SessionDuration = '720h',
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
)
$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$token = $env:CF_API_TOKEN
if (-not $token) {
  $sec = Read-Host -AsSecureString 'Cloudflare API トークン'
  $token = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
}
$headers = @{ Authorization = "Bearer $token"; 'Content-Type' = 'application/json' }
$api = 'https://api.cloudflare.com/client/v4'

function Invoke-CF([string]$Method, [string]$Path, $Body = $null) {
  $p = @{ Method = $Method; Uri = "$api$Path"; Headers = $headers }
  if ($null -ne $Body) { $p.Body = [Text.Encoding]::UTF8.GetBytes(($Body | ConvertTo-Json -Depth 10)) }
  $r = Invoke-RestMethod @p
  if (-not $r.success) { throw ($r.errors | ConvertTo-Json -Depth 5) }
  return $r.result
}

$zoneInfo = Invoke-CF GET "/zones?name=$Zone"
if (-not $zoneInfo) { throw "ゾーン $Zone が見つからない（トークンの Zone:Read の範囲を確認）" }
$account = $zoneInfo[0].account.id
Write-Host "アカウント $account"

try { $org = Invoke-CF GET "/accounts/$account/access/organizations" }
catch { throw 'Zero Trust がまだ有効になっていない。ダッシュボードの Zero Trust を一度開いてチーム名を決める（Free プラン）。' }
$team = $org.auth_domain
Write-Host "チームのドメイン $team"

$include = @($Emails | ForEach-Object { @{ email = @{ email = $_ } } })
$policyBody = @{ name = "$AppName 家族"; decision = 'allow'; include = $include; session_duration = $SessionDuration }
$policies = Invoke-CF GET "/accounts/$account/access/policies"
$policy = $policies | Where-Object { $_.name -eq $policyBody.name } | Select-Object -First 1
if ($policy) { $policy = Invoke-CF PUT "/accounts/$account/access/policies/$($policy.id)" $policyBody; Write-Host 'ポリシーを更新した' }
else { $policy = Invoke-CF POST "/accounts/$account/access/policies" $policyBody; Write-Host 'ポリシーを作った' }

$appBody = @{
  name = $AppName; domain = $Hostname; type = 'self_hosted'; session_duration = $SessionDuration
  app_launcher_visible = $false; auto_redirect_to_identity = $false
  policies = @(@{ id = $policy.id; precedence = 1 })
}
$apps = Invoke-CF GET "/accounts/$account/access/apps"
$app = $apps | Where-Object { $_.domain -eq $Hostname } | Select-Object -First 1
if ($app) { $app = Invoke-CF PUT "/accounts/$account/access/apps/$($app.id)" $appBody; Write-Host 'アプリを更新した' }
else { $app = Invoke-CF POST "/accounts/$account/access/apps" $appBody; Write-Host 'アプリを作った' }

# okura-web が JWT を確かめるための設定（秘密ではない：チームのドメインとアプリの AUD）
$cfgPath = Join-Path $Root '.work\cf-access.json'
New-Item -ItemType Directory -Force (Split-Path $cfgPath) | Out-Null
@{ team_domain = $team; aud = $app.aud; app_id = $app.id; policy_id = $policy.id; hostname = $Hostname; emails = $Emails } |
  ConvertTo-Json | Set-Content -Path $cfgPath -Encoding UTF8
Write-Host "できた。許可：$($Emails -join ', ')"
Write-Host "設定を書いた：$cfgPath（okura-web は次のリクエストから読む）"
