using FsCommon;
using System.Diagnostics;

namespace FsWatchdog;

/// <summary>
/// FsWatchdog: supervises FsAgent + FsMonitor. If they die, restart.
/// P3: file-based liveness + Process.Start. P4: add Win32 hooks / SCM service.
/// </summary>
internal static class Program
{
    private static int Main(string[] args)
    {
        Logger.Init(ProcessNames.Watchdog);
        Logger.Info(ProcessNames.Watchdog, "Starting FsWatchdog");

        var watchdogDir = AppContext.BaseDirectory;
        var agentExe = Path.Combine(watchdogDir, "FsAgent.exe");
        var monitorExe = Path.Combine(watchdogDir, "FsMonitor.exe");
        var trayExe = Path.Combine(watchdogDir, "FsTray.exe");
        var aliveFile = Path.Combine(AgentConfig.ConfigDir, "agent.alive");

        // Spawn the trio
        LaunchIfMissing(agentExe, "FsAgent");
        LaunchIfMissing(monitorExe, "FsMonitor");
        LaunchIfMissing(trayExe, "FsTray");

        while (true)
        {
            Thread.Sleep(5000);

            try
            {
                if (!File.Exists(aliveFile) ||
                    (DateTime.UtcNow - File.GetLastWriteTimeUtc(aliveFile)).TotalSeconds > 30)
                {
                    Logger.Warn(ProcessNames.Watchdog, "FsAgent appears dead, restarting");
                    LaunchIfMissing(agentExe, "FsAgent");
                }
            }
            catch (Exception ex)
            {
                Logger.Warn(ProcessNames.Watchdog, $"Check failed: {ex.Message}");
            }

            // Restart monitor if died
            if (!IsRunning(ProcessNames.Monitor))
            {
                Logger.Warn(ProcessNames.Watchdog, "FsMonitor dead, restarting");
                LaunchIfMissing(monitorExe, "FsMonitor");
            }
        }
    }

    private static void LaunchIfMissing(string exe, string name)
    {
        if (IsRunning(name))
        {
            Logger.Info(ProcessNames.Watchdog, $"{name} already running");
            return;
        }
        try
        {
            if (!File.Exists(exe))
            {
                Logger.Error(ProcessNames.Watchdog, $"{exe} not found");
                return;
            }
            var psi = new ProcessStartInfo
            {
                FileName = exe,
                UseShellExecute = false,
                WorkingDirectory = Path.GetDirectoryName(exe),
            };
            Process.Start(psi);
            Logger.Info(ProcessNames.Watchdog, $"Launched {name}");
        }
        catch (Exception ex)
        {
            Logger.Error(ProcessNames.Watchdog, $"Failed to launch {name}", ex);
        }
    }

    private static bool IsRunning(string name)
    {
        try
        {
            return Process.GetProcessesByName(name).Length > 0;
        }
        catch
        {
            return false;
        }
    }
}
