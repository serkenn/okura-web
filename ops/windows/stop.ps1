# start.ps1（監視役）を止める。停止フラグを置くと、監視役がサーバーとトンネルを止めて終わる。
param([string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path)
$stateDir = Join-Path $Root '.live'
New-Item -ItemType Directory -Force $stateDir | Out-Null
Set-Content -Path (Join-Path $stateDir 'stop') -Value (Get-Date -Format o)
$pidFile = Join-Path $stateDir 'supervisor.pid'
for ($i = 0; $i -lt 30; $i++) {
  if (-not (Test-Path $pidFile)) { Write-Host '止めました。'; exit 0 }
  Start-Sleep -Seconds 1
}
$old = Get-Content $pidFile -ErrorAction SilentlyContinue
if ($old) { Stop-Process -Id $old -Force -ErrorAction SilentlyContinue }
Remove-Item $pidFile -ErrorAction SilentlyContinue
Write-Host '監視役を強制終了しました（子プロセスが残っていればタスク マネージャーで確認）。'
