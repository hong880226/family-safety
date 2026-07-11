using FsCommon;

namespace FsAgent;

/// <summary>
/// Sends periodic heartbeat + flushes usage buffer.
/// </summary>
internal static class HeartbeatLoop
{
    // Sync the parent password blob to the cloud every N heartbeats.
    // With cfg.HeartbeatIntervalSec = 30s and N = 10, that's every 5 minutes.
    private const int ParentPasswordSyncEveryNHearbeats = 10;

    public static async Task RunAsync(
        BackendClient client,
        AgentConfig cfg,
        IpcServer ipc,
        CancellationToken ct)
    {
        var startTime = DateTime.UtcNow;
        var usageBuffer = new List<UsageRecordIn>();
        var lastFlush = DateTime.UtcNow;
        var heartbeatCount = 0;

        while (!ct.IsCancellationRequested)
        {
            try
            {
                // Compute usage seconds from buffered records
                var todaySec = ipc.GetTodayUsageSeconds();
                var weekSec = ipc.GetWeekUsageSeconds();
                var (fgApp, fgTitle) = ipc.GetCurrentForeground();

                var hb = await client.HeartbeatAsync(new HeartbeatRequest
                {
                    Timestamp = DateTime.UtcNow,
                    WindowsUsername = cfg.WindowsUsername,
                    ComputerModel = cfg.ComputerModel,
                    CurrentApp = fgApp,
                    WindowTitle = fgTitle,
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

            heartbeatCount++;
            if (heartbeatCount % ParentPasswordSyncEveryNHearbeats == 0)
            {
                await TrySyncParentPasswordAsync(client, ct);
            }

            try
            {
                await Task.Delay(TimeSpan.FromSeconds(cfg.HeartbeatIntervalSec), ct);
            }
            catch (OperationCanceledException) { break; }
        }
    }

    private static async Task TrySyncParentPasswordAsync(BackendClient client, CancellationToken ct)
    {
        try
        {
            var blob = ParentAuth.ExportForSync();
            if (blob == null) return; // not configured yet
            var ok = await client.SyncParentPasswordAsync(new SyncParentPasswordRequest
            {
                Hash = blob.HashBase64,
                Salt = blob.SaltBase64,
                Iterations = blob.Iterations,
            }, ct);
            if (!ok)
                Logger.Warn(ProcessNames.Agent, "Parent password cloud-sync returned non-success");
        }
        catch (OperationCanceledException) { throw; }
        catch (Exception ex)
        {
            Logger.Warn(ProcessNames.Agent, $"Parent password cloud-sync failed: {ex.Message}");
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
                    {
                        // Backend may pass reason = "overtime" | "outside_window"
                        //   | "window_cap_exceeded" | "toxic_content". v1 used a
                        // hardcoded "overtime"; PR-B forwards whatever the
                        // backend sends, defaulting to "overtime" if absent
                        // (older backends / extra-defensive).
                        var reason = cmd.TryGetProperty("reason", out var rProp)
                            ? (rProp.GetString() ?? "overtime")
                            : "overtime";
                        Logger.Info(ProcessNames.Agent,
                            $"Command: force_quiz received (reason={reason})");
                        QuizLauncher.Launch(cfg, reason);
                    }
                    break;
                case "show_warning":
                    {
                        var msg = cmd.TryGetProperty("message", out var m)
                            ? m.GetString() : null;
                        Logger.Info(ProcessNames.Agent,
                            $"Command: show_warning: {msg}");
                        ipc.NotifyWarning(msg);
                    }
                    break;
                case "lock_screen":
                    Logger.Info(ProcessNames.Agent,
                        "Command: lock_screen received");
                    LockScreen.Lock();
                    break;
                case "shutdown":
                    {
                        var sdDelay = cmd.TryGetProperty("delay_seconds", out var sdD)
                            ? sdD.GetInt32() : 60;
                        Logger.Info(ProcessNames.Agent,
                            $"Command: shutdown received (delay={sdDelay}s)");
                        RemotePower.Shutdown(sdDelay);
                    }
                    break;
                case "reboot":
                    {
                        var rbDelay = cmd.TryGetProperty("delay_seconds", out var rbD)
                            ? rbD.GetInt32() : 60;
                        Logger.Info(ProcessNames.Agent,
                            $"Command: reboot received (delay={rbDelay}s)");
                        RemotePower.Reboot(rbDelay);
                    }
                    break;
                default:
                    Logger.Warn(ProcessNames.Agent,
                        $"Command: unknown type '{type}', ignoring");
                    break;
            }
        }
        catch (Exception ex)
        {
            Logger.Warn(ProcessNames.Agent, $"HandleCommand error: {ex.Message}");
        }
    }
}
