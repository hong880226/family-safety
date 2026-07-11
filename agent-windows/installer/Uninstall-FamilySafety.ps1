# FamilySafety uninstaller (admin required)

param(
    [string]$InstallDir = "C:\Program Files\FamilySafety"
)

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Must run as Administrator"
    exit 1
}

# 1. Stop and remove service
$service = Get-Service -Name "FamilySafetyWatchdog" -ErrorAction SilentlyContinue
if ($service) {
    Stop-Service -Name "FamilySafetyWatchdog" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
    sc.exe delete FamilySafetyWatchdog | Out-Null
    Write-Host "Removed service FamilySafetyWatchdog"
}

# 2. Kill all FamilySafety processes
Get-Process -Name "FsAgent","FsMonitor","FsWatchdog","FsWatchdogService","FsQuiz","FsTray" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

# 3. Remove scheduled task
Unregister-ScheduledTask -TaskName "FamilySafety Watchdog (Scheduled)" -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Removed scheduled task"

# 4. Restore NTFS ACL and remove install dir
$configDir = Join-Path $env:ProgramData "FamilySafety"
if (Test-Path $InstallDir) {
    $acl = Get-Acl $InstallDir
    $denyRule = $acl.Access | Where-Object { $_.IdentityReference -eq "Users" -and $_.AccessControlType -eq "Deny" }
    if ($denyRule) {
        $acl.RemoveAccessRule($denyRule) | Out-Null
        Set-Acl $InstallDir $acl
    }
    Remove-Item -Recurse -Force $InstallDir
    Write-Host "Removed $InstallDir"
}

# 5. Keep config dir for now (in case parent wants to inspect logs)
Write-Host ""
Write-Host "Uninstall complete." -ForegroundColor Green
Write-Host "Note: $configDir (config + logs) was preserved." -ForegroundColor Yellow
