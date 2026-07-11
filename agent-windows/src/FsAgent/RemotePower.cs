using System;
using System.Diagnostics;
using FsCommon;

namespace FsAgent;

/// <summary>
/// Invokes shutdown.exe for the remote shutdown / reboot command.
/// The /t flag gives the user a grace window (default 60s) so they can
/// cancel via `shutdown /a` if needed. Delay is clamped to [0, 3600] seconds
/// (1h max) to defend against a misbehaving backend sending absurd values.
///
/// Reason code /d p:4:1 maps to "Planned: Other (Planned)" per Microsoft's
/// `shutdown /?` table — it's a hint to the event log about why the shutdown
/// was triggered, and is required by some audit / GPO policies.
/// </summary>
public static class RemotePower
{
    private const int MaxDelaySeconds = 3600;

    public static void Shutdown(int delaySeconds = 60)
        => Invoke("/s", delaySeconds);

    public static void Reboot(int delaySeconds = 60)
        => Invoke("/r", delaySeconds);

    private static void Invoke(string action, int delaySeconds)
    {
        if (delaySeconds < 0) delaySeconds = 0;
        if (delaySeconds > MaxDelaySeconds) delaySeconds = MaxDelaySeconds;

        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = "shutdown.exe",
                Arguments =
                    $"{action} /t {delaySeconds} "
                    + "/c \"FamilySafety: 家长已发起远程操作\" /d p:4:1 /f",
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
            };
            using var p = Process.Start(psi);
            p?.WaitForExit(10000);
            Logger.Info(ProcessNames.Agent,
                $"RemotePower {action} /t {delaySeconds} dispatched "
                + $"(exit={p?.ExitCode.ToString() ?? "n/a"})");
        }
        catch (Exception ex)
        {
            Logger.Error(ProcessNames.Agent,
                $"RemotePower {action} failed: {ex.Message}");
        }
    }
}
