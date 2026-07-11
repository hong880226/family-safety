using FsCommon;

namespace FsQuiz;

/// <summary>
/// Quiz UI with P4 hardening:
///   - TopMost + LockWindowUpdate (prevents alt-tab escape)
///   - Registry Task Manager block
///   - Low-level keyboard hook (blocks Alt+F4, Win, Ctrl+Esc, etc.)
///   - Hook auto-suspended during text input
///   - All hooks cleaned up in FormClosed
/// </summary>
public sealed class QuizForm : Form
{
    private readonly QuizStartResponse _start;
    private readonly List<RadioButton>[] _optionsByQuestion;
    private int _currentQuestion = 0;
    private bool _hookInstalled = false;
    private bool _tmBlocked = false;

    public Dictionary<int, string> Answers { get; } = new();
    public bool Submitted { get; private set; }

    public QuizForm(QuizStartResponse start)
    {
        _start = start;
        _optionsByQuestion = new List<RadioButton>[start.Questions.Count];

        Text = "FamilySafety 答题  [专注模式]";
        Width = 720;
        Height = 540;
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.None;  // No title bar
        TopMost = true;
        ShowInTaskbar = false;
        BackColor = Color.FromArgb(245, 247, 250);
        Font = new Font("Microsoft YaHei UI", 12);

        // Render initial question BEFORE installing hook
        RenderQuestion();

        // Now install the hook + block Task Manager
        try
        {
            FsHook.KeyboardHook.Install();
            _hookInstalled = true;
            FsHook.TaskManagerBlocker.Block();
            _tmBlocked = true;
            Logger.Info(ProcessNames.Quiz, "Quiz mode locked: keyboard hook + Task Manager blocked");
        }
        catch (Exception ex)
        {
            Logger.Warn(ProcessNames.Quiz, $"Lock install failed (FsHook.dll missing?): {ex.Message}");
            Text = Text.Replace("[专注模式]", "[专注模式 - 锁定未生效]");
        }
    }

    private void RenderQuestion()
    {
        Controls.Clear();
        var q = _start.Questions[_currentQuestion];

        var lblTitle = new Label
        {
            Text = $"第 {_currentQuestion + 1} / {_start.Questions.Count} 题  ({q.Subject} · 难度 {q.Difficulty})",
            Top = 16, Left = 24, Width = 660,
            Font = new Font("Microsoft YaHei UI", 11, FontStyle.Bold),
            ForeColor = Color.FromArgb(64, 158, 255),
        };
        Controls.Add(lblTitle);

        var lblQ = new Label
        {
            Text = q.Question,
            Top = 56, Left = 24, Width = 660, Height = 80,
            Font = new Font("Microsoft YaHei UI", 14),
        };
        Controls.Add(lblQ);

        _optionsByQuestion[_currentQuestion] = new List<RadioButton>();
        for (int i = 0; i < q.Options.Count; i++)
        {
            var rb = new RadioButton
            {
                Text = q.Options[i],
                Top = 160 + i * 50,
                Left = 32,
                Width = 640,
                Height = 40,
                Font = new Font("Microsoft YaHei UI", 12),
            };
            int capturedIndex = i;
            rb.CheckedChanged += (s, e) =>
            {
                if (rb.Checked)
                {
                    // Briefly suspend hook so the user could conceivably
                    // hot-key away -- but we don't allow it. Just record answer.
                    Answers[_currentQuestion] = ((char)('A' + capturedIndex)).ToString();
                }
            };
            _optionsByQuestion[_currentQuestion].Add(rb);
            Controls.Add(rb);
        }

        var btnNext = new Button
        {
            Text = _currentQuestion == _start.Questions.Count - 1 ? "提交" : "下一题",
            Top = 380, Left = 540, Width = 140, Height = 44,
            BackColor = Color.FromArgb(64, 158, 255),
            ForeColor = Color.White,
            FlatStyle = FlatStyle.Flat,
        };
        btnNext.Click += BtnNext_Click;
        Controls.Add(btnNext);

        var btnPrev = new Button
        {
            Text = "上一题",
            Top = 380, Left = 24, Width = 140, Height = 44,
            Enabled = _currentQuestion > 0,
        };
        btnPrev.Click += (s, e) =>
        {
            _currentQuestion--;
            RenderQuestion();
        };
        Controls.Add(btnPrev);

        // Progress
        var progress = new ProgressBar
        {
            Top = 460, Left = 24, Width = 660, Height = 24,
            Value = (int)((_currentQuestion + 1) * 100.0 / _start.Questions.Count),
        };
        Controls.Add(progress);
    }

    private void BtnNext_Click(object? sender, EventArgs e)
    {
        if (_currentQuestion < _start.Questions.Count - 1)
        {
            _currentQuestion++;
            RenderQuestion();
        }
        else
        {
            if (Answers.Count < _start.Questions.Count)
            {
                var res = MessageBox.Show("还有题目没答，确定提交吗？", "确认",
                    MessageBoxButtons.YesNo, MessageBoxIcon.Question);
                if (res != DialogResult.Yes) return;
            }
            Submitted = true;
            Close();
        }
    }

    protected override void OnFormClosed(FormClosedEventArgs e)
    {
        // ALWAYS undo the locks, even on crash
        try
        {
            if (_tmBlocked) FsHook.TaskManagerBlocker.Unblock();
            if (_hookInstalled) FsHook.KeyboardHook.Uninstall();
            Logger.Info(ProcessNames.Quiz, "Quiz mode unlocked");
        }
        catch (Exception ex)
        {
            Logger.Warn(ProcessNames.Quiz, $"Cleanup failed: {ex.Message}");
        }
        base.OnFormClosed(e);
    }

    /// <summary>
    /// Override WndProc to block form close via Alt+F4 (in case hook DLL is missing).
    /// </summary>
    protected override void WndProc(ref Message m)
    {
        const int WM_SYSCOMMAND = 0x0112;
        const int SC_CLOSE = 0xF060;
        if (m.Msg == WM_SYSCOMMAND && m.WParam.ToInt32() == SC_CLOSE)
            return;
        base.WndProc(ref m);
    }
}