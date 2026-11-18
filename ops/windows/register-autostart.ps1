# ログオン時に okura-web（start.ps1）を自動で起動するよう、タスクスケジューラに登録する（管理者権限は要らない）。
# 解除: Unregister-ScheduledTask -TaskName okura-web -Confirm:$false
param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path,
  [string]$TaskName = 'okura-web'
)
$ErrorActionPreference = 'Stop'
$launcher = Join-Path $Root 'ops\windows\launch-hidden.vbs'
$action = New-ScheduledTaskAction -Execute 'wscript.exe' -Argument "`"$launcher`"" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) `
  -MultipleInstances IgnoreNew -StartWhenAvailable -Priority 5
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings `
  -Principal $principal -Description 'okura-web（サーバーと Cloudflare トンネル）をログオン時に起動する' -Force | Out-Null
Write-Host "タスク $TaskName を登録しました。今すぐ起動するなら: Start-ScheduledTask -TaskName $TaskName"
