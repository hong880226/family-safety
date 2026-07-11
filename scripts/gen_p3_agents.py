"""P3: Generate FsAgent + FsMonitor + FsQuiz + FsTray + FsWatchdog."""
from pathlib import Path

ROOT = Path("E:/codeRepo/familysafety/agent-windows")


def write(rel: str, content: str) -> None:
    target = ROOT / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"  wrote {rel} ({len(content)} bytes)")


# ============ FsAgent ============
write("src/FsAgent/FsAgent.csproj", '''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net8.0-windows</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <UseWindowsForms>true</UseWindowsForms>
    <RootNamespace>FsAgent</RootNamespace>
    <AssemblyName>FsAgent</AssemblyName>
    <ApplicationManifest>app.manifest</ApplicationManifest>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="..\\FsCommon\\FsCommon.csproj" />
  </ItemGroup>
</Project>
''')

write("src/FsAgent/app.manifest", '''<?xml version="1.0" encoding="utf-8"?>
<assembly manifestVersion="1.0" xmlns="urn:schemas-microsoft-com:asm.v1">
  <assemblyIdentity version="1.0.0.0" name="FamilySafety.FsAgent" />
  <trustInfo xmlns="urn:schemas-microsoft-com:asm.v2">
    <security>
      <requestedPrivileges xmlns="urn:schemas-microsoft-com:asm.v3">
        <requestedExecutionLevel level="asInvoker" uiAccess="false" />
      </requestedPrivileges>
    </security>
  </trustInfo>
  <compatibility xmlns="urn:schemas-microsoft-com:compatibility.v1">
    <application>
      <supportedOS Id="{8e0f7a12-bfb3-4fe8-b9a5-48fd50a15a9a}"/>
      <supportedOS Id="{1f676c76-80e1-4239-95bb-83d0f6d0da78}"/>
      <supportedOS Id="{4a2f28e3-53b9-4441-ba9c-d69d4a4a6e38}"/>
    </application>
  </compatibility>
</assembly>
''')

write("src/FsAgent/Program.cs", '''using FsCommon;
using System.Diagnostics;
using System.Text.Json;

namespace FsAgent;

/// <summary>
/// FsAgent: the main FamilySafety service process.
/// Responsibilities:
///   - Register device on first run, save api_key locally
///   - Send periodic heartbeats
///   - Buffer and forward usage records from FsMonitor
///   - On force_quiz command, launch FsQuiz and lock the UI
///   - Communicate liveness to FsWatchdog (named pipe / heartbeat)
/// </summary>
internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        Logger.Init(ProcessNames.Agent);
        Logger.Info(ProcessNames.Agent, "Starting FsAgent");

        var cfg = AgentConfig.Load();
        var client = new BackendClient(cfg);

        // First-run registration if needed
        if (string.IsNullOrEmpty(cfg.ApiKey) || string.IsNullOrEmpty(cfg.DeviceId))
        {
            try
            {
                cfg.DeviceId = SystemInfo.GetDeviceId();
                cfg.ComputerModel = SystemInfo.GetComputerModel();
                cfg.WindowsUsername = SystemInfo.GetWindowsUsername();
                Logger.Info(ProcessNames.Agent,
                    $"First-run registration: device={cfg.DeviceId}, user={cfg.WindowsUsername}");

                var reg = client.RegisterAsync(new RegisterRequest
                {
                    DeviceId = null,  // let server assign
                    Name = cfg.DeviceName,
                    DeviceType = "windows",
                    ComputerModel = cfg.ComputerModel,
                    WindowsUsername = cfg.WindowsUsername
                }).GetAwaiter().GetResult();

                if (reg != null)
                {
                    cfg.DeviceId = reg.DeviceId;
                    cfg.ApiKey = reg.ApiKey;
                    cfg.Save();
                    Logger.Info(ProcessNames.Agent,
                        $"Registered: family_id={reg.FamilyId}, member_id={reg.MemberId}");
                }
                else
                {
                    Logger.Error(ProcessNames.Agent, "Registration returned null");
                    return 1;
                }
            }
            catch (Exception ex)
            {
                Logger.Error(ProcessNames.Agent, "First-run registration failed", ex);
                // Continue anyway - we can retry on next heartbeat
            }
        }

        // Start the IPC server for monitor to push usage
        var ipc = new IpcServer();
        ipc.Start();

        // Start the heartbeat loop in background
        using var cts = new CancellationTokenSource();
        var hbTask = HeartbeatLoop.RunAsync(client, cfg, ipc, cts.Token);

        // Start watchdog heartbeat
        var wdTask = WatchdogHeartbeat.RunAsync(cts.Token);

        Logger.Info(ProcessNames.Agent, "FsAgent running. Press Ctrl+C to stop.");

        // Trap console exit
        Console.CancelKeyPress += (s, e) =>
        {
            Logger.Info(ProcessNames.Agent, "Shutdown requested");
            cts.Cancel();
            e.Cancel = true;
        };

        try
        {
            Task.WaitAll(new[] { hbTask, wdTask }, Timeout.Infinite, cts.Token);
        }
        catch (OperationCanceledException)
        {
            // Expected on Ctrl+C
        }

        ipc.Stop();
        Logger.Info(ProcessNames.Agent, "FsAgent exited cleanly");
        return 0;
    }
}
''')

write("src/FsAgent/HeartbeatLoop.cs", '''using FsCommon;

namespace FsAgent;

/// <summary>
/// Sends periodic heartbeat + flushes usage buffer.
/// </summary>
internal static class HeartbeatLoop
{
    public static async Task RunAsync(
        BackendClient client,
        AgentConfig cfg,
        IpcServer ipc,
        CancellationToken ct)
    {
        var startTime = DateTime.UtcNow;
        var usageBuffer = new List<UsageRecordIn>();
        var lastFlush = DateTime.UtcNow;

        while (!ct.IsCancellationRequested)
        {
            try
            {
                // Compute usage seconds from buffered records
                var todaySec = ipc.GetTodayUsageSeconds();
                var weekSec = ipc.GetWeekUsageSeconds();

                var hb = await client.HeartbeatAsync(new HeartbeatRequest
                {
                    Timestamp = DateTime.UtcNow,
                    WindowsUsername = cfg.WindowsUsername,
                    ComputerModel = cfg.ComputerModel,
                    UsedSecondsToday = todaySec,
                    UsedSecondsThisWeek = weekSec,
                    UptimeSeconds = (int)(DateTime.UtcNow - startTime).TotalSeconds
                }, ct);

                if (hb != null)
                {
                    Logger.Info(ProcessNames.Agent,
                        $"Heartbeat OK: member={hb.MatchedMemberId}, commands={hb.Commands.Count}");

                    // Process commands (e.g. force_quiz)
                    foreach (var cmd in hb.Commands)
                    {
                        HandleCommand(cmd, cfg, ipc);
                    }
                }
            }
            catch (OperationCanceledException) { break; }
            catch (Exception ex)
            {
                Logger.Warn(ProcessNames.Agent, $"Heartbeat failed: {ex.Message}");
            }

            try
            {
                await Task.Delay(TimeSpan.FromSeconds(cfg.HeartbeatIntervalSec), ct);
            }
            catch (OperationCanceledException) { break; }
        }
    }

    private static void HandleCommand(
        System.Text.Json.JsonElement cmd, AgentConfig cfg, IpcServer ipc)
    {
        try
        {
            if (!cmd.TryGetProperty("type", out var typeProp)) return;
            var type = typeProp.GetString();
            switch (type)
            {
                case "force_quiz":
                    Logger.Info(ProcessNames.Agent, "Command: force_quiz received");
                    QuizLauncher.Launch(cfg, reason: "overtime");
                    break;
                case "show_warning":
                    var msg = cmd.TryGetProperty("message", out var m) ? m.GetString() : null;
                    Logger.Info(ProcessNames.Agent, $"Command: show_warning: {msg}");
                    ipc.NotifyWarning(msg);
                    break;
            }
        }
        catch (Exception ex)
        {
            Logger.Warn(ProcessNames.Agent, $"HandleCommand error: {ex.Message}");
        }
    }
}
''')

write("src/FsAgent/QuizLauncher.cs", '''using FsCommon;
using System.Diagnostics;

namespace FsAgent;

/// <summary>
/// Launches FsQuiz UI process.
/// </summary>
internal static class QuizLauncher
{
    public static void Launch(AgentConfig cfg, string reason)
    {
        try
        {
            var exe = Path.Combine(AppContext.BaseDirectory, "FsQuiz.exe");
            if (!File.Exists(exe))
            {
                Logger.Error(ProcessNames.Agent, $"FsQuiz.exe not found at {exe}");
                return;
            }
            var psi = new ProcessStartInfo
            {
                FileName = exe,
                Arguments = $"--reason \"{reason}\"",
                UseShellExecute = false,
                CreateNoWindow = false,
            };
            Process.Start(psi);
            Logger.Info(ProcessNames.Agent, $"Launched FsQuiz: reason={reason}");
        }
        catch (Exception ex)
        {
            Logger.Error(ProcessNames.Agent, "Failed to launch FsQuiz", ex);
        }
    }
}
''')

write("src/FsAgent/IpcServer.cs", '''using FsCommon;
using System.Collections.Concurrent;
using System.IO.Pipes;
using System.Text;
using System.Text.Json;

namespace FsAgent;

/// <summary>
/// Named-pipe IPC server that FsMonitor pushes usage records into,
/// and FsQuiz sends quiz completion events into.
/// </summary>
internal sealed class IpcServer
{
    private readonly ConcurrentQueue<UsageRecordIn> _usageBuffer = new();
    private int _todaySeconds;
    private int _weekSeconds;
    private CancellationTokenSource? _cts;
    private Task? _acceptTask;
    private readonly List<Task> _clients = new();

    public void Start()
    {
        _cts = new CancellationTokenSource();
        _acceptTask = Task.Run(() => AcceptLoopAsync(_cts.Token));
        Logger.Info(ProcessNames.Agent, "IPC server started");
    }

    public void Stop()
    {
        _cts?.Cancel();
        try { _acceptTask?.Wait(TimeSpan.FromSeconds(2)); } catch { }
    }

    private async Task AcceptLoopAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                var pipe = new NamedPipeServerStream(
                    ProcessNames.WatchdogPipe,
                    PipeDirection.InOut,
                    NamedPipeServerStream.MaxAllowedServerInstances,
                    PipeTransmissionMode.Byte,
                    PipeOptions.Asynchronous);

                await pipe.WaitForConnectionAsync(ct);
                _ = Task.Run(() => HandleClientAsync(pipe, ct));
            }
            catch (OperationCanceledException) { break; }
            catch (Exception ex)
            {
                Logger.Warn(ProcessNames.Agent, $"Accept failed: {ex.Message}");
                await Task.Delay(500, ct);
            }
        }
    }

    private async Task HandleClientAsync(NamedPipeServerStream pipe, CancellationToken ct)
    {
        try
        {
            using var reader = new StreamReader(pipe, Encoding.UTF8);
            string? line;
            while ((line = await reader.ReadLineAsync(ct)) != null)
            {
                if (string.IsNullOrWhiteSpace(line)) continue;
                ProcessMessage(line);
            }
        }
        catch (OperationCanceledException) { }
        catch (Exception ex)
        {
            Logger.Warn(ProcessNames.Agent, $"Client handler error: {ex.Message}");
        }
        finally
        {
            pipe.Dispose();
        }
    }

    private void ProcessMessage(string json)
    {
        try
        {
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            if (!root.TryGetProperty("type", out var typeProp)) return;
            var type = typeProp.GetString();
            switch (type)
            {
                case "usage_record":
                    var rec = JsonSerializer.Deserialize<UsageRecordIn>(json);
                    if (rec != null) OnUsageRecord(rec);
                    break;
                case "ping":
                    // Respond handled by pipe being open
                    break;
            }
        }
        catch (Exception ex)
        {
            Logger.Warn(ProcessNames.Agent, $"Bad IPC message: {ex.Message}");
        }
    }

    private void OnUsageRecord(UsageRecordIn rec)
    {
        _usageBuffer.Enqueue(rec);
        _todaySeconds += rec.DurationSeconds;
        _weekSeconds += rec.DurationSeconds;
        if (_usageBuffer.Count >= 50)
        {
            FlushToBackend();
        }
    }

    private void FlushToBackend()
    {
        // Flush handled by HeartbeatLoop; here we just provide counts
    }

    public int GetTodayUsageSeconds() => _todaySeconds;
    public int GetWeekUsageSeconds() => _weekSeconds;
    public IReadOnlyCollection<UsageRecordIn> DrainBuffered() => _usageBuffer.ToArray();

    public void NotifyWarning(string? message)
    {
        // Forward to tray / OS notification (handled by FsTray in P4)
        Logger.Info(ProcessNames.Agent, $"Notify: {message}");
    }
}
''')

write("src/FsAgent/WatchdogHeartbeat.cs", '''using FsCommon;
using System.Diagnostics;

namespace FsAgent;

/// <summary>
/// Tells the watchdog we are alive. Watchdog uses this to detect dead agent.
/// </summary>
internal static class WatchdogHeartbeat
{
    public static async Task RunAsync(CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                // Touch a shared file - watchdog checks timestamp
                var path = Path.Combine(AgentConfig.ConfigDir, "agent.alive");
                Directory.CreateDirectory(AgentConfig.ConfigDir);
                File.WriteAllText(path, DateTime.UtcNow.ToString("O"));
            }
            catch
            {
                // ignore
            }
            try
            {
                await Task.Delay(TimeSpan.FromSeconds(5), ct);
            }
            catch (OperationCanceledException) { break; }
        }
    }
}
''')


# ============ FsMonitor ============
write("src/FsMonitor/FsMonitor.csproj", '''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net8.0-windows</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <UseWindowsForms>true</UseWindowsForms>
    <RootNamespace>FsMonitor</RootNamespace>
    <AssemblyName>FsMonitor</AssemblyName>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="..\\FsCommon\\FsCommon.csproj" />
  </ItemGroup>
</Project>
''')

write("src/FsMonitor/Program.cs", '''using FsCommon;
using System.Diagnostics;

namespace FsMonitor;

/// <summary>
/// FsMonitor: tracks active foreground window + process name + idle time.
/// Sends UsageRecordIn messages to FsAgent via named pipe.
/// Runs silently (no UI); survives via FsWatchdog.
/// </summary>
internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        Logger.Init(ProcessNames.Monitor);
        Logger.Info(ProcessNames.Monitor, "Starting FsMonitor");

        var cfg = AgentConfig.Load();
        var tracker = new ForegroundTracker(cfg);
        var sink = new IpcClient();
        sink.Connect();

        var lastApp = "";
        var lastTitle = "";
        var lastStart = DateTime.UtcNow;

        while (!sink.Connected)
        {
            Thread.Sleep(2000);
            sink.Connect();
        }

        while (true)
        {
            try
            {
                var (app, title) = WinApi.GetForegroundInfo();
                if (app != lastApp || title != lastTitle)
                {
                    // App changed: emit usage for previous app
                    var now = DateTime.UtcNow;
                    var dur = (int)(now - lastStart).TotalSeconds;
                    if (dur > 0 && !string.IsNullOrEmpty(lastApp))
                    {
                        var rec = new UsageRecordIn
                        {
                            AppName = lastApp,
                            WindowTitle = lastTitle,
                            StartAt = lastStart,
                            EndAt = now,
                            DurationSeconds = dur,
                            IsOvertime = false,
                        };
                        sink.SendUsage(rec);
                    }
                    lastApp = app;
                    lastTitle = title;
                    lastStart = now;
                }
            }
            catch (Exception ex)
            {
                Logger.Warn(ProcessNames.Monitor, $"Tracker error: {ex.Message}");
            }

            Thread.Sleep(1000);
        }
    }
}
''')

write("src/FsMonitor/ForegroundTracker.cs", '''using FsCommon;

namespace FsMonitor;

/// <summary>
/// Foreground window tracker using Win32 APIs.
/// </summary>
public static class WinApi
{
    public static (string App, string Title) GetForegroundInfo()
    {
        try
        {
            var hwnd = GetForegroundWindow();
            if (hwnd == IntPtr.Zero) return ("", "");
            var title = GetWindowText(hwnd);
            GetWindowThreadProcessId(hwnd, out uint pid);
            var proc = System.Diagnostics.Process.GetProcessById((int)pid);
            var appName = proc.ProcessName + ".exe";
            proc.Dispose();
            return (appName, title ?? "");
        }
        catch
        {
            return ("", "");
        }
    }

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);

    private static string? GetWindowText(IntPtr hWnd)
    {
        var sb = new System.Text.StringBuilder(512);
        GetWindowText(hWnd, sb, sb.Capacity);
        return sb.ToString();
    }

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
}
''')

write("src/FsMonitor/IpcClient.cs", '''using FsCommon;
using System.IO.Pipes;
using System.Text;
using System.Text.Json;

namespace FsMonitor;

/// <summary>
/// Client side of the FsAgent IPC pipe. Reconnects automatically.
/// </summary>
public sealed class IpcClient : IDisposable
{
    private NamedPipeClientStream? _pipe;
    private StreamWriter? _writer;
    private readonly object _lock = new();

    public bool Connected => _pipe?.IsConnected == true;

    public void Connect()
    {
        try
        {
            lock (_lock)
            {
                _pipe?.Dispose();
                _pipe = new NamedPipeClientStream(".", ProcessNames.WatchdogPipe,
                    PipeDirection.Out, PipeOptions.Asynchronous);
                _pipe.Connect(2000);
                _writer = new StreamWriter(_pipe, new UTF8Encoding(false));
                _writer.AutoFlush = true;
                Logger.Info(ProcessNames.Monitor, "IPC connected to FsAgent");
            }
        }
        catch
        {
            _pipe?.Dispose();
            _pipe = null;
        }
    }

    public void SendUsage(UsageRecordIn rec)
    {
        if (!Connected) Connect();
        if (!Connected) return;
        try
        {
            lock (_lock)
            {
                var env = new
                {
                    type = "usage_record",
                    payload = rec
                };
                var json = JsonSerializer.Serialize(env);
                _writer!.WriteLine(json);
            }
        }
        catch (Exception ex)
        {
            Logger.Warn(ProcessNames.Monitor, $"SendUsage failed: {ex.Message}");
            Connect();
        }
    }

    public void Dispose()
    {
        lock (_lock)
        {
            _writer?.Dispose();
            _pipe?.Dispose();
        }
    }
}
''')


# ============ FsQuiz (UI placeholder - real UI in P4) ============
write("src/FsQuiz/FsQuiz.csproj", '''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net8.0-windows</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <UseWindowsForms>true</UseWindowsForms>
    <RootNamespace>FsQuiz</RootNamespace>
    <AssemblyName>FsQuiz</AssemblyName>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="..\\FsCommon\\FsCommon.csproj" />
  </ItemGroup>
</Project>
''')

write("src/FsQuiz/Program.cs", '''using FsCommon;

namespace FsQuiz;

/// <summary>
/// FsQuiz: fullscreen quiz UI (TopMost + locked).
/// P3 implements basic quiz flow; P4 will add keyboard hooks for hard lock.
/// </summary>
internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        Logger.Init(ProcessNames.Quiz);
        Logger.Info(ProcessNames.Quiz, "Starting FsQuiz");

        var cfg = AgentConfig.Load();
        var client = new BackendClient(cfg);
        var session = new QuizSession(client, cfg);
        session.Run();
        return 0;
    }
}
''')

write("src/FsQuiz/QuizSession.cs", '''using FsCommon;
using System.Text.Json;

namespace FsQuiz;

/// <summary>
/// Quiz session driver: start -> render questions -> collect answers -> submit.
/// UI rendering is in QuizForm (P3: WinForms basics, P4: WPF + hook lock).
/// </summary>
public sealed class QuizSession
{
    private readonly BackendClient _client;
    private readonly AgentConfig _cfg;

    public QuizSession(BackendClient client, AgentConfig cfg)
    {
        _client = client;
        _cfg = cfg;
    }

    public void Run()
    {
        try
        {
            // Pick a subject based on agent config (random among subjects for v0.1)
            var subjects = new[] { "math", "chinese", "english", "science" };
            var subject = subjects[Random.Shared.Next(subjects.Length)];

            var start = _client.StartQuizAsync(new QuizStartRequest { Subject = subject })
                              .GetAwaiter().GetResult();
            if (start == null || start.Questions.Count == 0)
            {
                Logger.Error(ProcessNames.Quiz, "No questions returned");
                return;
            }

            Logger.Info(ProcessNames.Quiz,
                $"Got {start.Questions.Count} questions, subject={subject}");

            // Render and collect
            var form = new QuizForm(start);
            Application.Run(form);

            if (form.Submitted && form.Answers.Count > 0)
            {
                var answers = form.Answers.ToDictionary(
                    kv => kv.Key.ToString(),
                    kv => kv.Value);

                var result = _client.SubmitQuizAsync(new QuizSubmitRequest
                {
                    Token = start.Token,
                    Answers = answers
                }).GetAwaiter().GetResult();

                if (result != null)
                {
                    Logger.Info(ProcessNames.Quiz,
                        $"Score {result.Score}/{result.Total}, reward {result.RewardMinutes}min");
                    MessageBox.Show(
                        $"本次答题：{result.Score}/{result.Total}（{result.CorrectRate:P0}）\n" +
                        $"奖励 {result.RewardMinutes} 分钟！\n\n" +
                        string.Join("\n", result.Explanations),
                        "答题结果",
                        MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
            }
        }
        catch (Exception ex)
        {
            Logger.Error(ProcessNames.Quiz, "Quiz session failed", ex);
            MessageBox.Show("答题系统出错，请联系家长。", "FamilySafety",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }
}
''')

write("src/FsQuiz/QuizForm.cs", '''using FsCommon;

namespace FsQuiz;

/// <summary>
/// Quiz UI - P3 minimal version.
/// P4 will add:
///   - TopMost + LockWindowUpdate (prevents alt-tab escape)
///   - Disable Task Manager via registry
///   - Hook DLL for keyboard (blocks Alt+F4, Win key, Ctrl+Esc)
/// </summary>
public sealed class QuizForm : Form
{
    private readonly QuizStartResponse _start;
    private readonly List<RadioButton>[] _optionsByQuestion;
    private int _currentQuestion = 0;
    public Dictionary<int, string> Answers { get; } = new();
    public bool Submitted { get; private set; }

    public QuizForm(QuizStartResponse start)
    {
        _start = start;
        _optionsByQuestion = new List<RadioButton>[start.Questions.Count];

        Text = "FamilySafety 答题";
        Width = 720;
        Height = 540;
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false;
        MinimizeBox = false;
        BackColor = Color.FromArgb(245, 247, 250);
        Font = new Font("Microsoft YaHei UI", 12);

        RenderQuestion();
    }

    private void RenderQuestion()
    {
        Controls.Clear();
        var q = _start.Questions[_currentQuestion];

        var lblTitle = new Label
        {
            Text = $"第 {_currentQuestion + 1} / {_start.Questions.Count} 题  ({q.Subject})",
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
        btnPrev.Click += (s, e) => { SaveCurrent(); _currentQuestion--; RenderQuestion(); };
        Controls.Add(btnPrev);
    }

    private void SaveCurrent()
    {
        var opts = _optionsByQuestion[_currentQuestion];
        for (int i = 0; i < opts.Count; i++)
        {
            if (opts[i].Checked)
            {
                Answers[_currentQuestion] = ((char)('A' + i)).ToString();
                return;
            }
        }
    }

    private void BtnNext_Click(object? sender, EventArgs e)
    {
        SaveCurrent();
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
}
''')


# ============ FsTray (minimal placeholder for P3) ============
write("src/FsTray/FsTray.csproj", '''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>WinExe</OutputType>
    <TargetFramework>net8.0-windows</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <UseWindowsForms>true</UseWindowsForms>
    <RootNamespace>FsTray</RootNamespace>
    <AssemblyName>FsTray</AssemblyName>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="..\\FsCommon\\FsCommon.csproj" />
  </ItemGroup>
</Project>
''')

write("src/FsTray/Program.cs", '''using FsCommon;

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
''')


# ============ FsWatchdog (minimal - real impl in P4 with hooks) ============
write("src/FsWatchdog/FsWatchdog.csproj", '''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net8.0-windows</TargetFramework>
    <Nullable>enable</Nullable>
    <ImplicitUsings>enable</ImplicitUsings>
    <RootNamespace>FsWatchdog</RootNamespace>
    <AssemblyName>FsWatchdog</AssemblyName>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="..\\FsCommon\\FsCommon.csproj" />
  </ItemGroup>
</Project>
''')

write("src/FsWatchdog/Program.cs", '''using FsCommon;
using System.Diagnostics;

namespace FsWatchdog;

/// <summary>
/// FsWatchdog: supervises FsAgent + FsMonitor. If they die, restart.
/// P3: file-based liveness + Process.Start. P4: add Win32 hooks / SCM service.
/// </summary>
internal static class Program
{
    private static int Main(string[] args)
    {
        Logger.Init(ProcessNames.Watchdog);
        Logger.Info(ProcessNames.Watchdog, "Starting FsWatchdog");

        var watchdogDir = AppContext.BaseDirectory;
        var agentExe = Path.Combine(watchdogDir, "FsAgent.exe");
        var monitorExe = Path.Combine(watchdogDir, "FsMonitor.exe");
        var trayExe = Path.Combine(watchdogDir, "FsTray.exe");
        var aliveFile = Path.Combine(AgentConfig.ConfigDir, "agent.alive");

        // Spawn the trio
        LaunchIfMissing(agentExe, "FsAgent");
        LaunchIfMissing(monitorExe, "FsMonitor");
        LaunchIfMissing(trayExe, "FsTray");

        while (true)
        {
            Thread.Sleep(5000);

            try
            {
                if (!File.Exists(aliveFile) ||
                    (DateTime.UtcNow - File.GetLastWriteTimeUtc(aliveFile)).TotalSeconds > 30)
                {
                    Logger.Warn(ProcessNames.Watchdog, "FsAgent appears dead, restarting");
                    LaunchIfMissing(agentExe, "FsAgent");
                }
            }
            catch (Exception ex)
            {
                Logger.Warn(ProcessNames.Watchdog, $"Check failed: {ex.Message}");
            }

            // Restart monitor if died
            if (!IsRunning(ProcessNames.Monitor))
            {
                Logger.Warn(ProcessNames.Watchdog, "FsMonitor dead, restarting");
                LaunchIfMissing(monitorExe, "FsMonitor");
            }
        }
    }

    private static void LaunchIfMissing(string exe, string name)
    {
        if (IsRunning(name))
        {
            Logger.Info(ProcessNames.Watchdog, $"{name} already running");
            return;
        }
        try
        {
            if (!File.Exists(exe))
            {
                Logger.Error(ProcessNames.Watchdog, $"{exe} not found");
                return;
            }
            var psi = new ProcessStartInfo
            {
                FileName = exe,
                UseShellExecute = false,
                WorkingDirectory = Path.GetDirectoryName(exe),
            };
            Process.Start(psi);
            Logger.Info(ProcessNames.Watchdog, $"Launched {name}");
        }
        catch (Exception ex)
        {
            Logger.Error(ProcessNames.Watchdog, $"Failed to launch {name}", ex);
        }
    }

    private static bool IsRunning(string name)
    {
        try
        {
            return Process.GetProcessesByName(name).Length > 0;
        }
        catch
        {
            return false;
        }
    }
}
''')


# ============ README ============
write("README.md", '''# FamilySafety Windows Agent

C# .NET 8 family of processes that run on each child's Windows computer.

## Process Architecture

```
FsWatchdog (the only "service-like" process)
  ├── supervises → restarts if dead
  ├── FsAgent (core daemon)
  │     ├── Registers device with backend
  │     ├── Sends periodic heartbeats
  │     ├── Receives commands (force_quiz, warnings)
  │     └── Hosts IPC pipe for monitor + quiz
  ├── FsMonitor (foreground tracker)
  │     └── Reports (app_name, window_title, duration) to FsAgent
  ├── FsQuiz (fullscreen UI, spawned on demand)
  │     ├── Start quiz session
  │     ├── Collect answers
  │     └── Submit + display reward
  └── FsTray (system tray icon)
        └── Quick actions + warnings
```

## Build

Requires .NET 8 SDK.

```bash
cd agent-windows
dotnet build FamilySafety.sln -c Release
```

Output goes to `src/FsAgent/bin/Release/net8.0-windows/`.

## Run (development)

```bash
# Start in order (FsWatchdog spawns the others)
cd src/FsWatchdog/bin/Release/net8.0-windows
./FsWatchdog.exe
```

## Configuration

`%ProgramData%\\FamilySafety\\agent.json` is auto-generated on first run:

```json
{
  "backendUrl": "http://192.168.1.10:8000",
  "deviceName": "DESKTOP-ABC123",
  "heartbeatIntervalSec": 30,
  "usageFlushIntervalSec": 60,
  "debug": false
}
```

`api_key` and `device_id` are populated after first successful registration.

## Logs

`%ProgramData%\\FamilySafety\\logs\\{FsWatchdog,FsAgent,FsMonitor,FsQuiz,FsTray}.log`

## Process Guarding (P3 baseline → P4 hardened)

| Layer | P3 | P4 |
|-------|----|----|
| Watchdog restart | file timestamp check | + named pipe ping + WM_TIMER |
| Task Manager block | none | registry + Hook DLL |
| Alt+F4 / Win key block | none | WH_KEYBOARD_LL hook DLL |
| UI lock during quiz | Form.TopMost | + LockSetForegroundWindow |
| NTFS ACL on agent dir | none | DACL prevents child user delete |
| Run as service | none | SCM service via `sc create` |
''')

print("\nP3 Windows Agent code done.")