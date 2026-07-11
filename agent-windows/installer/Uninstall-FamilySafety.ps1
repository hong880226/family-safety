# FamilySafety uninstaller (admin required)

param(
    [string]$InstallDir = "C:\Program Files\FamilySafety"
)

$ServiceName = "FamilySafety"

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Must run as Administrator"
    exit 1
}

# 1. Stop and remove service
$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($service) {
    Stop-Service -Name $ServiceName -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
    sc.exe delete $ServiceName | Out-Null
    Write-Host "Removed service $ServiceName"
}

# 2. Kill all FamilySafety processes (FsWatchdog is merged into FsWatchdogService)
Get-Process -Name "FsAgent","FsMonitor","FsWatchdogService","FsQuiz","FsTray","FsConfigUI" -ErrorAction SilentlyContinue | Stop-Process -Force
Start-Sleep -Seconds 2

# 3. Restore NTFS ACL and remove install dir
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

# 4. Remove desktop shortcut
$shortcutPath = [Environment]::GetFolderPath("Desktop") + "\FamilySafety 家长配置.lnk"
if (Test-Path $shortcutPath) {
    Remove-Item $shortcutPath -Force
    Write-Host "Removed desktop shortcut"
}

# 5. Keep config dir for now (in case parent wants to inspect logs)
#     Note: parents.bin is NOT deleted because it is a DPAPI blob keyed to
#     this machine; it is harmless on its own and removing it would force
#     the parent to re-enter the password on the next install.
Write-Host ""
Write-Host "Uninstall complete." -ForegroundColor Green
Write-Host "Note: $configDir (config + logs + parents.bin) was preserved." -ForegroundColor Yellow
Write-Host "To wipe parent credentials, delete parents.bin from that directory."