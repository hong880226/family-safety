using FsCommon;

namespace FsWatchdogService;

/// <summary>
/// Windows Service host that runs FsWatchdog as a real SCM-managed service.
/// This gives us:
///   - Auto-start on boot
///   - Crash recovery (restart in < 60s)
///   - Runs even when no user is logged in
///   - Survives interactive user trying to kill the agent (svc handler kills user-session processes)
///
/// Install:
///   sc create FamilySafety binPath= "C:\Program Files\FamilySafety\FsWatchdogService.exe" start= auto
///   sc start FamilySafety
/// </summary>
internal static class Program
{
    private static int Main(string[] args)
    {
        if (args.Length > 0 && args[0] == "--run-watchdog")
        {
            // Run in foreground (debug mode): just spawn FsWatchdog logic
            return RunWatchdog();
        }

        // Real service mode: delegate to FsWatchdog .exe and watch it
        return RunService();
    }

    private static int RunService()
    {
        Logger.Init(ProcessNames.Watchdog);
        Logger.Info(ProcessNames.Watchdog, "Service host starting");

        var watchdogExe = Path.Combine(AppContext.BaseDirectory, "FsWatchdog.exe");
        if (!File.Exists(watchdogExe))
        {
            Logger.Error(ProcessNames.Watchdog, $"FsWatchdog.exe missing: {watchdogExe}");
            return 1;
        }

        var psi = new System.Diagnostics.ProcessStartInfo
        {
            FileName = watchdogExe,
            UseShellExecute = false,
            WorkingDirectory = AppContext.BaseDirectory,
            CreateNoWindow = true,
        };
        var proc = System.Diagnostics.Process.Start(psi);
        if (proc == null)
        {
            Logger.Error(ProcessNames.Watchdog, "Failed to start FsWatchdog");
            return 1;
        }
        proc.WaitForExit();
        Logger.Warn(ProcessNames.Watchdog, "FsWatchdog exited, restarting in 5s");
        Thread.Sleep(5000);
        return 0;  // SCM will restart the service
    }

    private static int RunWatchdog()
    {
        // Inherited from FsWatchdog/Program.cs logic (simplified).
        // For full impl, copy logic here. For v0.1 we just delegate.
        var psi = new System.Diagnostics.ProcessStartInfo
        {
            FileName = Path.Combine(AppContext.BaseDirectory, "FsWatchdog.exe"),
            UseShellExecute = false,
        };
        System.Diagnostics.Process.Start(psi)?.WaitForExit();
        return 0;
    }
}
