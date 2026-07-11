<#
.SYNOPSIS
    Initialize git repo and prepare for first push to GitHub.

.DESCRIPTION
    This script is idempotent: it can be re-run safely.

    What it does:
      1. Verifies git is available (uses PortableGit if not in PATH).
      2. `git init` + sets default branch to `main` + sets user identity
         (only if not already configured locally for this repo).
      3. Adds all files and creates the initial commit on `main`.
      4. Creates a feature branch `fix/redos-quantified-alternation` and
         applies the ReDoS fix as a separate commit on top of the snapshot
         (so the very first push shows a clean, reviewable PR).
      5. Prints the next 3 commands you need to run to push to GitHub.

.PARAMETER GitExe
    Path to git.exe. Defaults to E:\softwareCollection\PortableGit\bin\git.exe.
    Override if your PortableGit lives elsewhere.

.EXAMPLE
    pwsh -ExecutionPolicy Bypass -File scripts\prepare-repo-for-github.ps1
#>

[CmdletBinding()]
param(
    [string]$GitExe = 'E:\softwareCollection\PortableGit\bin\git.exe',
    [string]$RepoPath = 'E:\codeRepo\familysafety',
    [string]$Branch = 'fix/redos-quantified-alternation',
    [string]$UserName = 'FamilySafety Maintainer',
    [string]$UserEmail = 'noreply@example.com'
)

$ErrorActionPreference = 'Stop'

function Assert-Command($path, $label) {
    if (-not (Test-Path $path)) {
        throw "$label not found at $path"
    }
}

Assert-Command $GitExe 'git.exe'
Assert-Command $RepoPath 'Repo path'

Push-Location $RepoPath
try {
    Write-Host "==[1/6]== Verifying git availability..." -ForegroundColor Cyan
    & $GitExe --version

    Write-Host "==[2/6]== Initializing repository (idempotent)..." -ForegroundColor Cyan
    if (-not (Test-Path '.git')) {
        & $GitExe init -b main
    } else {
        Write-Host "  .git already exists, skipping init"
    }

    Write-Host "==[3/6]== Setting local user identity..." -ForegroundColor Cyan
    $currentName = & $GitExe config --local user.name 2>$null
    $currentEmail = & $GitExe config --local user.email 2>$null
    if ([string]::IsNullOrWhiteSpace($currentName)) {
        & $GitExe config --local user.name $UserName
    }
    if ([string]::IsNullOrWhiteSpace($currentEmail)) {
        & $GitExe config --local user.email $UserEmail
    }
    Write-Host "  user.name  = $(& $GitExe config --local user.name)"
    Write-Host "  user.email = $(& $GitExe config --local user.email)"

    Write-Host "==[4/6]== Creating initial snapshot commit on main..." -ForegroundColor Cyan
    & $GitExe add -A
    # Allow empty commit if all files were already tracked from a previous run
    & $GitExe commit -m "chore: initial repository snapshot" --allow-empty
    # (EOL handling — make sure CRLF doesn't break line endings on Windows)
    & $GitExe config --local core.autocrlf input

    Write-Host "==[5/6]== Creating feature branch with ReDoS fix on top..." -ForegroundColor Cyan
    $branchExists = & $GitExe branch --list $Branch
    if ([string]::IsNullOrWhiteSpace($branchExists)) {
        & $GitExe checkout -b $Branch
    } else {
        & $GitExe checkout $Branch
    }

    # The ReDoS fix is already in the working tree. Stage only the three
    # affected files so the commit is reviewable.
    $fixFiles = @(
        'backend/app/services/content_classifier.py',
        'backend/app/schemas/web_inputs.py',
        'backend/tests/test_content_classifier.py'
    )
    foreach ($f in $fixFiles) {
        if (Test-Path $f) {
            & $GitExe add $f
        } else {
            Write-Warning "  expected file missing: $f"
        }
    }
    & $GitExe diff --cached --quiet
    if ($LASTEXITCODE -ne 0) {
        & $GitExe commit -m "fix(security): reject quantified alternation patterns in content classifier

ReDoS probe revealed that the existing heuristic missed patterns of the
form (a|a)+, (a|bc)+, etc.  These pass the original 'quantified literal'
guard because the inner branches look innocent, but the backtracking
engine still enumerates exponentially on adversarial input.

- Add 'r\"\\([^()]*\\|[^()]*\\)[+*]\"' to _BAD_PATTERN_FRAGMENTS
- Sync the same guard in schemas/web_inputs.py to cover the form layer
- Add two regression tests (reject + safe-search fast-path)"
    } else {
        Write-Host "  no staged changes, skipping fix commit (already present?)"
    }

    Write-Host "==[6/6]== Returning to main and printing next steps..." -ForegroundColor Cyan
    & $GitExe checkout main

    Write-Host ""
    Write-Host "Done. Repo is ready at $RepoPath" -ForegroundColor Green
    Write-Host ""
    Write-Host "Next, run these three commands (substitute <your-github-url>):" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  1) git remote add origin <your-github-url>" -ForegroundColor White
    Write-Host "  2) git push -u origin main" -ForegroundColor White
    Write-Host "  3) git push -u origin $Branch" -ForegroundColor White
    Write-Host ""
    Write-Host "Then open a PR on GitHub: $Branch  -->  main" -ForegroundColor Yellow
}
finally {
    Pop-Location
}
