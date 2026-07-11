using FsCommon;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Hosting.WindowsServices;
using System.Diagnostics;

namespace FsWatchdogService;

/// <summary>
/// FamilySafety Watchdog Service.
///
/// Single binary, two modes:
///   1. No args → run as a real Windows Service (UseWindowsService). SCM
///      starts it on boot, auto-restarts on crash (within ~60s), and runs
///      it in Session 0 so a kid can't kill it from the desktop.
///   2. Subcommand args → run as a console CLI for admin tasks:
///         configure --backend-url &lt;url&gt;
///         set-password    (verify old → set new)
///         reset-password  (no verify, audit-logged)
///         status          (print config + child PIDs)
///      These return quickly and never block on the watchdog loop.
///
/// Child lifecycle owned by <see cref="Supervisor"/>:
///   - On start: launch FsTray → FsAgent → FsMonitor (staggered).
///   - Every 5s: check FsAgent heartbeat file; check FsMonitor + FsTray by
///     process name; relaunch any dead children.
///   - On stop: kill children, signal supervisor to exit, return within 200ms.
///
/// First-run gate:
///   - OnStart refuses to bring up children until ParentAuth.IsSet() is true.
///     We write EventLog 7000 with a clear hint and exit non-zero so SCM
///     reports the failure (and so the install script can react).
///
/// Install:
///   sc.exe create FamilySafety binPath= "C:\Program Files\FamilySafety\FsWatchdogService.exe" start= auto
///   sc.exe start FamilySafety
/// </summary>
internal static class Program
{
    public const string ServiceName = "FamilySafety";

    private static int Main(string[] args)
    {
        // CLI subcommands: no SCM involvement, no service plumbing.
        if (args.Length > 0 && !string.Equals(args[0], "--service", StringComparison.OrdinalIgnoreCase))
        {
            return Cli.Run(args);
        }

        Logger.Init(ProcessNames.Watchdog);

        // Refuse to start until the parent has set a password. We do this
        // before UseWindowsService so the failure is visible to installers
        // and SCM alike.
        if (!ParentAuth.IsSet())
        {
            Logger.Error(ProcessNames.Watchdog,
                "Parent password not configured. Run FsConfigUI.exe or " +
                "`FsWatchdogService.exe set-password` before starting the service.");
            WriteEventLog(EventLogEntryType.Error, EventIdStartRefused,
                "FamilySafety: parents.bin not found. Run FsConfigUI.exe to set the parent password.");
            return 2;
        }

        var builder = Host.CreateApplicationBuilder(args);
        builder.Services.AddHostedService<Supervisor>();
        builder.Services.AddWindowsService(options => options.ServiceName = ServiceName);

        var host = builder.Build();
        host.Run();
        return 0;
    }

    // EventID constants for the Application log.
    public const int EventIdStartRefused = 7001;
    public const int EventIdChildDied = 7002;
    public const int EventIdStopping = 7003;

    internal static void WriteEventLog(EventLogEntryType type, int id, string message)
    {
        try
        {
            if (!EventLog.SourceExists(ServiceName))
                EventLog.CreateEventSource(ServiceName, "Application");
            EventLog.WriteEntry(ServiceName, message, type, id);
        }
        catch
        {
            // EventLog unavailable (e.g. CI / unprivileged context). The file
            // logger has already captured the same message.
        }
    }
}