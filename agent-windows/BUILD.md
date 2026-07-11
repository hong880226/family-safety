# FamilySafety Windows Agent - Build & Run

## Prerequisites

1. Windows 10/11 (64-bit)
2. [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0)
3. FamilySafety backend running (see `../deploy/README.md`)

## Build

```cmd
cd agent-windows
dotnet restore FamilySafety.sln
dotnet build FamilySafety.sln -c Release
```

Output binaries land in:
- `src\FsWatchdog\bin\Release\net8.0-windows\FsWatchdog.exe`
- `src\FsAgent\bin\Release\net8.0-windows\FsAgent.exe`
- `src\FsMonitor\bin\Release\net8.0-windows\FsMonitor.exe`
- `src\FsQuiz\bin\Release\net8.0-windows\FsQuiz.exe`
- `src\FsTray\bin\Release\net8.0-windows\FsTray.exe`

## First-run setup

1. Edit `src\FsWatchdog\bin\Release\net8.0-windows\agent-config.json`:
   ```json
   {
     "backendUrl": "http://192.168.1.10:8000"
   }
   ```
   Then copy this file to `%ProgramData%\FamilySafety\`:
   ```cmd
   mkdir %ProgramData%\FamilySafety
   copy agent-config.json %ProgramData%\FamilySafety\agent.json
   ```

2. Run FsWatchdog (which spawns the others):
   ```cmd
   src\FsWatchdog\bin\Release\net8.0-windows\FsWatchdog.exe
   ```

3. FsAgent auto-registers the device on first run. Check logs:
   ```cmd
   type %ProgramData%\FamilySafety\logs\FsAgent.log
   ```

## Install as a service (P4 feature)

When P4 adds the SCM service wrapper, you'll be able to:

```cmd
sc create FamilySafetyWatchdog binPath= "C:\Program Files\FamilySafety\FsWatchdog.exe" start= auto
sc start FamilySafetyWatchdog
```

## Development workflow

```cmd
# Live rebuild on changes
dotnet watch build --project src/FsAgent

# Run a single process for debugging
dotnet run --project src/FsAgent -c Debug
```

## Logs

`%ProgramData%\FamilySafety\logs\*.log` — one file per process.

Tail them with:
```powershell
Get-Content $env:ProgramData\FamilySafety\logs\FsAgent.log -Tail 20 -Wait
```

## Testing without Windows

The C# code uses `System.Management`, `user32.dll`, and WinForms APIs that
require Windows. Cross-platform compilation is not supported.

For Linux/macOS dev, focus on the Python backend (see `../backend/`).