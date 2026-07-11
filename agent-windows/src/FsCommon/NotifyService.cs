using System.Diagnostics;

namespace FsCommon;

/// <summary>
/// Helper for the FsAgent to surface a privacy-preserving heads-up before
/// doing something visible to the user (e.g. capturing a screenshot).
///
/// Today the only trick we have is "spawn FsTray.exe --notify-screenshot",
/// which makes the tray briefly show a balloon and exit. We also write an
/// audit line so the action is recoverable from the file log even if the
/// tray never opened (e.g. service crashed mid-flight).
///
/// PR-D note: this is intentionally simple. v2 should consider a shared
/// "ringbuffer" of UI events that the persistent FsTray instance consumes
/// in-process so we don't have to spawn a new exe for every notification.
/// </summary>
public static class NotifyService
{
    public static void NotifyScreenshotCapture(string triggerType)
    {
        try
        {
            var dir = Path.Combine(AgentConfig.ConfigDir, "logs");
            Directory.CreateDirectory(dir);
            var line = $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} [screenshot-notice] " +
                       $"trigger={triggerType}{Environment.NewLine}";
            File.AppendAllText(Path.Combine(dir, "screenshot-notice.log"), line);
        }
        catch
        {
            // logging should not crash the capture path
        }

        try
        {
            var exe = Path.Combine(AppContext.BaseDirectory, "FsTray.exe");
            if (!File.Exists(exe))
            {
                Logger.Warn("NotifyService", "FsTray.exe missing — cannot notify");
                return;
            }
            var psi = new ProcessStartInfo
            {
                FileName = exe,
                Arguments = "--notify-screenshot",
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            using var p = Process.Start(psi);
            // Don't wait — the tray spawns and pops the balloon async.
            // The agent then captures after a short delay (see HeartbeatLoop).
        }
        catch (Exception ex)
        {
            Logger.Warn("NotifyService", $"Notify spawn failed: {ex.Message}");
        }
    }
}
