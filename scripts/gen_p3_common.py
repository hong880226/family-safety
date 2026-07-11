"""P3: Generate Windows Agent C# .NET 8 project structure."""
from pathlib import Path

ROOT = Path("E:/codeRepo/familysafety/agent-windows")


def write(rel: str, content: str) -> None:
    target = ROOT / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"  wrote {rel} ({len(content)} bytes)")


# ===== Solution file =====
write("FamilySafety.sln", '''Microsoft Visual Studio Solution File, Format Version 12.00
# Visual Studio Version 17
Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "FsAgent", "src\FsAgent\FsAgent.csproj", "{11111111-1111-1111-1111-111111111111}"
EndProject
Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "FsMonitor", "src\FsMonitor\FsMonitor.csproj", "{22222222-2222-2222-2222-222222222222}"
EndProject
Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "FsQuiz", "src\FsQuiz\FsQuiz.csproj", "{33333333-3333-3333-3333-333333333333}"
EndProject
Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "FsTray", "src\FsTray\FsTray.csproj", "{44444444-4444-4444-4444-444444444444}"
EndProject
Project("{FAE04EC0-301F-11D3-BF4B-00C04F79EFBC}") = "FsCommon", "src\FsCommon\FsCommon.csproj", "{55555555-5555-5555-5555-555555555555}"
EndProject
Global
\tGlobalSection(SolutionConfigurationPlatforms) = preSolution
\t\tDebug|Any CPU = Debug|Any CPU
\t\tRelease|Any CPU = Release|Any CPU
\tEndGlobalSection
\tGlobalSection(ProjectConfigurationPlatforms) = postSolution
\t\t{11111111-1111-1111-1111-111111111111}.Debug|Any CPU.ActiveCfg = Debug|Any CPU
\t\t{11111111-1111-1111-1111-111111111111}.Debug|Any CPU.Build.0 = Debug|Any CPU
\t\t{11111111-1111-1111-1111-111111111111}.Release|Any CPU.ActiveCfg = Release|Any CPU
\t\t{11111111-1111-1111-1111-111111111111}.Release|Any CPU.Build.0 = Release|Any CPU
\t\t{22222222-2222-2222-2222-222222222222}.Debug|Any CPU.ActiveCfg = Debug|Any CPU
\t\t{22222222-2222-2222-2222-222222222222}.Debug|Any CPU.Build.0 = Debug|Any CPU
\t\t{22222222-2222-2222-2222-222222222222}.Release|Any CPU.ActiveCfg = Release|Any CPU
\t\t{22222222-2222-2222-2222-222222222222}.Release|Any CPU.Build.0 = Release|Any CPU
\t\t{33333333-3333-3333-3333-333333333333}.Debug|Any CPU.ActiveCfg = Debug|Any CPU
\t\t{33333333-3333-3333-3333-333333333333}.Debug|Any CPU.Build.0 = Debug|Any CPU
\t\t{33333333-3333-3333-3333-333333333333}.Release|Any CPU.ActiveCfg = Release|Any CPU
\t\t{33333333-3333-3333-3333-333333333333}.Release|Any CPU.Build.0 = Release|Any CPU
\t\t{44444444-4444-4444-4444-444444444444}.Debug|Any CPU.ActiveCfg = Debug|Any CPU
\t\t{44444444-4444-4444-4444-444444444444}.Debug|Any CPU.Build.0 = Debug|Any CPU
\t\t{44444444-4444-4444-4444-444444444444}.Release|Any CPU.ActiveCfg = Release|Any CPU
\t\t{44444444-4444-4444-4444-444444444444}.Release|Any CPU.Build.0 = Release|Any CPU
\t\t{55555555-5555-5555-5555-555555555555}.Debug|Any CPU.ActiveCfg = Debug|Any CPU
\t\t{55555555-5555-5555-5555-555555555555}.Debug|Any CPU.Build.0 = Debug|Any CPU
\t\t{55555555-5555-5555-5555-555555555555}.Release|Any CPU.ActiveCfg = Release|Any CPU
\t\t{55555555-5555-5555-5555-555555555555}.Release|Any CPU.Build.0 = Release|Any CPU
\tEndGlobalSection
EndGlobal
''')

# ===== Shared library =====
write("src/FsCommon/FsCommon.csproj", '''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net8.0-windows</TargetFramework>
    <Nullable>enable</Nullable>
    <LangVersion>12.0</LangVersion>
    <TreatWarningsAsErrors>false</TreatWarningsAsErrors>
    <ImplicitUsings>enable</ImplicitUsings>
  </PropertyGroup>
</Project>
''')

write("src/FsCommon/AgentConfig.cs", '''using System.Text.Json;
using System.Text.Json.Serialization;

namespace FsCommon;

/// <summary>
/// Configuration loaded from %ProgramData%\\FamilySafety\\agent.json.
/// Falls back to built-in defaults if file is missing.
/// </summary>
public sealed class AgentConfig
{
    public string BackendUrl { get; set; } = "http://127.0.0.1:8000";
    public string ApiKey { get; set; } = "";
    public string DeviceId { get; set; } = "";
    public string DeviceName { get; set; } = Environment.MachineName;
    public string ComputerModel { get; set; } = "";
    public string WindowsUsername { get; set; } = "";
    public int HeartbeatIntervalSec { get; set; } = 30;
    public int UsageFlushIntervalSec { get; set; } = 60;
    public bool Debug { get; set; } = false;

    public static string ConfigDir => Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
        "FamilySafety"
    );

    public static string ConfigPath => Path.Combine(ConfigDir, "agent.json");

    public static AgentConfig Load()
    {
        try
        {
            if (File.Exists(ConfigPath))
            {
                var json = File.ReadAllText(ConfigPath);
                var cfg = JsonSerializer.Deserialize<AgentConfig>(json, new JsonSerializerOptions
                {
                    PropertyNameCaseInsensitive = true,
                    ReadCommentHandling = JsonCommentHandling.Skip,
                    AllowTrailingCommas = true
                });
                if (cfg != null) return cfg;
            }
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[FsCommon] Config load failed: {ex.Message}");
        }
        return new AgentConfig();
    }

    public void Save()
    {
        try
        {
            Directory.CreateDirectory(ConfigDir);
            var json = JsonSerializer.Serialize(this, new JsonSerializerOptions
            {
                WriteIndented = true,
                PropertyNamingPolicy = JsonNamingPolicy.CamelCase
            });
            File.WriteAllText(ConfigPath, json);
        }
        catch (Exception ex)
        {
            Console.Error.WriteLine($"[FsCommon] Config save failed: {ex.Message}");
        }
    }
}
''')

write("src/FsCommon/Logger.cs", '''using System.Text;

namespace FsCommon;

/// <summary>
/// Simple file + console logger. Writes to %ProgramData%\\FamilySafety\\logs\\{name}.log
/// </summary>
public static class Logger
{
    private static readonly object _lock = new();
    private static string? _logDir;

    public static void Init(string name)
    {
        _logDir = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.CommonApplicationData),
            "FamilySafety", "logs"
        );
        Directory.CreateDirectory(_logDir!);
    }

    public static void Info(string source, string msg)
    {
        Write("INFO", source, msg);
        Console.WriteLine($"[{source}] {msg}");
    }

    public static void Warn(string source, string msg)
    {
        Write("WARN", source, msg);
        Console.Error.WriteLine($"[{source}] WARN: {msg}");
    }

    public static void Error(string source, string msg, Exception? ex = null)
    {
        var full = ex == null ? msg : $"{msg} :: {ex.GetType().Name}: {ex.Message}";
        Write("ERROR", source, full);
        Console.Error.WriteLine($"[{source}] ERROR: {full}");
    }

    private static void Write(string level, string source, string msg)
    {
        if (_logDir == null) return;
        try
        {
            lock (_lock)
            {
                var file = Path.Combine(_logDir, $"{source}.log");
                File.AppendAllText(file,
                    $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} [{level}] {msg}{Environment.NewLine}",
                    Encoding.UTF8);
            }
        }
        catch
        {
            // swallow - logger should not crash
        }
    }
}
''')

write("src/FsCommon/ProcessNames.cs", '''namespace FsCommon;

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
    public const string WatchdogMutex = "Global\\\\FsWatchdog_SingleInstance";

    /// <summary>
    /// Named pipe for watchdog IPC (heartbeat, restart requests).
    /// </summary>
    public const string WatchdogPipe = "FsWatchdog_Pipe";

    /// <summary>
    /// Shared memory segment for monitor->agent IPC.
    /// </summary>
    public const string SharedMemName = "FsShared_State";
}
''')

write("src/FsCommon/BackendClient.cs", '''using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace FsCommon;

/// <summary>
/// HTTP client for the FamilySafety backend.
/// All endpoints live under /api/v1/. Bearer auth via ApiKey.
/// </summary>
public sealed class BackendClient
{
    private readonly HttpClient _http;
    private readonly AgentConfig _cfg;
    private readonly JsonSerializerOptions _jsonOpts = new()
    {
        PropertyNameCaseInsensitive = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull
    };

    public BackendClient(AgentConfig cfg)
    {
        _cfg = cfg;
        _http = new HttpClient
        {
            BaseAddress = new Uri(cfg.BackendUrl),
            Timeout = TimeSpan.FromSeconds(15)
        };
    }

    private void Auth()
    {
        _http.DefaultRequestHeaders.Authorization =
            new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", _cfg.ApiKey);
    }

    public async Task<RegisterResponse?> RegisterAsync(RegisterRequest req, CancellationToken ct = default)
    {
        var resp = await _http.PostAsJsonAsync("/api/v1/agent/register", req, _jsonOpts, ct);
        resp.EnsureSuccessStatusCode();
        return await resp.Content.ReadFromJsonAsync<RegisterResponse>(_jsonOpts, ct);
    }

    public async Task<HeartbeatResponse?> HeartbeatAsync(HeartbeatRequest req, CancellationToken ct = default)
    {
        Auth();
        var resp = await _http.PostAsJsonAsync("/api/v1/agent/heartbeat", req, _jsonOpts, ct);
        resp.EnsureSuccessStatusCode();
        return await resp.Content.ReadFromJsonAsync<HeartbeatResponse>(_jsonOpts, ct);
    }

    public async Task<bool> ReportUsageAsync(UsageBatchRequest req, CancellationToken ct = default)
    {
        Auth();
        var resp = await _http.PostAsJsonAsync("/api/v1/agent/usage", req, _jsonOpts, ct);
        return resp.IsSuccessStatusCode;
    }

    public async Task<QuizStartResponse?> StartQuizAsync(QuizStartRequest req, CancellationToken ct = default)
    {
        Auth();
        var resp = await _http.PostAsJsonAsync("/api/v1/quiz/start", req, _jsonOpts, ct);
        resp.EnsureSuccessStatusCode();
        return await resp.Content.ReadFromJsonAsync<QuizStartResponse>(_jsonOpts, ct);
    }

    public async Task<QuizSubmitResponse?> SubmitQuizAsync(QuizSubmitRequest req, CancellationToken ct = default)
    {
        Auth();
        var resp = await _http.PostAsJsonAsync("/api/v1/quiz/submit", req, _jsonOpts, ct);
        resp.EnsureSuccessStatusCode();
        return await resp.Content.ReadFromJsonAsync<QuizSubmitResponse>(_jsonOpts, ct);
    }
}

// ===== DTOs matching backend Pydantic schemas =====

public sealed class RegisterRequest
{
    [JsonPropertyName("device_id")] public string? DeviceId { get; set; }
    [JsonPropertyName("name")] public string Name { get; set; } = "";
    [JsonPropertyName("device_type")] public string DeviceType { get; set; } = "windows";
    [JsonPropertyName("computer_model")] public string? ComputerModel { get; set; }
    [JsonPropertyName("windows_username")] public string? WindowsUsername { get; set; }
    [JsonPropertyName("family_setup_token")] public string? FamilySetupToken { get; set; }
}

public sealed class RegisterResponse
{
    [JsonPropertyName("device_id")] public string DeviceId { get; set; } = "";
    [JsonPropertyName("api_key")] public string ApiKey { get; set; } = "";
    [JsonPropertyName("family_id")] public int FamilyId { get; set; }
    [JsonPropertyName("member_id")] public int? MemberId { get; set; }
    [JsonPropertyName("message")] public string Message { get; set; } = "";
}

public sealed class HeartbeatRequest
{
    [JsonPropertyName("timestamp")] public DateTime Timestamp { get; set; }
    [JsonPropertyName("windows_username")] public string? WindowsUsername { get; set; }
    [JsonPropertyName("computer_model")] public string? ComputerModel { get; set; }
    [JsonPropertyName("current_app")] public string? CurrentApp { get; set; }
    [JsonPropertyName("window_title")] public string? WindowTitle { get; set; }
    [JsonPropertyName("used_seconds_today")] public int UsedSecondsToday { get; set; }
    [JsonPropertyName("used_seconds_this_week")] public int UsedSecondsThisWeek { get; set; }
    [JsonPropertyName("uptime_seconds")] public int UptimeSeconds { get; set; }
}

public sealed class HeartbeatResponse
{
    [JsonPropertyName("matched_rule")] public System.Text.Json.JsonElement? MatchedRule { get; set; }
    [JsonPropertyName("matched_member_id")] public int? MatchedMemberId { get; set; }
    [JsonPropertyName("commands")] public List<System.Text.Json.JsonElement> Commands { get; set; } = new();
    [JsonPropertyName("server_time")] public DateTime ServerTime { get; set; }
}

public sealed class UsageBatchRequest
{
    [JsonPropertyName("records")] public List<UsageRecordIn> Records { get; set; } = new();
}

public sealed class UsageRecordIn
{
    [JsonPropertyName("app_name")] public string AppName { get; set; } = "";
    [JsonPropertyName("window_title")] public string? WindowTitle { get; set; }
    [JsonPropertyName("start_at")] public DateTime StartAt { get; set; }
    [JsonPropertyName("end_at")] public DateTime EndAt { get; set; }
    [JsonPropertyName("duration_seconds")] public int DurationSeconds { get; set; }
    [JsonPropertyName("category")] public string? Category { get; set; }
    [JsonPropertyName("sub_label")] public string? SubLabel { get; set; }
    [JsonPropertyName("confidence")] public double? Confidence { get; set; }
    [JsonPropertyName("is_overtime")] public bool IsOvertime { get; set; }
}

public sealed class QuizStartRequest
{
    [JsonPropertyName("subject")] public string? Subject { get; set; }
}

public sealed class QuizStartResponse
{
    [JsonPropertyName("token")] public string Token { get; set; } = "";
    [JsonPropertyName("questions")] public List<QuizQuestion> Questions { get; set; } = new();
    [JsonPropertyName("config_used")] public System.Text.Json.JsonElement? ConfigUsed { get; set; }
    [JsonPropertyName("expires_in")] public int ExpiresIn { get; set; }
}

public sealed class QuizQuestion
{
    [JsonPropertyName("id")] public int Id { get; set; }
    [JsonPropertyName("subject")] public string Subject { get; set; } = "";
    [JsonPropertyName("grade")] public int Grade { get; set; }
    [JsonPropertyName("difficulty")] public int Difficulty { get; set; }
    [JsonPropertyName("question")] public string Question { get; set; } = "";
    [JsonPropertyName("options")] public List<string> Options { get; set; } = new();
}

public sealed class QuizSubmitRequest
{
    [JsonPropertyName("token")] public string Token { get; set; } = "";
    [JsonPropertyName("answers")] public Dictionary<string, string> Answers { get; set; } = new();
}

public sealed class QuizSubmitResponse
{
    [JsonPropertyName("score")] public int Score { get; set; }
    [JsonPropertyName("total")] public int Total { get; set; }
    [JsonPropertyName("correct_rate")] public double CorrectRate { get; set; }
    [JsonPropertyName("reward_minutes")] public int RewardMinutes { get; set; }
    [JsonPropertyName("explanations")] public List<string> Explanations { get; set; } = new();
    [JsonPropertyName("remaining_minutes")] public int? RemainingMinutes { get; set; }
}
''')

write("src/FsCommon/SystemInfo.cs", '''using System.Management;
using System.Runtime.InteropServices;

namespace FsCommon;

/// <summary>
/// Collects system metadata for device registration.
/// </summary>
public static class SystemInfo
{
    public static string GetWindowsUsername()
    {
        try
        {
            return Environment.UserName ?? "";
        }
        catch
        {
            return "";
        }
    }

    public static string GetComputerModel()
    {
        try
        {
            using var searcher = new ManagementObjectSearcher("SELECT * FROM Win32_ComputerSystem");
            foreach (var obj in searcher.Get())
            {
                var model = obj["Model"]?.ToString();
                var manufacturer = obj["Manufacturer"]?.ToString();
                if (!string.IsNullOrWhiteSpace(model))
                {
                    return $"{manufacturer} {model}".Trim();
                }
            }
        }
        catch
        {
            // WMI not available (e.g. non-Windows during dev)
        }
        return "Unknown";
    }

    public static string GetDeviceId()
    {
        // Stable machine ID via SMBIOS UUID, fallback to machine name hash.
        try
        {
            using var searcher = new ManagementObjectSearcher("SELECT UUID FROM Win32_ComputerSystemProduct");
            foreach (var obj in searcher.Get())
            {
                var uuid = obj["UUID"]?.ToString();
                if (!string.IsNullOrWhiteSpace(uuid) && uuid != "FFFFFFFF-FFFF-FFFF-FFFF-FFFFFFFFFFFF")
                {
                    return uuid;
                }
            }
        }
        catch
        {
            // ignored
        }
        // Fallback: SHA-256 of machine name + OS version
        var input = $"{Environment.MachineName}|{Environment.OSVersion}";
        var bytes = System.Text.Encoding.UTF8.GetBytes(input);
        var hash = System.Security.Cryptography.SHA256.HashData(bytes);
        return Convert.ToHexString(hash)[..32];
    }
}
''')

print("\nFsCommon done.")