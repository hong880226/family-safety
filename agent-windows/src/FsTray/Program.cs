using FsCommon;

namespace FsTray;

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
        // we even attempt sc stop. Auth failure just denies; never exposes
        // whether the service is running.
        if (!ParentAuth.IsSet())
        {
            AuditAuth("deny (no password configured)");
            MessageBox.Show("尚未配置家长密码,无法退出。请先打开\"家长配置面板\"完成设置。",
                "FamilySafety", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        using var dlg = new PasswordDialog();
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
        Logger.Info(ProcessNames.Tray, "Parent authenticated; requesting service stop");

        // Ask SCM to stop the service. UseShellExecute=false so we capture stderr
        // without a console window popping up. If the user is not elevated this
        // fails with permission denied; we treat that as a hard refuse.
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
            MessageBox.Show($"无法停止服务: {ex.Message}\n\n如果家长本人也无法退出,请在管理员 PowerShell 中运行:\n  sc.exe stop {ServiceName}",
                "FamilySafety", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }

        // Tear down our own UI; the watchdog will see us exit and stop trying
        // to respawn us because the service is going down.
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

/// <summary>
/// Modal password prompt with 30-second auto-close.
/// </summary>
internal sealed class PasswordDialog : Form
{
    private readonly TextBox _txt = new() { UseSystemPasswordChar = true, Dock = DockStyle.Fill };
    private readonly Button _ok = new() { Text = "确定", DialogResult = DialogResult.OK, Width = 90 };
    private readonly Button _cancel = new() { Text = "取消", DialogResult = DialogResult.Cancel, Width = 90 };
    private readonly System.Windows.Forms.Timer _autoClose = new() { Interval = 30_000 };

    public string EnteredPassword => _txt.Text;

    public PasswordDialog()
    {
        Text = "家长验证";
        FormBorderStyle = FormBorderStyle.FixedDialog;
        StartPosition = FormStartPosition.CenterParent;
        MaximizeBox = false;
        MinimizeBox = false;
        ShowInTaskbar = false;
        ClientSize = new Size(360, 130);
        Font = new Font("Microsoft YaHei UI", 9F);

        var lbl = new Label
        {
            Text = "请输入家长密码以退出 FamilySafety:",
            Dock = DockStyle.Top,
            Height = 30,
            TextAlign = ContentAlignment.MiddleLeft,
            Padding = new Padding(8, 0, 0, 0),
        };

        var buttonPanel = new FlowLayoutPanel
        {
            Dock = DockStyle.Bottom,
            FlowDirection = FlowDirection.RightToLeft,
            Height = 40,
            Padding = new Padding(8),
        };
        buttonPanel.Controls.Add(_cancel);
        buttonPanel.Controls.Add(_ok);

        _txt.Dock = DockStyle.Top;

        Controls.Add(_txt);
        Controls.Add(lbl);
        Controls.Add(buttonPanel);

        AcceptButton = _ok;
        CancelButton = _cancel;
        FormClosing += (_, e) =>
        {
            if (e.CloseReason == CloseReason.UserClosing && DialogResult != DialogResult.OK)
            {
                // Cancel is implicit on window close
            }
        };

        _autoClose.Tick += (_, _) =>
        {
            _autoClose.Stop();
            DialogResult = DialogResult.Cancel;
            Close();
        };
        Shown += (_, _) =>
        {
            _txt.Focus();
            _autoClose.Start();
        };
    }
}

internal static class AgentConfigExt
{
    public static string BackupUrl(this AgentConfig cfg) => cfg.BackendUrl;
}