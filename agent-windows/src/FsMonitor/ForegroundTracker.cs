using FsCommon;
using System.Diagnostics;

namespace FsMonitor;

/// <summary>
/// ForegroundTracker: polls the active foreground window every second
/// and emits a UsageRecordIn whenever the app or window title changes.
/// Designed to be called from the FsMonitor main loop.
///
/// All Win32 access goes through WinApi.GetForegroundInfo().
/// </summary>
internal sealed class ForegroundTracker
{
    private readonly AgentConfig _cfg;
    private readonly Action<UsageRecordIn> _emit;

    private string _lastApp = "";
    private string _lastTitle = "";
    private DateTime _lastStart = DateTime.UtcNow;

    /// <param name="cfg">Loaded agent config (used for tagging records with family_id etc).</param>
    /// <param name="emit">Callback invoked for each completed (previous) usage slice.</param>
    public ForegroundTracker(AgentConfig cfg, Action<UsageRecordIn> emit)
    {
        _cfg = cfg ?? throw new ArgumentNullException(nameof(cfg));
        _emit = emit ?? throw new ArgumentNullException(nameof(emit));
    }

    /// <summary>
    /// Call once per main-loop tick. Detects app/title transitions and
    /// emits a record for the *previous* slice before resetting.
    /// </summary>
    public void Tick()
    {
        var (app, title) = WinApi.GetForegroundInfo();
        if (app == _lastApp && title == _lastTitle) return;

        var now = DateTime.UtcNow;
        var dur = (int)(now - _lastStart).TotalSeconds;
        if (dur > 0 && !string.IsNullOrEmpty(_lastApp))
        {
            // Overtime is decided by FsAgent/parent; v0.1 defaults to false.
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
    /// Flush whatever slice is currently open (called on shutdown).
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
