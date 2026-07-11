# FsHook — Low-Level Hook DLL

Native C++/CLI DLL providing low-level Windows hooks for FamilySafety.

## Building

Requires **Visual Studio 2022** with:
- Desktop development with C++ workload
- .NET 8 SDK
- C++/CLI support (built into VS)

```cmd
cd src\FsHook
msbuild FsHook.vcxproj -p:Configuration=Release -p:Platform=x64
```

Output: `src\FsHookd\Release\FsHook.dll`

## What it does

| Function | Implementation | Used when |
|----------|---------------|-----------|
| `KeyboardHook.Install()` | `SetWindowsHookEx(WH_KEYBOARD_LL)` | Quiz mode starts |
| `KeyboardHook.Uninstall()` | `UnhookWindowsHookEx` | Quiz mode ends |
| `KeyboardHook.Suspend/Resume` | internal bool toggle | During text input |
| `TaskManagerBlocker.Block()` | `HKCU\...\DisableTaskMgr=1` | Quiz mode starts |
| `TaskManagerBlocker.Unblock()` | Delete registry value | Quiz mode ends |

## Blocked key combos

- `Alt+F4`        — close window
- `Alt+Tab`       — switch app
- `Alt+Esc`
- `Ctrl+Esc`      — start menu
- `Ctrl+Shift+Esc` — Task Manager (also blocked at registry layer)
- `LWin / RWin`   — start menu / task view

## Security notes

- Hooks only installed during quiz, never permanently
- All hooks uninstalled in finally blocks
- Registry changes auto-reverted on FormClosed or process crash (handled by FsAgent)

## Limitations

- Does NOT block `Ctrl+Alt+Del` (handled by Windows, not user-mode)
- Children in Admin group can still kill the process; use NTFS ACL + standard user account for hardening
