using FsCommon;
using System.Diagnostics;

namespace FsMonitor;

/// <summary>
/// FsMonitor: tracks active foreground window + process name + idle time.
/// Sends UsageRecordIn messages to FsAgent via named pipe.
/// Runs silently (no UI); survives via FsWatchdog.
/// </summary>
internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        Logger.Init(ProcessNames.Monitor);
        Logger.Info(ProcessNames.Monitor, "Starting FsMonitor");

        var cfg = AgentConfig.Load();
        var sink = new IpcClient();

        // Connect to FsAgent (retry loop). IpcClient.Connect() swallows its
        // own failures; we just keep retrying until the pipe becomes live.
        while (!sink.Connected)
        {
            Logger.Warn(ProcessNames.Monitor, "Waiting for FsAgent pipe...");
            sink.Connect();
            Thread.Sleep(2000);
        }

        var tracker = new ForegroundTracker(cfg, rec => sink.SendUsage(rec));

        try
        {
            while (true)
            {
                try
                {
                    tracker.Tick();
                }
                catch (Exception ex)
                {
                    Logger.Warn(ProcessNames.Monitor, $"Tracker error: {ex.Message}");
                }
                Thread.Sleep(1000);
            }
        }
        finally
        {
            // Best-effort flush on shutdown so a clean exit doesn't drop the open slice.
            try { tracker.Flush(); } catch { /* ignore */ }
        }
    }
}
