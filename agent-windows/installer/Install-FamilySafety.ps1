# FamilySafety Windows Agent installer
# Run as Administrator.
# Usage:
#   PS> .\installer\Install-FamilySafety.ps1 -BackendUrl "http://192.168.1.10:8000" -InstallDir "C:\Program Files\FamilySafety"

param(
    [Parameter(Mandatory=$true)] [string]$BackendUrl,
    [string]$InstallDir = "C:\Program Files\FamilySafety",
    [string]$SourceDir = (Split-Path -Parent $PSScriptRoot)
)

# 1. Verify admin
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Must run as Administrator"
    exit 1
}

# 2. Verify .NET 8 SDK installed (warn only; needed for first build, not runtime)
# The binary release does NOT need SDK.

# 3. Create install dir
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

# 4. Copy binaries
$binRoot = Join-Path $SourceDir "src"
$projects = @("FsWatchdog", "FsWatchdogService", "FsAgent", "FsMonitor", "FsQuiz", "FsTray", "FsCommon")
foreach ($p in $projects) {
    $release = Join-Path $binRoot "$p\bin\Release\net8.0-windows"
    if (-not (Test-Path $release)) {
        Write-Warning "$p not built yet. Run: dotnet build $SourceDir\FamilySafety.sln -c Release"
        continue
    }
    Copy-Item -Path "$release\*" -Destination $InstallDir -Recurse -Force
}

# 5. Copy FsHook.dll
# FsHook is a managed C# project referenced transitively by FsQuiz, but
# the other binaries (FsAgent, FsMonitor, ...) do not depend on it, so we
# have to copy it explicitly here. The output lives under the standard
# SDK-style bin\Release\net8.0-windows\ folder — there is no x64\
# subdirectory.
$hookDll = Join-Path $SourceDir "src\FsHook\bin\Release\net8.0-windows\FsHook.dll"
if (Test-Path $hookDll) {
    Copy-Item $hookDll $InstallDir -Force
} else {
    Write-Warning "FsHook.dll not built (expected at $hookDll). Hook DLL required for hardening."
}

# 6. Write agent.json (parent-editable)
$configDir = Join-Path $env:ProgramData "FamilySafety"
New-Item -ItemType Directory -Force -Path $configDir | Out-Null
$cfg = @{
    backendUrl = $BackendUrl
    deviceName = $env:COMPUTERNAME
    heartbeatIntervalSec = 30
    usageFlushIntervalSec = 60
    debug = $false
} | ConvertTo-Json
$cfgPath = Join-Path $configDir "agent.json"
Set-Content -Path $cfgPath -Value $cfg -Encoding UTF8

# 7. Apply NTFS ACL: deny "Users" group write/delete on install dir
$acl = Get-Acl $InstallDir
$denyRule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    "Users", "Delete,DeleteSubdirectoriesAndFiles,Write,Modify", "ContainerInherit,ObjectInherit", "Deny")
$acl.AddAccessRule($denyRule)
Set-Acl $InstallDir $acl
Write-Host "Applied NTFS deny rule for Users on $InstallDir"

# 8. Install Windows Service
$serviceName = "FamilySafetyWatchdog"
$existing = Get-Service -Name $serviceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Service $serviceName already installed"
} else {
    New-Service -Name $serviceName -BinaryPathName "$InstallDir\FsWatchdogService.exe" -StartupType Automatic -DisplayName "FamilySafety Watchdog" -Description "Monitors and restarts FamilySafety Agent" | Out-Null
    Write-Host "Installed service $serviceName"
}

# 9. Start the service
Start-Service -Name $serviceName -ErrorAction SilentlyContinue
Write-Host "Started service $serviceName"

# 10. Also create a Scheduled Task as backup auto-start (survives if SCM fails)
$taskName = "FamilySafety Watchdog (Scheduled)"
$existingTask = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if (-not $existingTask) {
    $action = New-ScheduledTaskAction -Execute "$InstallDir\FsWatchdogService.exe" -Argument "--run-watchdog"
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 5 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -User "SYSTEM" -RunLevel Highest | Out-Null
    Write-Host "Created scheduled task $taskName (SYSTEM user, AtLogOn)"
}

Write-Host ""
Write-Host "Installation complete." -ForegroundColor Green
Write-Host "Install dir: $InstallDir"
Write-Host "Config dir:  $configDir"
Write-Host "Service:     $serviceName"
Write-Host "Logs:        $configDir\logs"
Write-Host ""
Write-Host "First-run will auto-register this device with the backend." -ForegroundColor Cyan
