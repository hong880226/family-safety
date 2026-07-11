using FsCommon;
using System.Diagnostics;
using System.Text.Json;

namespace FsAgent;

/// <summary>
/// FsAgent: the main FamilySafety service process.
/// Responsibilities:
///   - Register device on first run, save api_key locally
///   - Send periodic heartbeats
///   - Buffer and forward usage records from FsMonitor
///   - On force_quiz command, launch FsQuiz and lock the UI
///   - Communicate liveness to FsWatchdog (named pipe / heartbeat)
/// </summary>
internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        Logger.Init(ProcessNames.Agent);
        Logger.Info(ProcessNames.Agent, "Starting FsAgent");

        var cfg = AgentConfig.Load();
        var client = new BackendClient(cfg);

        // First-run registration if needed
        if (string.IsNullOrEmpty(cfg.ApiKey) || string.IsNullOrEmpty(cfg.DeviceId))
        {
            try
            {
                cfg.DeviceId = SystemInfo.GetDeviceId();
                cfg.ComputerModel = SystemInfo.GetComputerModel();
                cfg.WindowsUsername = SystemInfo.GetWindowsUsername();
                Logger.Info(ProcessNames.Agent,
                    $"First-run registration: device={cfg.DeviceId}, user={cfg.WindowsUsername}");

                var reg = client.RegisterAsync(new RegisterRequest
                {
                    DeviceId = null,  // let server assign
                    Name = cfg.DeviceName,
                    DeviceType = "windows",
                    ComputerModel = cfg.ComputerModel,
                    WindowsUsername = cfg.WindowsUsername
                }).GetAwaiter().GetResult();

                if (reg != null)
                {
                    cfg.DeviceId = reg.DeviceId;
                    cfg.ApiKey = reg.ApiKey;
                    cfg.Save();
                    Logger.Info(ProcessNames.Agent,
                        $"Registered: family_id={reg.FamilyId}, member_id={reg.MemberId}");
                }
                else
                {
                    Logger.Error(ProcessNames.Agent, "Registration returned null");
                    return 1;
                }
            }
            catch (Exception ex)
            {
                Logger.Error(ProcessNames.Agent, "First-run registration failed", ex);
                // Continue anyway - we can retry on next heartbeat
            }
        }

        // Start the IPC server for monitor to push usage
        var ipc = new IpcServer();
        ipc.Start();

        // Start the heartbeat loop in background
        using var cts = new CancellationTokenSource();
        var hbTask = HeartbeatLoop.RunAsync(client, cfg, ipc, cts.Token);

        // Start watchdog heartbeat
        var wdTask = WatchdogHeartbeat.RunAsync(cts.Token);

        Logger.Info(ProcessNames.Agent, "FsAgent running. Press Ctrl+C to stop.");

        // Trap console exit
        Console.CancelKeyPress += (s, e) =>
        {
            Logger.Info(ProcessNames.Agent, "Shutdown requested");
            cts.Cancel();
            e.Cancel = true;
        };

        try
        {
            Task.WaitAll(new[] { hbTask, wdTask }, Timeout.Infinite, cts.Token);
        }
        catch (OperationCanceledException)
        {
            // Expected on Ctrl+C
        }

        ipc.Stop();
        Logger.Info(ProcessNames.Agent, "FsAgent exited cleanly");
        return 0;
    }
}
