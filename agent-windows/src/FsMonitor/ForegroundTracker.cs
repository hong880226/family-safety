using FsCommon;

namespace FsMonitor;

/// <summary>
/// Win32 helpers used by FsMonitor — wrapped here so the rest of the
/// codebase doesn't need System.Runtime.InteropServices imports.
/// </summary>
public static class WinApi
{
    public static (string App, string Title) GetForegroundInfo()
    {
        try
        {
            var hwnd = GetForegroundWindow();
            if (hwnd == IntPtr.Zero) return ("", "");
            var title = GetWindowText(hwnd);
            GetWindowThreadProcessId(hwnd, out uint pid);
            var proc = System.Diagnostics.Process.GetProcessById((int)pid);
            var appName = proc.ProcessName + ".exe";
            proc.Dispose();
            return (appName, title ?? "");
        }
        catch
        {
            return ("", "");
        }
    }

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);

    private static string? GetWindowText(IntPtr hWnd)
    {
        var sb = new System.Text.StringBuilder(512);
        GetWindowText(hWnd, sb, sb.Capacity);
        return sb.ToString();
    }

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
}

/// <summary>
/// Foreground window activity tracker. Polled by FsMonitor.Main once a
/// second; emits a UsageRecordIn whenever the active app or window title
/// changes. Maintains the open slice in memory so the caller can flush on
/// shutdown.
/// </summary>
internal sealed class ForegroundTracker
{
    private readonly AgentConfig _cfg;
    private readonly Action<UsageRecordIn> _emit;

    private string _lastApp = "";
    private string _lastTitle = "";
    private DateTime _lastStart = DateTime.UtcNow;

    public ForegroundTracker(AgentConfig cfg, Action<UsageRecordIn> emit)
    {
        _cfg = cfg ?? throw new ArgumentNullException(nameof(cfg));
        _emit = emit ?? throw new ArgumentNullException(nameof(emit));
    }

    /// <summary>
    /// Call once per main-loop tick. Detects app/title transitions and
    /// emits a record for the *previous* slice before resetting state.
    /// </summary>
    public void Tick()
    {
        var (app, title) = WinApi.GetForegroundInfo();
        if (app == _lastApp && title == _lastTitle) return;

        var now = DateTime.UtcNow;
        var dur = (int)(now - _lastStart).TotalSeconds;
        if (dur > 0 && !string.IsNullOrEmpty(_lastApp))
        {
            _emit(new UsageRecordIn
            {
                AppName = _lastApp,
                WindowTitle = _lastTitle,
                StartAt = _lastStart,
                EndAt = now,
                DurationSeconds = dur,
                IsOvertime = false,
            });
        }
        _lastApp = app;
        _lastTitle = title;
        _lastStart = now;
    }

    /// <summary>
    /// Flush whatever slice is currently open (call on shutdown).
    /// </summary>
    public void Flush()
    {
        var now = DateTime.UtcNow;
        var dur = (int)(now - _lastStart).TotalSeconds;
        if (dur > 0 && !string.IsNullOrEmpty(_lastApp))
        {
            _emit(new UsageRecordIn
            {
                AppName = _lastApp,
                WindowTitle = _lastTitle,
                StartAt = _lastStart,
                EndAt = now,
                DurationSeconds = dur,
                IsOvertime = false,
            });
        }
    }
}
