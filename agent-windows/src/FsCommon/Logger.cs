using System.Text;

namespace FsCommon;

/// <summary>
/// Simple file + console logger. Writes to %ProgramData%\FamilySafety\logs\{name}.log
/// </summary>
public static class Logger
{
    private static readonly object _lock = new();
    private static string? _logDir;

    public static void Init(string name)
    {
        _logDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
            "FamilySafety", "logs"
        );
        Directory.CreateDirectory(_logDir!);
    }

    public static void Info(string source, string msg)
    {
        Write("INFO", source, msg);
        Console.WriteLine($"[{source}] {msg}");
    }

    public static void Warn(string source, string msg)
    {
        Write("WARN", source, msg);
        Console.Error.WriteLine($"[{source}] WARN: {msg}");
    }

    public static void Error(string source, string msg, Exception? ex = null)
    {
        var full = ex == null ? msg : $"{msg} :: {ex.GetType().Name}: {ex.Message}";
        Write("ERROR", source, full);
        Console.Error.WriteLine($"[{source}] ERROR: {full}");
    }

    private static void Write(string level, string source, string msg)
    {
        if (_logDir == null) return;
        try
        {
            lock (_lock)
            {
                var file = Path.Combine(_logDir, $"{source}.log");
                File.AppendAllText(file,
                    $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} [{level}] {msg}{Environment.NewLine}",
                    Encoding.UTF8);
            }
        }
        catch
        {
            // swallow - logger should not crash
        }
    }
}
