using FsCommon;

namespace FsTray;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        Logger.Init(ProcessNames.Tray);
        Application.SetHighDpiMode(HighDpiMode.SystemAware);

        // --notify-screenshot: pop a balloon and exit. Used by FsAgent just
        // before it captures the screen (PR-D screenshot flow).
        if (args.Length > 0 &&
            string.Equals(args[0], "--notify-screenshot", StringComparison.OrdinalIgnoreCase))
        {
            new TrayApp().ShowScreenshotNotification();
            return 0;
        }

        Application.Run(new TrayApp());
        return 0;
    }
}

public sealed class TrayApp : ApplicationContext
{
    private const string ServiceName = "FamilySafety";
    private const string AuthLogName = "tray-auth.log";

    private readonly NotifyIcon _tray;

    public TrayApp()
    {
        _tray = new NotifyIcon
        {
            Icon = SystemIcons.Shield,
            Visible = true,
            Text = "FamilySafety"
        };
        var menu = new ContextMenuStrip();
        menu.Items.Add("FamilySafety 家长控制", null, (s, e) => OpenDashboard());
        menu.Items.Add("打开家长配置面板", null, (s, e) => OpenConfigUI());
        menu.Items.Add("---");
        menu.Items.Add("重新注册设备", null, (s, e) => Reregister());
        menu.Items.Add("---");
        menu.Items.Add("退出 (家长)", null, (s, e) => RequestExitWithAuth());
        _tray.ContextMenuStrip = menu;
        _tray.DoubleClick += (s, e) => OpenDashboard();
        Logger.Info(ProcessNames.Tray, "Tray app running");
    }

    /// <summary>
    /// Pop a one-shot balloon telling the user "家长正在查看你的桌面".
    /// Invoked by FsAgent (PR-D) just before it captures the primary screen,
    /// so the child always sees a heads-up before the shutter fires.
    /// </summary>
    public void ShowScreenshotNotification()
    {
        using var balloon = new NotifyIcon
        {
            Icon = SystemIcons.Information,
            Visible = true,
            BalloonTipTitle = "FamilySafety",
            BalloonTipText = "家长正在查看你的桌面",
            BalloonTipIcon = ToolTipIcon.Info,
        };
        balloon.ShowBalloonTip(5000);
        // Give the balloon time to render before the host process exits.
        System.Threading.Thread.Sleep(2500);
        Logger.Info(ProcessNames.Tray, "Screenshot notification shown");
    }

    private void OpenDashboard()
    {
        var cfg = AgentConfig.Load();
        try
        {
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
            {
                FileName = cfg.BackendUrl,
                UseShellExecute = true
            });
        }
        catch (Exception ex)
        {
            Logger.Error(ProcessNames.Tray, "Failed to open dashboard", ex);
        }
    }

    private void OpenConfigUI()
    {
        try
        {
            var exe = Path.Combine(AppContext.BaseDirectory, "FsConfigUI.exe");
            if (!File.Exists(exe))
            {
                MessageBox.Show("找不到 FsConfigUI.exe,无法打开配置面板。",
                    "FamilySafety", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
            {
                FileName = exe,
                UseShellExecute = true,
                Verb = "runas", // request elevation
            });
        }
        catch (Exception ex)
        {
            Logger.Error(ProcessNames.Tray, "Failed to launch FsConfigUI", ex);
        }
    }

    private void Reregister()
    {
        var cfg = AgentConfig.Load();
        cfg.ApiKey = "";
        cfg.DeviceId = "";
        cfg.Save();
        MessageBox.Show("已清除 API Key。下次重启 FsAgent 时将自动重新注册。");
    }

    private void RequestExitWithAuth()
    {
        // Three lines a kid can't bypass: require the parent password BEFORE
        // we even attempt to talk to the watchdog. Auth failure just denies;
        // never exposes whether the service is running.
        //
        // PR-D: replaced the sc.exe-stop + UAC dance with a parent-password
        // authenticated message on the FsWatchdog_Ctrl_Pipe. Falls back to
        // the old sc.exe path only if the pipe is unreachable (e.g. service
        // not installed).
        if (!ParentAuth.IsSet())
        {
            AuditAuth("deny (no password configured)");
            MessageBox.Show("尚未配置家长密码,无法退出。请先打开\"家长配置面板\"完成设置。",
                "FamilySafety", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        using var dlg = new ParentPasswordDialog();
        var result = dlg.ShowDialog();
        if (result != DialogResult.OK)
        {
            AuditAuth("deny (dialog cancelled)");
            return;
        }

        if (!ParentAuth.Verify(dlg.EnteredPassword))
        {
            AuditAuth("deny (wrong password)");
            MessageBox.Show("密码错误,已拒绝退出。",
                "FamilySafety", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        AuditAuth("allow (correct password)");
        Logger.Info(ProcessNames.Tray, "Parent authenticated; requesting graceful stop");

        var ok = ServicePipeClient.SendGracefulStop(dlg.EnteredPassword);
        if (ok)
        {
            MessageBox.Show("已发送退出指令。FamilySafety 将在几秒内关闭所有守护进程。",
                "FamilySafety", MessageBoxButtons.OK, MessageBoxIcon.Information);
            ExitThread();
            return;
        }

        // Pipe unreachable — watchdog may not be running yet, or the user
        // is invoking this from a non-default install path. Fall back to
        // the legacy sc.exe + UAC path so the parent always has a way out.
        AuditAuth("pipe unreachable, falling back to sc.exe stop");
        try
        {
            var psi = new System.Diagnostics.ProcessStartInfo
            {
                FileName = "sc.exe",
                Arguments = $"stop {ServiceName}",
                UseShellExecute = true,
                Verb = "runas",
                CreateNoWindow = true,
                WindowStyle = System.Diagnostics.ProcessWindowStyle.Hidden,
            };
            using var p = System.Diagnostics.Process.Start(psi);
            p?.WaitForExit(5000);
        }
        catch (Exception ex)
        {
            AuditAuth($"stop failed: {ex.GetType().Name}: {ex.Message}");
            MessageBox.Show($"通过命名管道停止失败,sc.exe 也无法运行:{ex.Message}\n\n" +
                $"如果家长本人也无法退出,请在管理员 PowerShell 中运行:\n  sc.exe stop {ServiceName}",
                "FamilySafety", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }

        ExitThread();
    }

    private static void AuditAuth(string detail)
    {
        try
        {
            var dir = Path.Combine(AgentConfig.ConfigDir, "logs");
            Directory.CreateDirectory(dir);
            var line = $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} [tray-exit] {detail}{Environment.NewLine}";
            File.AppendAllText(Path.Combine(dir, AuthLogName), line, System.Text.Encoding.UTF8);
        }
        catch { /* ignore */ }
    }
}

internal static class AgentConfigExt
{
    public static string BackupUrl(this AgentConfig cfg) => cfg.BackendUrl;
}