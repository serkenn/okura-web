# okura-web（サーバー）と Cloudflare トンネルを起動し、落ちたら起こし直す監視役。
# タスクスケジューラからログオン時に起動する（register-autostart.ps1）。止めるときは stop.ps1。
# 公開するホスト名（例 okura.example.com）は -PublicHost か、.work\public-host.txt（1行。git に入れない）で渡す。
param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
  [string]$Cloudflared = 'C:\Program Files (x86)\cloudflared\cloudflared.exe',
  [string]$TunnelConfig = (Join-Path $env:USERPROFILE '.cloudflared\okura.yml'),
  [string]$TunnelName = 'okura',
  [string]$PublicHost = '',
  [int]$Port = 8765,
  [int]$KeepLogDays = 14
)
$ErrorActionPreference = 'Stop'
if (-not $PublicHost) {
  $hostFile = Join-Path $Root '.work\public-host.txt'
  if (Test-Path $hostFile) { $PublicHost = (Get-Content $hostFile -TotalCount 1).Trim() }
}
if (-not $PublicHost) { throw '公開するホスト名がありません。-PublicHost で渡すか、.work\public-host.txt に書いてください。' }

$logDir = Join-Path $Root 'logs'
$stateDir = Join-Path $Root '.live'
New-Item -ItemType Directory -Force $logDir, $stateDir | Out-Null
$stopFlag = Join-Path $stateDir 'stop'
$pidFile = Join-Path $stateDir 'supervisor.pid'

if (Test-Path $pidFile) {
  $old = Get-Content $pidFile -ErrorAction SilentlyContinue
  if ($old -and (Get-Process -Id $old -ErrorAction SilentlyContinue)) {
    Write-Host "すでに起動しています (PID $old)。先に stop.ps1 を実行してください。"
    exit 1
  }
}
Remove-Item $stopFlag -ErrorAction SilentlyContinue
Set-Content -Path $pidFile -Value $PID

function Write-Log([string]$message) {
  $line = "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $message
  Add-Content -Path (Join-Path $logDir 'supervisor.log') -Value $line -Encoding UTF8
}

Get-ChildItem -Path $logDir -File -Filter '*-*.log' -ErrorAction SilentlyContinue |
  Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-$KeepLogDays) } |
  Remove-Item -Force -ErrorAction SilentlyContinue

$python = Join-Path $Root '.work\venvs\web\Scripts\python.exe'
if (-not (Test-Path $python)) { throw "$python がありません。README の「始め方」で仮想環境を作ってください。" }

function Start-Server {
  $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
  $env:OKURA_WEB_PORT = "$Port"
  Write-Log "start server"
  # アクセスのログは方法とパスだけ（家族のデータは書かない）
  return Start-Process -FilePath $python -ArgumentList @('-I', '-X', 'utf8', (Join-Path $Root 'serve.py'), '--public-host', $PublicHost) `
    -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logDir "server-$stamp.out.log") -RedirectStandardError (Join-Path $logDir "server-$stamp.log")
}

function Start-Tunnel {
  $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
  Write-Log "start tunnel $TunnelName"
  return Start-Process -FilePath $Cloudflared -ArgumentList @('tunnel', '--no-autoupdate', '--config', $TunnelConfig, 'run', $TunnelName) `
    -WorkingDirectory $Root -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $logDir "tunnel-$stamp.out.log") -RedirectStandardError (Join-Path $logDir "tunnel-$stamp.log")
}

function Test-Healthy {
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/api/status" -UseBasicParsing -TimeoutSec 3
    return $r.StatusCode -eq 200
  } catch { return $false }
}

$server = Start-Server
# サーバーが応答してからトンネルを開く
for ($i = 0; $i -lt 30 -and -not (Test-Healthy); $i++) { Start-Sleep -Seconds 1 }
$tunnel = Start-Tunnel
$failures = 0

try {
  while (-not (Test-Path $stopFlag)) {
    Start-Sleep -Seconds 5
    if ($server.HasExited) {
      Write-Log "server exited ($($server.ExitCode)); restarting"
      $server = Start-Server
    } elseif (-not (Test-Healthy)) {
      $failures++
      if ($failures -ge 6) {
        Write-Log "server not responding; restarting"
        Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
        $server = Start-Server
        $failures = 0
      }
    } else { $failures = 0 }
    if ($tunnel.HasExited) {
      Write-Log "tunnel exited ($($tunnel.ExitCode)); restarting"
      $tunnel = Start-Tunnel
    }
  }
} finally {
  Write-Log "stopping"
  foreach ($p in @($tunnel, $server)) {
    if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
  }
  Remove-Item $pidFile -ErrorAction SilentlyContinue
}
# exit 0 だと終わらないことがある（子のプロセスの出力を待つ）。タスクが「実行中」のまま残らないように強く終わる
[Environment]::Exit(0)
