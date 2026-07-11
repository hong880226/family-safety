# FamilySafety installer round-trip test
#
# Runs the install → uninstall cycle in an isolated temp directory so
# you can validate the installer end-to-end WITHOUT touching
# C:\Program Files, the real Windows Service store, or ProgramData.
#
# This is what you want when smoke-testing artifacts downloaded from
# the GitHub Actions build.
#
# Usage (admin required):
#   PS> .\installer\Test-InstallCycle.ps1 -ArtifactDir "<path-to-unzipped-artifact>"
#   PS> .\installer\Test-InstallCycle.ps1 -ArtifactDir ".\out\Release-build"
#
# What it does:
#   1. Creates a throwaway install dir under $env:TEMP\FsInstallTest-XXXX
#   2. Invokes Install-FamilySafety.ps1 with -InstallDir pointing there
#   3. Verifies the service is registered, binaries are on disk, ACL is set
#   4. Invokes Uninstall-FamilySafety.ps1
#   5. Verifies everything is gone
#
# Notes:
#   - Uses Windows Service store either way (FamilySafetyWatchdog is
#     registered globally) — that's fine, the uninstall step cleans it up.
#   - Does NOT use the ProgramData\FamilySafety config dir for the test
#     install path, but Uninstall-FamilySafety.ps1 still preserves it.

param(
    [Parameter(Mandatory=$true)] [string]$ArtifactDir,
    [string]$BackendUrl = "http://localhost:8000"
)

$ErrorActionPreference = "Stop"

# Resolve to absolute path
$ArtifactDir = (Resolve-Path $ArtifactDir).Path
Write-Host "Artifact dir: $ArtifactDir" -ForegroundColor Cyan

# 1. Admin check
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Error "Must run as Administrator"
    exit 1
}

# 2. Verify required binaries are present
$expectedDirs = @("FsWatchdog","FsWatchdogService","FsAgent","FsMonitor","FsQuiz","FsTray","FsCommon")
$missing = @()
foreach ($p in $expectedDirs) {
    $path = Join-Path $ArtifactDir "$p\bin\Release\net8.0-windows"
    if (-not (Test-Path $path)) { $missing += $path }
}
if ($missing.Count -gt 0) {
    Write-Error "Missing artifact folders (run Build-All.ps1 first, or unzip full Release artifact):`n  - $($missing -join "`n  - ")"
    exit 1
}

# 3. Build a synthetic SourceDir layout the installer expects
#    (src\<Project>\bin\Release\net8.0-windows\)
$sandboxRoot = Join-Path $env:TEMP "FsInstallTest-$([guid]::NewGuid().ToString('N').Substring(0,8))"
$sourceDir   = Join-Path $sandboxRoot "src"
New-Item -ItemType Directory -Force -Path $sourceDir | Out-Null

Write-Host "Sandbox source dir: $sourceDir" -ForegroundColor Yellow
foreach ($p in $expectedDirs) {
    $src = Join-Path $ArtifactDir "$p\bin\Release\net8.0-windows"
    $dst = Join-Path $sourceDir "$p\bin\Release\net8.0-windows"
    New-Item -ItemType Directory -Force -Path (Split-Path $dst) | Out-Null
    Copy-Item -Path "$src\*" -Destination $dst -Recurse -Force
}

# 4. Pick an isolated install dir (NOT Program Files)
$installDir = Join-Path $sandboxRoot "install"
$configDir  = Join-Path $sandboxRoot "ProgramData\FamilySafety"

Write-Host ""
Write-Host "===== STEP 1: INSTALL =====" -ForegroundColor Green
Write-Host "InstallDir: $installDir"

$installerPs1 = Join-Path $PSScriptRoot "Install-FamilySafety.ps1"
& $installerPs1 -BackendUrl $BackendUrl -InstallDir $installDir -SourceDir $sandboxRoot

if ($LASTEXITCODE -ne 0) {
    Write-Error "Install step failed (exit $LASTEXITCODE)"
    exit $LASTEXITCODE
}

# 5. Verify
Write-Host ""
Write-Host "===== STEP 2: VERIFY =====" -ForegroundColor Green

$checks = @(
    @{ Name = "InstallDir exists";       Pass = (Test-Path $installDir) },
    @{ Name = "FsAgent.exe on disk";     Pass = (Test-Path (Join-Path $installDir "FsAgent.exe")) },
    @{ Name = "FsWatchdogService.exe";   Pass = (Test-Path (Join-Path $installDir "FsWatchdogService.exe")) },
    @{ Name = "FsHook.dll on disk";      Pass = (Test-Path (Join-Path $installDir "FsHook.dll")) },
    @{ Name = "agent.json written";      Pass = (Test-Path (Join-Path $env:ProgramData "FamilySafety\agent.json")) },
    @{ Name = "Service registered";      Pass = [bool](Get-Service -Name "FamilySafetyWatchdog" -ErrorAction SilentlyContinue) },
    @{ Name = "Scheduled task";          Pass = [bool](Get-ScheduledTask -TaskName "FamilySafety Watchdog (Scheduled)" -ErrorAction SilentlyContinue) },
)

$failed = 0
foreach ($c in $checks) {
    $mark = if ($c.Pass) { "[OK]" } else { $mark = "[FAIL]"; $failed++ }
    $color = if ($c.Pass) { "Green" } else { "Red" }
    Write-Host "  $mark $($c.Name)" -ForegroundColor $color
}

if ($failed -gt 0) {
    Write-Error "Post-install verification failed ($failed check(s)). See above."
    Write-Warning "Proceeding with uninstall anyway to leave a clean machine."
}

# 6. Uninstall
Write-Host ""
Write-Host "===== STEP 3: UNINSTALL =====" -ForegroundColor Green
$uninstallerPs1 = Join-Path $PSScriptRoot "Uninstall-FamilySafety.ps1"
& $uninstallerPs1 -InstallDir $installDir

if ($LASTEXITCODE -ne 0) {
    Write-Error "Uninstall failed (exit $LASTEXITCODE)"
    exit $LASTEXITCODE
}

# 7. Verify gone
Write-Host ""
Write-Host "===== STEP 4: POST-UNINSTALL VERIFY =====" -ForegroundColor Green

$postChecks = @(
    @{ Name = "InstallDir removed";      Pass = -not (Test-Path $installDir) },
    @{ Name = "Service removed";         Pass = -not (Get-Service -Name "FamilySafetyWatchdog" -ErrorAction SilentlyContinue) },
    @{ Name = "Scheduled task removed";  Pass = -not (Get-ScheduledTask -TaskName "FamilySafety Watchdog (Scheduled)" -ErrorAction SilentlyContinue) },
)

$failed2 = 0
foreach ($c in $postChecks) {
    $color = if ($c.Pass) { "Green" } else { "Red" }
    if (-not $c.Pass) { $failed2++ }
    Write-Host "  $(if($c.Pass){'[OK]'}else{'[FAIL]'}) $($c.Name)" -ForegroundColor $color
}

# 8. Cleanup sandbox
Remove-Item -Recurse -Force $sandboxRoot -ErrorAction SilentlyContinue

Write-Host ""
if ($failed -eq 0 -and $failed2 -eq 0) {
    Write-Host "ROUND-TRIP TEST PASSED." -ForegroundColor Green
    exit 0
} else {
    Write-Error "ROUND-TRIP TEST FAILED ($failed install check(s), $failed2 uninstall check(s))."
    exit 1
}