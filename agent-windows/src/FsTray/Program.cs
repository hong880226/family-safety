using FsCommon;

namespace FsTray;

/// <summary>
/// FsTray: system tray icon with quick actions.
/// P3: minimal. P4: rich menu + warning balloon.
/// </summary>
internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        Logger.Init(ProcessNames.Tray);
        Application.SetHighDpiMode(HighDpiMode.SystemAware);
        Application.Run(new TrayApp());
        return 0;
    }
}

public sealed class TrayApp : ApplicationContext
{
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
        menu.Items.Add("---");
        menu.Items.Add("重新注册设备", null, (s, e) => Reregister());
        menu.Items.Add("---");
        menu.Items.Add("退出 (家长)", null, (s, e) => ExitThread());
        _tray.ContextMenuStrip = menu;
        _tray.DoubleClick += (s, e) => OpenDashboard();
        Logger.Info(ProcessNames.Tray, "Tray app running");
    }

    private void OpenDashboard()
    {
        var cfg = AgentConfig.Load();
        try
        {
            System.Diagnostics.Process.Start(new System.Diagnostics.ProcessStartInfo
            {
                FileName = cfg.BackupUrl(),
                UseShellExecute = true
            });
        }
        catch (Exception ex)
        {
            Logger.Error(ProcessNames.Tray, "Failed to open dashboard", ex);
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
}

internal static class AgentConfigExt
{
    public static string BackupUrl(this AgentConfig cfg)
    {
        return cfg.BackendUrl;
    }
}
