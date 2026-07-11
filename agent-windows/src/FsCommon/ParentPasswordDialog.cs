namespace FsCommon;

/// <summary>
/// Modal password prompt with 30-second auto-close. Used by both FsTray
/// (for "退出 (家长)") and FsConfigUI (for the equivalent stop-service
/// button) so the dialog UX is identical in both places.
///
/// Extracted from FsTray/Program.cs in PR-D so the FsConfigUI side can
/// share the same look-and-feel and 30s timeout.
/// </summary>
public sealed class ParentPasswordDialog : Form
{
    private readonly TextBox _txt = new() { UseSystemPasswordChar = true, Dock = DockStyle.Fill };
    private readonly Button _ok = new() { Text = "确定", DialogResult = DialogResult.OK, Width = 90 };
    private readonly Button _cancel = new() { Text = "取消", DialogResult = DialogResult.Cancel, Width = 90 };
    private readonly System.Windows.Forms.Timer _autoClose = new() { Interval = 30_000 };

    public string EnteredPassword => _txt.Text;

    public ParentPasswordDialog()
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
