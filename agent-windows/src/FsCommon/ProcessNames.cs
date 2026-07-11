namespace FsCommon;

/// <summary>
/// Constants used across all FamilySafety processes.
/// </summary>
public static class ProcessNames
{
    public const string Watchdog = "FsWatchdog";
    public const string Agent = "FsAgent";
    public const string Monitor = "FsMonitor";
    public const string Quiz = "FsQuiz";
    public const string Tray = "FsTray";

    /// <summary>
    /// Name of the named mutex held by the watchdog (single instance).
    /// </summary>
    public const string WatchdogMutex = "Global\\FsWatchdog_SingleInstance";

    /// <summary>
    /// Named pipe for watchdog IPC (heartbeat, restart requests).
    /// </summary>
    public const string WatchdogPipe = "FsWatchdog_Pipe";

    /// <summary>
    /// Shared memory segment for monitor->agent IPC.
    /// </summary>
    public const string SharedMemName = "FsShared_State";
}
