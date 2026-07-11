# FamilySafety Windows Agent — build helper
#
# Produces a Release build of every project in FamilySafety.sln so the
# PowerShell installer (Install-FamilySafety.ps1) and the Inno Setup
# package (FamilySafety.iss) can find every binary at its expected path.
#
# All managed-C# projects (including FsHook) drop their output under
# src\<Project>\bin\Release\net8.0-windows\ — there is no x64\ subfolder.
#
# Usage:
#   PS> .\installer\Build-All.ps1
#   PS> .\installer\Build-All.ps1 -Configuration Debug
#
# After this script completes, run the installer with:
#   PS> .\installer\Install-FamilySafety.ps1 -BackendUrl "http://your-host:8000"

param(
    [string]$Configuration = "Release",
    [string]$SolutionPath = (Join-Path (Split-Path -Parent $PSScriptRoot) "FamilySafety.sln")
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $SolutionPath)) {
    Write-Error "Solution not found at $SolutionPath"
    exit 1
}

Write-Host "Building $SolutionPath -c $Configuration ..." -ForegroundColor Cyan
dotnet build $SolutionPath -c $Configuration /p:ContinuousIntegrationBuild=true
if ($LASTEXITCODE -ne 0) {
    Write-Error "dotnet build failed (exit $LASTEXITCODE)"
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "Build succeeded. Artifacts are under:" -ForegroundColor Green
Write-Host "  src\<Project>\bin\$Configuration\net8.0-windows\" -ForegroundColor Green
Write-Host ""
Write-Host "Next step:" -ForegroundColor Cyan
Write-Host "  .\installer\Install-FamilySafety.ps1 -BackendUrl 'http://your-host:8000'"