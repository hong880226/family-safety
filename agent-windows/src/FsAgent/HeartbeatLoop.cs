using FsCommon;

namespace FsAgent;

/// <summary>
/// Sends periodic heartbeat + flushes usage buffer.
/// </summary>
internal static class HeartbeatLoop
{
    public static async Task RunAsync(
        BackendClient client,
        AgentConfig cfg,
        IpcServer ipc,
        CancellationToken ct)
    {
        var startTime = DateTime.UtcNow;
        var usageBuffer = new List<UsageRecordIn>();
        var lastFlush = DateTime.UtcNow;

        while (!ct.IsCancellationRequested)
        {
            try
            {
                // Compute usage seconds from buffered records
                var todaySec = ipc.GetTodayUsageSeconds();
                var weekSec = ipc.GetWeekUsageSeconds();

                var hb = await client.HeartbeatAsync(new HeartbeatRequest
                {
                    Timestamp = DateTime.UtcNow,
                    WindowsUsername = cfg.WindowsUsername,
                    ComputerModel = cfg.ComputerModel,
                    UsedSecondsToday = todaySec,
                    UsedSecondsThisWeek = weekSec,
                    UptimeSeconds = (int)(DateTime.UtcNow - startTime).TotalSeconds
                }, ct);

                if (hb != null)
                {
                    Logger.Info(ProcessNames.Agent,
                        $"Heartbeat OK: member={hb.MatchedMemberId}, commands={hb.Commands.Count}");

                    // Process commands (e.g. force_quiz)
                    foreach (var cmd in hb.Commands)
                    {
                        HandleCommand(cmd, cfg, ipc);
                    }
                }
            }
            catch (OperationCanceledException) { break; }
            catch (Exception ex)
            {
                Logger.Warn(ProcessNames.Agent, $"Heartbeat failed: {ex.Message}");
            }

            try
            {
                await Task.Delay(TimeSpan.FromSeconds(cfg.HeartbeatIntervalSec), ct);
            }
            catch (OperationCanceledException) { break; }
        }
    }

    private static void HandleCommand(
        System.Text.Json.JsonElement cmd, AgentConfig cfg, IpcServer ipc)
    {
        try
        {
            if (!cmd.TryGetProperty("type", out var typeProp)) return;
            var type = typeProp.GetString();
            switch (type)
            {
                case "force_quiz":
                    Logger.Info(ProcessNames.Agent, "Command: force_quiz received");
                    QuizLauncher.Launch(cfg, reason: "overtime");
                    break;
                case "show_warning":
                    var msg = cmd.TryGetProperty("message", out var m) ? m.GetString() : null;
                    Logger.Info(ProcessNames.Agent, $"Command: show_warning: {msg}");
                    ipc.NotifyWarning(msg);
                    break;
            }
        }
        catch (Exception ex)
        {
            Logger.Warn(ProcessNames.Agent, $"HandleCommand error: {ex.Message}");
        }
    }
}
