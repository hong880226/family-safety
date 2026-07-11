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

                    // Process commands (e.g. force_quiz). capture_screen is
                    // awaited so the upload finishes before the next heartbeat
                    // tick fires; lock/shutdown/reboot remain fire-and-forget.
                    foreach (var cmd in hb.Commands)
                    {
                        await HandleCommandAsync(cmd, cfg, ipc, client, ct);
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

    private static async Task HandleCommandAsync(
        System.Text.Json.JsonElement cmd,
        AgentConfig cfg,
        IpcServer ipc,
        BackendClient client,
        CancellationToken ct)
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
                case "capture_screen":
                    {
                        // PR-D: privacy-first capture flow. We always tell
                        // FsTray to pop a "家长正在查看你的桌面" balloon BEFORE
                        // the shutter fires, then wait briefly so the balloon
                        // has a chance to render on the user's desktop.
                        var trigger = cmd.TryGetProperty("trigger_type", out var tProp)
                            ? (tProp.GetString() ?? "parent_now")
                            : "parent_now";
                        Logger.Info(ProcessNames.Agent,
                            $"Command: capture_screen received (trigger={trigger})");

                        NotifyService.NotifyScreenshotCapture(trigger);

                        try { await Task.Delay(TimeSpan.FromSeconds(2), ct); }
                        catch (OperationCanceledException) { return; }

                        var jpeg = ScreenshotCapture.CapturePrimaryScreenJpeg(quality: 60);
                        if (jpeg != null && jpeg.Length > 0)
                        {
                            var ok = await client.UploadScreenshotAsync(jpeg, trigger, ct);
                            if (ok)
                                Logger.Info(ProcessNames.Agent,
                                    $"Uploaded screenshot ({jpeg.Length} bytes)");
                            else
                                Logger.Warn(ProcessNames.Agent,
                                    "Screenshot upload returned non-success");
                        }
                        else
                        {
                            Logger.Warn(ProcessNames.Agent,
                                "Screenshot capture produced empty/null bytes");
                        }
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
