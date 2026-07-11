# FamilySafety Windows Agent

C# .NET 8 family of processes that run on each child's Windows computer.

## Process Architecture

```
FsWatchdogService (Windows Service, Session 0)
  │ supervises children, runs the watch loop
  │
  ├── FsTray     (system tray icon, parent menu + password-gated exit)
  │     └── quick actions + "open parent config"
  ├── FsAgent    (core daemon)
  │     ├── Registers device with backend (on first run)
  │     ├── Sends periodic heartbeats (every 30s)
  │     ├── Cloud-syncs parent password blob (every ~5 min)
  │     └── Hosts IPC pipe for monitor + quiz
  ├── FsMonitor  (foreground tracker)
  │     └── Reports (app_name, window_title, duration) to FsAgent
  └── FsQuiz     (fullscreen UI, spawned on demand)
        ├── Start quiz session
        ├── Collect answers
        └── Submit + display reward

FsConfigUI (standalone WinForms, parent-only)
  ├── Configure backend URL
  ├── Set / rotate parent password (PBKDF2 + DPAPI)
  └── Cloud-sync password to backend
```

## Build

The agent is built on **GitHub Actions**, not on developer machines. See
`.github/workflows/agent-windows-build.yml`. The CI artifact is a zip named
`familysafety-agent-windows-<sha>.zip` that bundles all project outputs plus
`FsHook.dll`.

For local builds you need .NET 8 SDK:

```bash
cd agent-windows
dotnet build FamilySafety.sln -c Release
```

Output goes to `src/<Project>/bin/Release/net8.0-windows/`.

## Install

Use the PowerShell installer. It writes `%ProgramData%\FamilySafety\agent.json`,
applies the Users-deny NTFS ACL on the install dir, registers the SCM service
named **`FamilySafety`** (binary `FsWatchdogService.exe`), and then launches
`FsConfigUI.exe` for the parent to set the backend URL and password.

```powershell
# From the unzipped CI artifact:
.\installer\Install-FamilySafety.ps1 -BackendUrl "http://192.168.1.10:8000"
```

The install script is **interactive**: the parent must enter the password
twice before the service will start. If the GUI is dismissed without saving,
the service will refuse to launch its children (logged to EventLog
Application, source `FamilySafety`, event 7001).

After install, the tray icon appears and a desktop shortcut
(`FamilySafety 家长配置.lnk`) lets the parent re-open `FsConfigUI.exe` for
later changes (backend URL, password rotation).

## Configuration

**`%ProgramData%\FamilySafety\agent.json`** (non-sensitive, parent-editable):

```json
{
  "backendUrl": "http://192.168.1.10:8000",
  "deviceName": "DESKTOP-ABC123",
  "heartbeatIntervalSec": 30,
  "usageFlushIntervalSec": 60,
  "debug": false
}
```

`apiKey` and `deviceId` are populated after first successful registration.

**`%ProgramData%\FamilySafety\parents.bin`** (parent password, DPAPI-encrypted):

A `ProtectedData.Protect(scope=LocalMachine)` blob. Only Windows
administrators on this machine can read or modify it. Created by
`FsConfigUI.exe`, verified by the FsTray exit dialog and the
FsWatchdogService OnStart gate.

## CLI subcommands (admin-only)

`FsWatchdogService.exe` doubles as a CLI when run with arguments:

```powershell
.\FsWatchdogService.exe configure --backend-url "http://host:8000"
.\FsWatchdogService.exe set-password    # verify existing, then change
.\FsWatchdogService.exe reset-password  # no verify, audit-logged
.\FsWatchdogService.exe status
```

Without arguments, the binary enters Windows Service mode (handled by SCM).

## Logs

`%ProgramData%\FamilySafety\logs\` — one file per process:

- `FsWatchdog.log` — service supervisor (child restarts, password gate, etc.)
- `FsAgent.log` — heartbeats, cloud-sync attempts, errors
- `FsMonitor.log` — usage tracking
- `FsTray.log` — tray menu, auth attempts
- `auth.log` — password set/reset audit trail

## Process Guarding

| Layer | Implementation |
|-------|----------------|
| Watchdog restart | `FsWatchdogService.Supervisor`, 5s loop, file heartbeat + Process.GetProcessesByName |
| Tray exit gate | `FsTray.RequestExitWithAuth` → `ParentAuth.Verify` (PBKDF2 + DPAPI) |
| Alt+F4 / Win key block | FsHook keyboard hook (during quiz only) |
| Task Manager block | FsHook registry write (during quiz only) |
| UI lock during quiz | Form.TopMost + FsHook |
| NTFS ACL on install dir | `Install-FamilySafety.ps1` denies `Users` write/delete |
| Run as service | `FsWatchdogService.exe`, Session 0, auto-restart via SCM |
| First-run gate | `ParentAuth.IsSet()` check in OnStart; refuses start without password |