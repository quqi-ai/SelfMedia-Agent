# 注册 Windows 定时任务：每天 07:30 执行自媒体 Agent 的采集/口播/选题阶段
# 用法（PowerShell，非管理员亦可注册当前用户任务）：
#   powershell -ExecutionPolicy Bypass -File run\install_task.ps1
# 卸载：
#   powershell -ExecutionPolicy Bypass -File run\install_task.ps1 -Uninstall

param(
    [switch]$Uninstall,
    [string]$Time = "07:30",
    [string]$TaskName = "SelfMediaAgent-DailyMorning"
)

$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path -Parent $PSScriptRoot
$Bat = Join-Path $ProjectDir "run\run_daily.bat"

if ($Uninstall) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Write-Host "已卸载定时任务：$TaskName"
    exit 0
}

if (-not (Test-Path $Bat)) { throw "找不到 $Bat" }

$Action = New-ScheduledTaskAction -Execute "cmd.exe" -Argument "/c `"$Bat`""
$Trigger = New-ScheduledTaskTrigger -Daily -At $Time
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Force | Out-Null
Write-Host "已注册定时任务：$TaskName，每天 $Time 执行"
Write-Host "项目目录：$ProjectDir"
Write-Host "如需修改时间：重新运行并指定 -Time '08:00'"
