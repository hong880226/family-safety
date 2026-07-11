# FamilySafety Windows Agent — Build & Install

## Prerequisites

1. Windows 10/11 (64-bit) for installation
2. A reachable FamilySafety backend (see `../deploy/README.md`)
3. **For installation**: download the CI artifact zip from GitHub Actions
   (`.github/workflows/agent-windows-build.yml`). It contains all binaries
   and `FsHook.dll`.
4. **For local development**: .NET 8 SDK (`winget install Microsoft.DotNet.SDK.8`).

## Build (CI)

Push to `main` triggers `.github/workflows/agent-windows-build.yml`. After
the run completes, download `familysafety-agent-windows-zip` from the
Actions page. Extract it anywhere.

The extracted artifact mirrors what the installer expects under
`src/<Project>/bin/Release/net8.0-windows/`.

## Build (local dev)

```powershell
cd agent-windows
dotnet restore FamilySafety.sln
dotnet build FamilySafety.sln -c Release
```

Output binaries land in:
- `src\FsWatchdogService\bin\Release\net8.0-windows\FsWatchdogService.exe`
- `src\FsAgent\bin\Release\net8.0-windows\FsAgent.exe`
- `src\FsMonitor\bin\Release\net8.0-windows\FsMonitor.exe`
- `src\FsQuiz\bin\Release\net8.0-windows\FsQuiz.exe`
- `src\FsTray\bin\Release\net8.0-windows\FsTray.exe`
- `src\FsConfigUI\bin\Release\net8.0-windows\FsConfigUI.exe`

`FsWatchdog` is no longer built separately — its logic merged into
`FsWatchdogService` (BackgroundService).

## Install

From an **elevated** PowerShell, in the unzipped artifact directory:

```powershell
.\installer\Install-FamilySafety.ps1 -BackendUrl "http://192.168.1.10:8000"
```

The installer:

1. Copies binaries + `FsHook.dll` to `C:\Program Files\FamilySafety`
2. Writes `%ProgramData%\FamilySafety\agent.json`
3. Applies the Users-deny NTFS ACL
4. Registers the SCM service **`FamilySafety`** (binary `FsWatchdogService.exe`)
5. Launches **`FsConfigUI.exe`** elevated — parent must enter the password
6. If the password is set, starts the service; otherwise warns and exits
7. Creates a desktop shortcut `FamilySafety 家长配置.lnk`

If you skip the GUI and dismiss the password prompt, the service is
registered but will refuse to start children. Re-run `FsConfigUI.exe`
manually, or:

```powershell
.\FsWatchdogService.exe set-password
Start-Service FamilySafety
```

## Uninstall

```powershell
.\installer\Uninstall-FamilySafety.ps1
```

This stops + deletes the service, kills any remaining children, removes
the install dir and the desktop shortcut, but **preserves**
`%ProgramData%\FamilySafety\` (config + logs + `parents.bin`). To wipe
the parent credentials, delete `parents.bin` manually.

## Logs

`%ProgramData%\FamilySafety\logs\*.log` — one file per process.

```powershell
Get-Content $env:ProgramData\FamilySafety\logs\FsWatchdog.log -Tail 20 -Wait
```

## EventLog

`FamilySafety` writes to the Windows Application log with three event IDs:

- **7001** — start refused (parents.bin missing)
- **7002** — child process died, restarted
- **7003** — service stopping cleanly

View with:

```powershell
Get-EventLog -LogName Application -Source FamilySafety -Newest 20
```

## Testing without Windows

The C# code uses `System.Management`, `user32.dll`, and WinForms APIs that
require Windows. Cross-platform compilation is not supported.

For Linux/macOS dev, focus on the Python backend (see `../backend/`).