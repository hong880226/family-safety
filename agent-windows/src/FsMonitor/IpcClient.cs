using FsCommon;
using System.IO.Pipes;
using System.Text;
using System.Text.Json;

namespace FsMonitor;

/// <summary>
/// Client side of the FsAgent IPC pipe. Reconnects automatically.
/// </summary>
public sealed class IpcClient : IDisposable
{
    private NamedPipeClientStream? _pipe;
    private StreamWriter? _writer;
    private readonly object _lock = new();

    public bool Connected => _pipe?.IsConnected == true;

    public void Connect()
    {
        try
        {
            lock (_lock)
            {
                _pipe?.Dispose();
                _pipe = new NamedPipeClientStream(".", ProcessNames.WatchdogPipe,
                    PipeDirection.Out, PipeOptions.Asynchronous);
                _pipe.Connect(2000);
                _writer = new StreamWriter(_pipe, new UTF8Encoding(false));
                _writer.AutoFlush = true;
                Logger.Info(ProcessNames.Monitor, "IPC connected to FsAgent");
            }
        }
        catch
        {
            _pipe?.Dispose();
            _pipe = null;
        }
    }

    public void SendUsage(UsageRecordIn rec)
    {
        if (!Connected) Connect();
        if (!Connected) return;
        try
        {
            lock (_lock)
            {
                var env = new
                {
                    type = "usage_record",
                    payload = rec
                };
                var json = JsonSerializer.Serialize(env);
                _writer!.WriteLine(json);
            }
        }
        catch (Exception ex)
        {
            Logger.Warn(ProcessNames.Monitor, $"SendUsage failed: {ex.Message}");
            Connect();
        }
    }

    public void Dispose()
    {
        lock (_lock)
        {
            _writer?.Dispose();
            _pipe?.Dispose();
        }
    }
}
