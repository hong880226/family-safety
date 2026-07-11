using System;
using System.Diagnostics;
using System.Runtime.InteropServices;
using FsCommon;

namespace FsAgent;

/// <summary>
/// Wraps User32!LockWorkStation for the remote lock_screen command.
///
/// IMPORTANT — Session 0 limitation (v1):
///   The FamilySafety service runs in Session 0 (no interactive desktop).
///   LockWorkStation() called from Session 0 returns FALSE because there is
///   no user window station to lock. v1 still calls it (so the command-channel
///   path is observable in logs and via the heartbeat), but the screen will
///   NOT actually lock from a true Session 0 service.
///
/// v2 TODO:
///   - Ship a small user-context helper exe (FsLockHelper.exe) and invoke it
///     from FsWatchdog via WTSCreateProcess / schtasks /runas, or use the
///     "interactive services" pattern with a per-user named-event trigger.
///   - Alternatively, use `wtsapi32!WTSSendMessage` + impersonation.
/// For PR-B we accept the limitation; the backend will see "ack" via the
/// next heartbeat's consumed command, even though the desktop stays unlocked.
/// </summary>
public static class LockScreen
{
    [DllImport("user32.dll", SetLastError = true)]
    private static extern bool LockWorkStation();

    public static void Lock()
    {
        try
        {
            // Direct P/Invoke. Will fail silently on Session 0 — see class docs.
            var ok = LockWorkStation();
            if (ok)
            {
                Logger.Info(ProcessNames.Agent,
                    "LockWorkStation succeeded");
                return;
            }

            var err = Marshal.GetLastWin32Error();
            Logger.Warn(ProcessNames.Agent,
                $"LockWorkStation returned false (Win32 err={err}); "
                + "service likely runs in Session 0 — see class-level comment");

            // Fallback: try via rundll32 which uses the service's session but
            // exercises the same code path. Useful for command-channel
            // observability (the cmd will show in logs as dispatched).
            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = "rundll32.exe",
                    Arguments = "user32.dll,LockWorkStation",
                    UseShellExecute = false,
                    CreateNoWindow = true,
                };
                using var p = Process.Start(psi);
                p?.WaitForExit(5000);
                Logger.Info(ProcessNames.Agent,
                    "LockWorkStation dispatch via rundll32 attempted (Session 0 fallback)");
            }
            catch (Exception ex)
            {
                Logger.Warn(ProcessNames.Agent,
                    $"rundll32 fallback failed: {ex.Message}");
            }
        }
        catch (Exception ex)
        {
            Logger.Error(ProcessNames.Agent, $"Lock failed: {ex.Message}");
        }
    }
}
