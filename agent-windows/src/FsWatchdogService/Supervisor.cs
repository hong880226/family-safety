using FsCommon;
using Microsoft.Extensions.Hosting;
using System.Diagnostics;

namespace FsWatchdogService;

/// <summary>
/// Long-running hosted service: orchestrates child processes and runs the
/// liveness loop. SCM calls StartAsync/StopAsync; we own the child PIDs and
/// the watchdog loop. StopAsync must return quickly — we just signal the
/// loop and kill the children.
/// </summary>
internal sealed class Supervisor : BackgroundService
{
    private static readonly TimeSpan HeartbeatTimeout = TimeSpan.FromSeconds(30);
    private static readonly TimeSpan MonitorInterval = TimeSpan.FromSeconds(5);

    // Staggered startup delays (relative to Supervisor.StartAsync).
    private static readonly TimeSpan TrayDelay = TimeSpan.FromMilliseconds(500);
    private static readonly TimeSpan AgentDelay = TimeSpan.FromSeconds(2);
    private static readonly TimeSpan MonitorDelay = TimeSpan.FromSeconds(4);

    private readonly CancellationTokenSource _stopping = new();
    private readonly Dictionary<string, Process> _children = new(StringComparer.OrdinalIgnoreCase);

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        // Wire the SCM stop signal into our local CTS so the inner loop
        // sees both signals.
        using var linked = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken, _stopping.Token);

        Logger.Info(ProcessNames.Watchdog, "Supervisor starting child processes");

        try
        {
            LaunchIfMissing(ProcessNames.Tray, TrayDelay, linked.Token);
            LaunchIfMissing(ProcessNames.Agent, AgentDelay, linked.Token);
            LaunchIfMissing(ProcessNames.Monitor, MonitorDelay, linked.Token);
        }
        catch (OperationCanceledException)
        {
            Logger.Info(ProcessNames.Watchdog, "Supervisor cancelled before children were all up");
            return;
        }

        Logger.Info(ProcessNames.Watchdog, "All children launched; entering watch loop");

        var aliveFile = Path.Combine(AgentConfig.ConfigDir, "agent.alive");
        var installedDir = AppContext.BaseDirectory;

        while (!linked.IsCancellationRequested)
        {
            try
            {
                await Task.Delay(MonitorInterval, linked.Token);
            }
            catch (OperationCanceledException) { break; }

            try
            {
                if (!File.Exists(aliveFile) ||
                    (DateTime.UtcNow - File.GetLastWriteTimeUtc(aliveFile)) > HeartbeatTimeout)
                {
                    Logger.Warn(ProcessNames.Watchdog, "FsAgent heartbeat stale, restarting");
                    RestartChild(ProcessNames.Agent, installedDir, linked.Token);
                }
            }
            catch (Exception ex)
            {
                Logger.Warn(ProcessNames.Watchdog, $"Agent heartbeat check failed: {ex.Message}");
            }

            if (!IsRunning(ProcessNames.Monitor))
            {
                Logger.Warn(ProcessNames.Watchdog, "FsMonitor dead, restarting");
                RestartChild(ProcessNames.Monitor, installedDir, linked.Token);
            }

            if (!IsRunning(ProcessNames.Tray))
            {
                Logger.Warn(ProcessNames.Watchdog, "FsTray dead, restarting");
                RestartChild(ProcessNames.Tray, installedDir, linked.Token);
            }
        }

        Logger.Info(ProcessNames.Watchdog, "Watch loop exited");
    }

    public override async Task StopAsync(CancellationToken cancellationToken)
    {
        Logger.Info(ProcessNames.Watchdog, "StopAsync: signaling children to terminate");
        Program.WriteEventLog(EventLogEntryType.Information, Program.EventIdStopping,
            "FamilySafety watchdog stopping; terminating child processes.");

        _stopping.Cancel();

        foreach (var (name, proc) in _children)
        {
            try
            {
                if (proc != null && !proc.HasExited)
                {
                    proc.Kill(entireProcessTree: true);
                    Logger.Info(ProcessNames.Watchdog, $"Killed {name} (pid {proc.Id})");
                }
            }
            catch (Exception ex)
            {
                Logger.Warn(ProcessNames.Watchdog, $"Kill {name} failed: {ex.Message}");
            }
        }

        // Sweep any orphans by name (e.g. ones we did not launch this session).
        foreach (var name in new[] { ProcessNames.Agent, ProcessNames.Monitor, ProcessNames.Tray })
        {
            try
            {
                foreach (var p in Process.GetProcessesByName(name))
                {
                    try { p.Kill(entireProcessTree: true); } catch { /* ignore */ }
                }
            }
            catch { /* ignore */ }
        }

        await base.StopAsync(cancellationToken);
    }

    private void LaunchIfMissing(string name, TimeSpan delay, CancellationToken ct)
    {
        if (ct.IsCancellationRequested) return;
        if (IsRunning(name))
        {
            Logger.Info(ProcessNames.Watchdog, $"{name} already running");
            return;
        }

        try { Task.Delay(delay, ct).GetAwaiter().GetResult(); }
        catch (OperationCanceledException) { throw; }

        StartChild(name, AppContext.BaseDirectory, ct);
    }

    private void RestartChild(string name, string installedDir, CancellationToken ct)
    {
        if (_children.TryGetValue(name, out var old))
        {
            try { if (old is { HasExited: false }) old.Kill(entireProcessTree: true); }
            catch { /* ignore */ }
            _children.Remove(name);
        }
        StartChild(name, installedDir, ct);
        Program.WriteEventLog(EventLogEntryType.Warning, Program.EventIdChildDied,
            $"FamilySafety: restarted {name}");
    }

    private void StartChild(string name, string installedDir, CancellationToken ct)
    {
        if (ct.IsCancellationRequested) return;

        var exe = Path.Combine(installedDir, name + ".exe");
        if (!File.Exists(exe))
        {
            Logger.Error(ProcessNames.Watchdog, $"{exe} not found");
            return;
        }

        try
        {
            var psi = new ProcessStartInfo
            {
                FileName = exe,
                UseShellExecute = false,
                WorkingDirectory = installedDir,
                CreateNoWindow = name == ProcessNames.Watchdog, // never ourselves here
            };
            var proc = Process.Start(psi);
            if (proc == null)
            {
                Logger.Error(ProcessNames.Watchdog, $"Process.Start returned null for {name}");
                return;
            }
            _children[name] = proc;
            Logger.Info(ProcessNames.Watchdog, $"Launched {name} (pid {proc.Id})");
        }
        catch (Exception ex)
        {
            Logger.Error(ProcessNames.Watchdog, $"Failed to launch {name}", ex);
        }
    }

    private static bool IsRunning(string name)
    {
        try { return Process.GetProcessesByName(name).Length > 0; }
        catch { return false; }
    }
}