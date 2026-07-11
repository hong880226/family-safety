#pragma once

namespace FsHook {

/// <summary>
/// Blocks Task Manager by setting registry
///   HKCU\Software\Microsoft\Windows\CurrentVersion\Policies\System
///   DisableTaskMgr = 1
/// and disables Ctrl+Alt+Del task manager via system policy.
///
/// To unblock, set DisableTaskMgr = 0 (or delete the value).
/// </summary>
public ref class TaskManagerBlocker
{
public:
    static bool Block();
    static bool Unblock();
    static bool IsBlocked();
};

} // namespace FsHook
