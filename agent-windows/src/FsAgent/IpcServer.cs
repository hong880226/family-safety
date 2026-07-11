using FsCommon;
using System.Collections.Concurrent;
using System.IO.Pipes;
using System.Text;
using System.Text.Json;

namespace FsAgent;

/// <summary>
/// Named-pipe IPC server that FsMonitor pushes usage records into,
/// and FsQuiz sends quiz completion events into.
/// </summary>
internal sealed class IpcServer
{
    private readonly ConcurrentQueue<UsageRecordIn> _usageBuffer = new();
    private int _todaySeconds;
    private int _weekSeconds;
    // Snapshot of the most recent foreground app/title we saw from FsMonitor.
    // FsMonitor reports these via UsageRecordIn (already populated by WinApi).
    // Used by HeartbeatLoop to fill current_app / window_title on the heartbeat.
    private string _lastApp = "";
    private string _lastTitle = "";
    private CancellationTokenSource? _cts;
    private Task? _acceptTask;
    private readonly List<Task> _clients = new();

    public void Start()
    {
        _cts = new CancellationTokenSource();
        _acceptTask = Task.Run(() => AcceptLoopAsync(_cts.Token));
        Logger.Info(ProcessNames.Agent, "IPC server started");
    }

    public void Stop()
    {
        _cts?.Cancel();
        try { _acceptTask?.Wait(TimeSpan.FromSeconds(2)); } catch { }
    }

    private async Task AcceptLoopAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                var pipe = new NamedPipeServerStream(
                    ProcessNames.WatchdogPipe,
                    PipeDirection.InOut,
                    NamedPipeServerStream.MaxAllowedServerInstances,
                    PipeTransmissionMode.Byte,
                    PipeOptions.Asynchronous);

                await pipe.WaitForConnectionAsync(ct);
                _ = Task.Run(() => HandleClientAsync(pipe, ct));
            }
            catch (OperationCanceledException) { break; }
            catch (Exception ex)
            {
                Logger.Warn(ProcessNames.Agent, $"Accept failed: {ex.Message}");
                await Task.Delay(500, ct);
            }
        }
    }

    private async Task HandleClientAsync(NamedPipeServerStream pipe, CancellationToken ct)
    {
        try
        {
            using var reader = new StreamReader(pipe, Encoding.UTF8);
            string? line;
            while ((line = await reader.ReadLineAsync(ct)) != null)
            {
                if (string.IsNullOrWhiteSpace(line)) continue;
                ProcessMessage(line);
            }
        }
        catch (OperationCanceledException) { }
        catch (Exception ex)
        {
            Logger.Warn(ProcessNames.Agent, $"Client handler error: {ex.Message}");
        }
        finally
        {
            pipe.Dispose();
        }
    }

    private void ProcessMessage(string json)
    {
        try
        {
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            if (!root.TryGetProperty("type", out var typeProp)) return;
            var type = typeProp.GetString();
            switch (type)
            {
                case "usage_record":
                    var rec = JsonSerializer.Deserialize<UsageRecordIn>(json);
                    if (rec != null) OnUsageRecord(rec);
                    break;
                case "ping":
                    // Respond handled by pipe being open
                    break;
            }
        }
        catch (Exception ex)
        {
            Logger.Warn(ProcessNames.Agent, $"Bad IPC message: {ex.Message}");
        }
    }

    private void OnUsageRecord(UsageRecordIn rec)
    {
        _usageBuffer.Enqueue(rec);
        _todaySeconds += rec.DurationSeconds;
        _weekSeconds += rec.DurationSeconds;
        // Remember the most recent foreground app+title so the next heartbeat
        // can report them. Empty/blank values overwrite as well — we want the
        // freshest signal FsMonitor has given us.
        if (!string.IsNullOrEmpty(rec.AppName)) _lastApp = rec.AppName;
        if (rec.WindowTitle != null) _lastTitle = rec.WindowTitle;
        if (_usageBuffer.Count >= 50)
        {
            FlushToBackend();
        }
    }

    private void FlushToBackend()
    {
        // Flush handled by HeartbeatLoop; here we just provide counts
    }

    public int GetTodayUsageSeconds() => _todaySeconds;
    public int GetWeekUsageSeconds() => _weekSeconds;
    public IReadOnlyCollection<UsageRecordIn> DrainBuffered() => _usageBuffer.ToArray();

    /// <summary>
    /// Returns (app, title) for the most recent foreground window observed via
    /// FsMonitor's IPC usage_record events. Returns ("", "") if FsMonitor hasn't
    /// pushed any records yet (e.g. service started before monitor).
    /// Caller should send empty strings (not null) to the backend.
    /// </summary>
    public (string app, string title) GetCurrentForeground() => (_lastApp, _lastTitle);

    public void NotifyWarning(string? message)
    {
        // Forward to tray / OS notification (handled by FsTray in P4)
        Logger.Info(ProcessNames.Agent, $"Notify: {message}");
    }
}
