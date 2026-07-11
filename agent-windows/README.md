# FamilySafety Windows Agent

C# .NET 8 family of processes that run on each child's Windows computer.

## Process Architecture

```
FsWatchdog (the only "service-like" process)
  ├── supervises → restarts if dead
  ├── FsAgent (core daemon)
  │     ├── Registers device with backend
  │     ├── Sends periodic heartbeats
  │     ├── Receives commands (force_quiz, warnings)
  │     └── Hosts IPC pipe for monitor + quiz
  ├── FsMonitor (foreground tracker)
  │     └── Reports (app_name, window_title, duration) to FsAgent
  ├── FsQuiz (fullscreen UI, spawned on demand)
  │     ├── Start quiz session
  │     ├── Collect answers
  │     └── Submit + display reward
  └── FsTray (system tray icon)
        └── Quick actions + warnings
```

## Build

Requires .NET 8 SDK.

```bash
cd agent-windows
dotnet build FamilySafety.sln -c Release
```

Output goes to `src/FsAgent/bin/Release/net8.0-windows/`.

## Run (development)

```bash
# Start in order (FsWatchdog spawns the others)
cd src/FsWatchdog/bin/Release/net8.0-windows
./FsWatchdog.exe
```

## Configuration

`%ProgramData%\FamilySafety\agent.json` is auto-generated on first run:

```json
{
  "backendUrl": "http://192.168.1.10:8000",
  "deviceName": "DESKTOP-ABC123",
  "heartbeatIntervalSec": 30,
  "usageFlushIntervalSec": 60,
  "debug": false
}
```

`api_key` and `device_id` are populated after first successful registration.

## Logs

`%ProgramData%\FamilySafety\logs\{FsWatchdog,FsAgent,FsMonitor,FsQuiz,FsTray}.log`

## Process Guarding (P3 baseline → P4 hardened)

| Layer | P3 | P4 |
|-------|----|----|
| Watchdog restart | file timestamp check | + named pipe ping + WM_TIMER |
| Task Manager block | none | registry + Hook DLL |
| Alt+F4 / Win key block | none | WH_KEYBOARD_LL hook DLL |
| UI lock during quiz | Form.TopMost | + LockSetForegroundWindow |
| NTFS ACL on agent dir | none | DACL prevents child user delete |
| Run as service | none | SCM service via `sc create` |
