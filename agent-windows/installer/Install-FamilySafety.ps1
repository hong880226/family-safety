# FamilySafety Windows Agent installer
# Run as Administrator.
# Usage:
#   PS> .\installer\Install-FamilySafety.ps1 -BackendUrl "http://192.168.1.10:8000" -InstallDir "C:\Program Files\FamilySafety"

param(
    [Parameter(Mandatory=$true)] [string]$BackendUrl,
    [string]$InstallDir = "C:\Program Files\FamilySafety",
    [string]$SourceDir = (Split-Path -Parent $PSScriptRoot)
)

$ServiceName = "FamilySafety"

# 1. Verify admin
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Must run as Administrator"
    exit 1
}

# 2. Create install dir
New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null

# 3. Copy binaries (FsWatchdog merged into FsWatchdogService, no longer built separately)
$binRoot = Join-Path $SourceDir "src"
$projects = @("FsWatchdogService", "FsAgent", "FsMonitor", "FsQuiz", "FsTray", "FsCommon", "FsConfigUI")
foreach ($p in $projects) {
    $release = Join-Path $binRoot "$p\bin\Release\net8.0-windows"
    if (-not (Test-Path $release)) {
        Write-Warning "$p not built yet. Run: dotnet build $SourceDir\FamilySafety.sln -c Release"
        continue
    }
    Copy-Item -Path "$release\*" -Destination $InstallDir -Recurse -Force
}

# 4. Copy FsHook.dll
$hookDll = Join-Path $SourceDir "src\FsHook\bin\Release\net8.0-windows\FsHook.dll"
if (Test-Path $hookDll) {
    Copy-Item $hookDll $InstallDir -Force
} else {
    Write-Warning "FsHook.dll not built (expected at $hookDll). Hook DLL required for hardening."
}

# 5. Write agent.json (parent-editable, non-sensitive)
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

# 6. Apply NTFS ACL: deny "Users" group write/delete on install dir
$acl = Get-Acl $InstallDir
$denyRule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    "Users", "Delete,DeleteSubdirectoriesAndFiles,Write,Modify", "ContainerInherit,ObjectInherit", "Deny")
$acl.AddAccessRule($denyRule)
Set-Acl $InstallDir $acl
Write-Host "Applied NTFS deny rule for Users on $InstallDir"

# 7. Install Windows Service
$existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Service $ServiceName already installed"
} else {
    New-Service -Name $ServiceName `
        -BinaryPathName "$InstallDir\FsWatchdogService.exe" `
        -StartupType Automatic `
        -DisplayName "FamilySafety Watchdog" `
        -Description "Monitors and restarts FamilySafety Agent; supervises child processes." | Out-Null
    Write-Host "Installed service $ServiceName"
}

# 8. First-run: require parent to set the password via the GUI.
#    The watchdog service refuses to start children until parents.bin exists.
#    We launch FsConfigUI.exe elevated and let the parent enter the password.
#    The GUI also writes agent.json (if backendUrl changed) and saves the
#    password to the DPAPI-encrypted parents.bin file.
$configUiExe = Join-Path $InstallDir "FsConfigUI.exe"
$passwordFile = Join-Path $configDir "parents.bin"

Write-Host ""
Write-Host "===== First-run parent setup =====" -ForegroundColor Cyan
Write-Host "Launching FsConfigUI.exe to set parent password and verify the backend URL."
Write-Host "The service will not start until the parent password has been set."
Write-Host ""

$parentConfigDone = $false
for ($attempt = 1; $attempt -le 3; $attempt++) {
    if (Test-Path $passwordFile) {
        Write-Host "parents.bin already exists, skipping setup." -ForegroundColor Green
        $parentConfigDone = $true
        break
    }

    try {
        $proc = Start-Process -FilePath $configUiExe -Verb RunAs -PassThru -Wait
        if (Test-Path $passwordFile) {
            $parentConfigDone = $true
            break
        } else {
            Write-Warning "FsConfigUI did not create parents.bin (exit code $($proc.ExitCode))."
        }
    } catch {
        Write-Warning "Failed to launch FsConfigUI: $_"
    }

    $retry = Read-Host "Parent password not set. Retry? (Y/N)"
    if ($retry -notin @("Y","y","Yes","yes")) { break }
}

if (-not $parentConfigDone) {
    Write-Warning ""
    Write-Warning "Parent password not configured. The service will refuse to start." -ForegroundColor Yellow
    Write-Warning "Run $configUiExe manually to set the password later." -ForegroundColor Yellow
}

# 9. Start the service (will succeed only if parents.bin exists)
Write-Host ""
Start-Service -Name $ServiceName -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2
$svc = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if ($svc -and $svc.Status -eq 'Running') {
    Write-Host "Started service $ServiceName" -ForegroundColor Green
} else {
    Write-Warning "Service $ServiceName is not running. Check EventLog (Application, source: $ServiceName)."
}

# 10. Create desktop shortcut for ongoing configuration
$shortcutPath = [Environment]::GetFolderPath("Desktop") + "\FamilySafety 家长配置.lnk"
$ws = New-Object -ComObject WScript.Shell
$ws.CreateShortcut($shortcutPath).TargetPath = $configUiExe
$ws.CreateShortcut($shortcutPath).WorkingDirectory = $InstallDir
$ws.CreateShortcut($shortcutPath).IconLocation = "$InstallDir\FsTray.exe,0"
$ws.CreateShortcut($shortcutPath).Save() | Out-Null
# Update the COM-created shortcut (CreateShortcut returns the same object twice)
$shortcut = $ws.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $configUiExe
$shortcut.WorkingDirectory = $InstallDir
$shortcut.IconLocation = "$InstallDir\FsTray.exe,0"
$shortcut.Description = "修改 FamilySafety 后台地址和重置家长密码"
$shortcut.Save()
Write-Host "Created desktop shortcut: $shortcutPath"

Write-Host ""
Write-Host "Installation complete." -ForegroundColor Green
Write-Host "Install dir: $InstallDir"
Write-Host "Config dir:  $configDir"
Write-Host "Service:     $ServiceName"
Write-Host "Logs:        $configDir\logs"
Write-Host "Shortcut:    $shortcutPath"
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  - Verify the tray icon (FsTray) appears in the notification area."
Write-Host "  - FsAgent will auto-register with the backend on first run."
Write-Host "  - The parent password is cloud-synced by FsAgent every 5 minutes."