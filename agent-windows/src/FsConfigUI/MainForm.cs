using System.Net.Http.Json;
using FsCommon;

namespace FsConfigUI;

public sealed class MainForm : Form
{
    private readonly AgentConfig _cfg = AgentConfig.Load();

    private readonly TextBox _txtBackend = new() { Width = 380 };
    private readonly TextBox _txtDeviceName = new() { ReadOnly = true, Width = 380, BackColor = SystemColors.Control };
    private readonly TextBox _txtDeviceId = new() { ReadOnly = true, Width = 380, BackColor = SystemColors.Control };
    private readonly TextBox _txtPwd1 = new() { Width = 380, UseSystemPasswordChar = true };
    private readonly TextBox _txtPwd2 = new() { Width = 380, UseSystemPasswordChar = true };
    private readonly ProgressBar _strength = new() { Width = 380, Minimum = 0, Maximum = 4 };
    private readonly Label _lblStrength = new() { AutoSize = true };
    private readonly Label _lblStatus = new() { AutoSize = true, ForeColor = SystemColors.ControlText };
    private readonly Button _btnTest = new() { Text = "测试连接", Width = 110, Height = 32 };
    private readonly Button _btnSave = new() { Text = "保存", Width = 110, Height = 32 };
    private readonly Button _btnSaveStart = new() { Text = "保存并启动服务", Width = 140, Height = 32 };
    private readonly Button _btnCancel = new() { Text = "取消", Width = 110, Height = 32 };

    public MainForm()
    {
        Text = "FamilySafety 家长配置";
        FormBorderStyle = FormBorderStyle.FixedDialog;
        StartPosition = FormStartPosition.CenterScreen;
        MaximizeBox = false;
        MinimizeBox = false;
        ShowInTaskbar = true;
        ClientSize = new Size(540, 480);
        Font = new Font("Microsoft YaHei UI", 9F);

        var root = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 8,
            Padding = new Padding(16),
            AutoSize = false,
        };
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 28));   // title
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 64));   // backend
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 32));   // deviceName
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 32));   // deviceId
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 96));   // passwords
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 28));   // strength
        root.RowStyles.Add(new RowStyle(SizeType.Absolute, 28));   // status
        root.RowStyles.Add(new RowStyle(SizeType.Percent, 100));   // buttons

        var lblTitle = new Label
        {
            Text = "设置家长密码和后台地址",
            Font = new Font("Microsoft YaHei UI", 11F, FontStyle.Bold),
            AutoSize = true,
        };
        root.Controls.Add(lblTitle, 0, 0);

        root.Controls.Add(MakeField("后台地址 (例如 http://192.168.1.10:8000):", _txtBackend), 0, 1);
        root.Controls.Add(MakeField("设备名称:", _txtDeviceName), 0, 2);
        root.Controls.Add(MakeField("设备 ID:", _txtDeviceId), 0, 3);

        var pwdPanel = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 2,
        };
        pwdPanel.RowStyles.Add(new RowStyle(SizeType.Percent, 50));
        pwdPanel.RowStyles.Add(new RowStyle(SizeType.Percent, 50));
        pwdPanel.Controls.Add(MakeField("家长密码 (至少 8 位):", _txtPwd1), 0, 0);
        pwdPanel.Controls.Add(MakeField("再次输入:", _txtPwd2), 0, 1);
        root.Controls.Add(pwdPanel, 0, 4);

        var strengthPanel = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = false };
        strengthPanel.Controls.Add(_strength);
        strengthPanel.Controls.Add(_lblStrength);
        root.Controls.Add(strengthPanel, 0, 5);

        root.Controls.Add(_lblStatus, 0, 6);

        var btnPanel = new FlowLayoutPanel
        {
            Dock = DockStyle.Fill,
            FlowDirection = FlowDirection.RightToLeft,
            AutoSize = false,
        };
        btnPanel.Controls.Add(_btnCancel);
        btnPanel.Controls.Add(_btnSaveStart);
        btnPanel.Controls.Add(_btnSave);
        btnPanel.Controls.Add(_btnTest);
        root.Controls.Add(btnPanel, 0, 7);

        Controls.Add(root);

        _txtBackend.Text = _cfg.BackendUrl;
        _txtDeviceName.Text = _cfg.DeviceName;
        _txtDeviceId.Text = string.IsNullOrEmpty(_cfg.DeviceId) ? "(尚未注册)" : _cfg.DeviceId;

        _txtPwd1.TextChanged += (_, _) => UpdateStrength();
        _txtPwd2.TextChanged += (_, _) => UpdateStrength();

        _btnTest.Click += async (_, _) => await TestConnectionAsync();
        _btnSave.Click += (_, _) => Save(startService: false);
        _btnSaveStart.Click += (_, _) => Save(startService: true);
        _btnCancel.Click += (_, _) => Close();

        UpdateStrength();
        UpdateStatus(ParentAuth.IsSet() ? "已检测到家长密码,可继续修改。" : "尚未设置家长密码 — 首次配置请填写下方两栏。",
                     isError: false);
    }

    private static Control MakeField(string label, Control input)
    {
        var panel = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 2,
        };
        panel.RowStyles.Add(new RowStyle(SizeType.Absolute, 22));
        panel.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        var lbl = new Label { Text = label, AutoSize = true };
        input.Dock = DockStyle.Fill;
        panel.Controls.Add(lbl, 0, 0);
        panel.Controls.Add(input, 0, 1);
        return panel;
    }

    private void UpdateStrength()
    {
        var pwd = _txtPwd1.Text;
        var score = ScorePassword(pwd);
        _strength.Value = Math.Min(score, _strength.Maximum);
        _lblStrength.Text = score switch
        {
            <= 1 => "弱",
            2 => "一般",
            3 => "良好",
            _ => "强",
        };
    }

    private static int ScorePassword(string pwd)
    {
        if (string.IsNullOrEmpty(pwd)) return 0;
        int s = 0;
        if (pwd.Length >= 8) s++;
        if (pwd.Length >= 12) s++;
        if (pwd.Any(char.IsDigit) && pwd.Any(char.IsLetter)) s++;
        if (pwd.Any(c => !char.IsLetterOrDigit(c))) s++;
        return s;
    }

    private async Task TestConnectionAsync()
    {
        var url = (_txtBackend.Text ?? "").Trim();
        if (string.IsNullOrEmpty(url))
        {
            UpdateStatus("请填写后台地址后再测试。", isError: true);
            return;
        }
        _btnTest.Enabled = false;
        UpdateStatus("正在测试连接…", isError: false);
        try
        {
            using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };
            var resp = await http.GetAsync(url.TrimEnd('/') + "/health");
            if (resp.IsSuccessStatusCode)
                UpdateStatus($"连接成功 ({url})", isError: false);
            else
                UpdateStatus($"后端返回 HTTP {(int)resp.StatusCode}", isError: true);
        }
        catch (Exception ex)
        {
            UpdateStatus($"无法连接: {ex.Message}", isError: true);
        }
        finally
        {
            _btnTest.Enabled = true;
        }
    }

    private void Save(bool startService)
    {
        var url = (_txtBackend.Text ?? "").Trim();
        var pwd1 = _txtPwd1.Text ?? "";
        var pwd2 = _txtPwd2.Text ?? "";

        if (string.IsNullOrEmpty(url) || !Uri.TryCreate(url, UriKind.Absolute, out _))
        {
            MessageBox.Show(this, "请填写合法的后台地址 (含 http:// 或 https://)。",
                "校验失败", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            _txtBackend.Focus();
            return;
        }

        // Password required on first run; optional on subsequent edits.
        var passwordWanted = pwd1.Length > 0 || pwd2.Length > 0;
        if (passwordWanted)
        {
            if (pwd1.Length < 8)
            {
                MessageBox.Show(this, "家长密码至少 8 位。", "校验失败",
                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
                _txtPwd1.Focus();
                return;
            }
            if (pwd1 != pwd2)
            {
                MessageBox.Show(this, "两次输入的密码不一致。", "校验失败",
                    MessageBoxButtons.OK, MessageBoxIcon.Warning);
                _txtPwd2.Focus();
                return;
            }
        }
        else if (!ParentAuth.IsSet())
        {
            MessageBox.Show(this, "首次配置必须设置家长密码,否则服务无法启动。",
                "缺少密码", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            _txtPwd1.Focus();
            return;
        }

        try
        {
            _cfg.BackendUrl = url;
            _cfg.Save();

            if (passwordWanted)
            {
                ParentAuth.SetPassword(pwd1);
                TrySyncPasswordToCloud();
            }
        }
        catch (Exception ex)
        {
            MessageBox.Show(this, $"保存失败: {ex.Message}", "错误",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
            return;
        }

        if (startService)
        {
            TryStartService();
        }

        DialogResult = DialogResult.OK;
        Close();
    }

    private void TrySyncPasswordToCloud()
    {
        // Best-effort: only fires if the agent has already registered (apiKey set).
        // First-run cloudsync is impossible because we don't have a DeviceId yet.
        try
        {
            var cfg = AgentConfig.Load();
            if (string.IsNullOrEmpty(cfg.ApiKey) || string.IsNullOrEmpty(cfg.DeviceId))
            {
                UpdateStatus("密码已保存到本机。云端同步将在 FsAgent 首次注册后自动完成。",
                             isError: false);
                return;
            }
            var blob = ParentAuth.ExportForSync();
            if (blob == null) return;
            using var http = new HttpClient { BaseAddress = new Uri(cfg.BackendUrl), Timeout = TimeSpan.FromSeconds(5) };
            http.DefaultRequestHeaders.Authorization =
                new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", cfg.ApiKey);
            var resp = http.PostAsJsonAsync("/api/v1/agent/sync-parent-password",
                new
                {
                    hash = blob.HashBase64,
                    salt = blob.SaltBase64,
                    iterations = blob.Iterations,
                }).GetAwaiter().GetResult();
            UpdateStatus(resp.IsSuccessStatusCode
                ? "密码已保存,并已同步到云端。"
                : $"密码已保存,但云端同步失败 (HTTP {(int)resp.StatusCode})。",
                isError: !resp.IsSuccessStatusCode);
        }
        catch (Exception ex)
        {
            UpdateStatus($"密码已保存。云端同步失败: {ex.Message}", isError: true);
        }
    }

    private void TryStartService()
    {
        try
        {
            var psi = new System.Diagnostics.ProcessStartInfo
            {
                FileName = "sc.exe",
                Arguments = "start FamilySafety",
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
            UpdateStatus($"已保存,但启动服务失败: {ex.Message}", isError: true);
        }
    }

    private void UpdateStatus(string text, bool isError)
    {
        _lblStatus.Text = text;
        _lblStatus.ForeColor = isError ? Color.Firebrick : Color.SeaGreen;
    }
}