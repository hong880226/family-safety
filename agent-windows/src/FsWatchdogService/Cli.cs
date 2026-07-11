using FsCommon;
using System.Diagnostics;

namespace FsWatchdogService;

/// <summary>
/// Admin-facing console subcommands. These run synchronously and return a
/// process exit code; they never enter the service loop.
/// </summary>
internal static class Cli
{
    public static int Run(string[] args)
    {
        var cmd = args[0].ToLowerInvariant();
        Logger.Init(ProcessNames.Watchdog);

        try
        {
            switch (cmd)
            {
                case "configure":
                    return Configure(args);
                case "set-password":
                    return SetPasswordInteractive(verifyExisting: true);
                case "reset-password":
                    return SetPasswordInteractive(verifyExisting: false);
                case "status":
                    return Status();
                default:
                    Console.Error.WriteLine($"Unknown command: {cmd}");
                    PrintUsage();
                    return 64; // EX_USAGE
            }
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"error: {ex.Message}");
            return 1;
        }
    }

    private static int Configure(string[] args)
    {
        // configure [--backend-url URL]
        string? newUrl = null;
        for (int i = 1; i < args.Length; i++)
        {
            if (args[i] == "--backend-url" && i + 1 < args.Length)
                newUrl = args[++i];
        }

        var cfg = AgentConfig.Load();
        if (!string.IsNullOrWhiteSpace(newUrl))
        {
            cfg.BackendUrl = newUrl;
            cfg.Save();
            Console.WriteLine($"backendUrl set to: {newUrl}");
        }
        else
        {
            Console.WriteLine($"backendUrl (unchanged): {cfg.BackendUrl}");
        }

        Console.WriteLine($"deviceId:        {cfg.DeviceId}");
        Console.WriteLine($"deviceName:      {cfg.DeviceName}");
        Console.WriteLine($"apiKey set:      {!string.IsNullOrEmpty(cfg.ApiKey)}");
        return 0;
    }

    private static int SetPasswordInteractive(bool verifyExisting)
    {
        if (verifyExisting && ParentAuth.IsSet())
        {
            var old = PromptSecret("Current parent password: ");
            if (!ParentAuth.Verify(old))
            {
                Console.Error.WriteLine("Current password incorrect.");
                return 2;
            }
        }

        var pwd1 = PromptSecret("New parent password (min 8 chars): ");
        if (pwd1.Length < 8)
        {
            Console.Error.WriteLine("Password must be at least 8 characters.");
            return 2;
        }
        var pwd2 = PromptSecret("Confirm new password: ");
        if (pwd1 != pwd2)
        {
            Console.Error.WriteLine("Passwords do not match.");
            return 2;
        }

        ParentAuth.SetPassword(pwd1);
        Console.WriteLine(verifyExisting
            ? "Password updated."
            : "Password reset (no prior verification).");
        return 0;
    }

    private static int Status()
    {
        var cfg = AgentConfig.Load();
        Console.WriteLine("FamilySafety status");
        Console.WriteLine($"  backendUrl:   {cfg.BackendUrl}");
        Console.WriteLine($"  deviceId:     {cfg.DeviceId}");
        Console.WriteLine($"  deviceName:   {cfg.DeviceName}");
        Console.WriteLine($"  apiKey set:   {!string.IsNullOrEmpty(cfg.ApiKey)}");
        Console.WriteLine($"  parent pwd:   {(ParentAuth.IsSet() ? "set" : "NOT SET")}");

        foreach (var name in new[] { ProcessNames.Agent, ProcessNames.Monitor, ProcessNames.Tray })
        {
            try
            {
                var procs = Process.GetProcessesByName(name);
                if (procs.Length == 0)
                    Console.WriteLine($"  {name,-10}: not running");
                else
                    Console.WriteLine($"  {name,-10}: running (pid {procs[0].Id})");
            }
            catch (Exception ex)
            {
                Console.WriteLine($"  {name,-10}: error {ex.Message}");
            }
        }

        var svc = ServiceControllerSafe.Get();
        Console.WriteLine($"  service:      {(svc ?? "not installed")}");
        return 0;
    }

    private static string PromptSecret(string prompt)
    {
        Console.Write(prompt);
        var sb = new System.Text.StringBuilder();
        while (true)
        {
            var key = Console.ReadKey(intercept: true);
            if (key.Key == ConsoleKey.Enter) break;
            if (key.Key == ConsoleKey.Backspace && sb.Length > 0)
            {
                sb.Length--;
                Console.Write("\b \b");
                continue;
            }
            if (!char.IsControl(key.KeyChar))
            {
                sb.Append(key.KeyChar);
                Console.Write('*');
            }
        }
        Console.WriteLine();
        return sb.ToString();
    }

    private static void PrintUsage()
    {
        Console.Error.WriteLine("Usage:");
        Console.Error.WriteLine("  FsWatchdogService.exe                                  (run as Windows Service)");
        Console.Error.WriteLine("  FsWatchdogService.exe configure [--backend-url URL]");
        Console.Error.WriteLine("  FsWatchdogService.exe set-password     (verify existing, then change)");
        Console.Error.WriteLine("  FsWatchdogService.exe reset-password   (no verify, audit-logged)");
        Console.Error.WriteLine("  FsWatchdogService.exe status");
    }
}

internal static class ServiceControllerSafe
{
    public static string? Get()
    {
        try
        {
            var sc = new ProcessStartInfo
            {
                FileName = "sc.exe",
                Arguments = $"query {Program.ServiceName}",
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true,
            };
            using var p = Process.Start(sc);
            if (p == null) return null;
            var stdout = p.StandardOutput.ReadToEnd();
            p.WaitForExit(2000);
            return stdout.Contains("RUNNING") ? $"{Program.ServiceName} (RUNNING)"
                 : stdout.Contains("STOPPED") ? $"{Program.ServiceName} (STOPPED)"
                 : stdout.Contains("does not exist") ? null
                 : $"{Program.ServiceName} (?)";
        }
        catch
        {
            return null;
        }
    }
}