using FsCommon;
using Microsoft.Extensions.Hosting;
using System.Diagnostics;
using System.IO.Pipes;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

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
    private Task? _controlListenerTask;

    public override Task StartAsync(CancellationToken cancellationToken)
    {
        Logger.Info(ProcessNames.Watchdog, "StartAsync: spawning control pipe listener");
        _controlListenerTask = Task.Run(() => ListenForControlCommands(_stopping.Token));
        return base.StartAsync(cancellationToken);
    }

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

        await TearDownChildrenAsync();

        await base.StopAsync(cancellationToken);
    }

    /// <summary>
    /// Parent-password-authenticated orderly shutdown. Invoked when FsTray /
    /// FsConfigUI / CLI sends a graceful_stop message on the control pipe.
    /// Tries to close child main windows cleanly first, then escalates to
    /// Kill after 5s. Removes agent.alive so any later relauncher knows we
    /// left on purpose (not crashed).
    /// </summary>
    public Task GracefulStopAsync()
    {
        Logger.Info(ProcessNames.Watchdog, "GracefulStopAsync: requested by parent UI");
        Program.WriteEventLog(EventLogEntryType.Information, Program.EventIdStopping,
            "FamilySafety: graceful_stop via parent-password auth.");

        // Cancel the watch loop so ExecuteAsync returns, then run the
        // standard BackgroundService shutdown path which also calls our
        // (now refactored) StopAsync to tear down children.
        _stopping.Cancel();
        return base.StopAsync(CancellationToken.None);
    }

    private async Task TearDownChildrenAsync()
    {
        foreach (var (name, proc) in _children)
        {
            try
            {
                if (proc != null && !proc.HasExited)
                {
                    try { proc.CloseMainWindow(); }
                    catch { /* process may not have a main window */ }

                    if (!proc.WaitForExit(5000))
                    {
                        proc.Kill(entireProcessTree: true);
                        Logger.Info(ProcessNames.Watchdog,
                            $"Killed {name} (pid {proc.Id}) after 5s grace");
                    }
                    else
                    {
                        Logger.Info(ProcessNames.Watchdog,
                            $"{name} (pid {proc.Id}) closed cleanly");
                    }
                }
            }
            catch (Exception ex)
            {
                Logger.Warn(ProcessNames.Watchdog, $"Stop {name} failed: {ex.Message}");
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

        // Remove the liveness file so a later session can tell we exited cleanly.
        try
        {
            var aliveFile = Path.Combine(AgentConfig.ConfigDir, "agent.alive");
            if (File.Exists(aliveFile)) File.Delete(aliveFile);
        }
        catch { /* best-effort */ }
    }

    /// <summary>
    /// Background loop that listens on <see cref="ProcessNames.WatchdogControlPipe"/>
    /// for parent-issued commands. Currently only graceful_stop is supported.
    /// Spawned once in <see cref="StartAsync"/>.
    /// </summary>
    private async Task ListenForControlCommands(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                using var server = new NamedPipeServerStream(
                    ProcessNames.WatchdogControlPipe,
                    PipeDirection.In,
                    maxNumberOfServerInstances: 1,
                    PipeTransmissionMode.Byte,
                    PipeOptions.Asynchronous);

                await server.WaitForConnectionAsync(ct);
                using var reader = new StreamReader(server, Encoding.UTF8);
                var line = await reader.ReadLineAsync(ct);
                if (line == null) continue;

                HandleControlMessage(line);
            }
            catch (OperationCanceledException) { break; }
            catch (Exception ex)
            {
                Logger.Warn(ProcessNames.Watchdog,
                    $"Control pipe listener error: {ex.Message}");
                try { await Task.Delay(500, ct); } catch { break; }
            }
        }
    }

    private void HandleControlMessage(string json)
    {
        try
        {
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            if (!root.TryGetProperty("type", out var typeProp)) return;
            var type = typeProp.GetString();
            switch (type)
            {
                case "graceful_stop":
                    if (VerifyControlAuth(root))
                    {
                        Logger.Info(ProcessNames.Watchdog,
                            "Received graceful_stop from parent UI (auth ok)");
                        _ = GracefulStopAsync();
                    }
                    else
                    {
                        Logger.Warn(ProcessNames.Watchdog,
                            "graceful_stop received but parent-password hash did not match");
                    }
                    break;
                default:
                    Logger.Warn(ProcessNames.Watchdog,
                        $"Unknown control message type '{type}'");
                    break;
            }
        }
        catch (Exception ex)
        {
            Logger.Warn(ProcessNames.Watchdog,
                $"Bad control message: {ex.GetType().Name}: {ex.Message}");
        }
    }

    private static bool VerifyControlAuth(JsonElement root)
    {
        try
        {
            if (!root.TryGetProperty("password_hash", out var hashProp) ||
                !root.TryGetProperty("salt", out var saltProp) ||
                !root.TryGetProperty("iterations", out var iterProp))
            {
                return false;
            }
            var stored = ParentAuth.ExportForSync();
            if (stored == null) return false;

            // The caller derived PBKDF2 from the entered plaintext using
            // (salt, iter) — same as us. Constant-time compare against the
            // hash we have on disk.
            var supplied = Convert.FromBase64String(hashProp.GetString() ?? "");
            var expected = Convert.FromBase64String(stored.HashBase64);
            return supplied.Length == expected.Length &&
                   CryptographicOperations.FixedTimeEquals(supplied, expected);
        }
        catch (Exception ex)
        {
            Logger.Warn(ProcessNames.Watchdog,
                $"VerifyControlAuth failed: {ex.GetType().Name}: {ex.Message}");
            return false;
        }
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