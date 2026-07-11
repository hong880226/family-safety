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
        var tracker = new ForegroundTracker(cfg);
        var sink = new IpcClient();
        sink.Connect();

        var lastApp = "";
        var lastTitle = "";
        var lastStart = DateTime.UtcNow;

        while (!sink.Connected)
        {
            Thread.Sleep(2000);
            sink.Connect();
        }

        while (true)
        {
            try
            {
                var (app, title) = WinApi.GetForegroundInfo();
                if (app != lastApp || title != lastTitle)
                {
                    // App changed: emit usage for previous app
                    var now = DateTime.UtcNow;
                    var dur = (int)(now - lastStart).TotalSeconds;
                    if (dur > 0 && !string.IsNullOrEmpty(lastApp))
                    {
                        var rec = new UsageRecordIn
                        {
                            AppName = lastApp,
                            WindowTitle = lastTitle,
                            StartAt = lastStart,
                            EndAt = now,
                            DurationSeconds = dur,
                            IsOvertime = false,
                        };
                        sink.SendUsage(rec);
                    }
                    lastApp = app;
                    lastTitle = title;
                    lastStart = now;
                }
            }
            catch (Exception ex)
            {
                Logger.Warn(ProcessNames.Monitor, $"Tracker error: {ex.Message}");
            }

            Thread.Sleep(1000);
        }
    }
}
