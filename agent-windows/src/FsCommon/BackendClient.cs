using System.Net.Http.Json;
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

    /// <summary>
    /// Cloud-sync the parent password blob so the parent dashboard can
    /// verify / rotate the parent password remotely. Idempotent.
    /// </summary>
    public async Task<bool> SyncParentPasswordAsync(SyncParentPasswordRequest req, CancellationToken ct = default)
    {
        Auth();
        var resp = await _http.PostAsJsonAsync("/api/v1/agent/sync-parent-password", req, _jsonOpts, ct);
        return resp.IsSuccessStatusCode;
    }

    /// <summary>
    /// Upload a screenshot (JPEG or PNG) to the backend's ingestion endpoint.
    /// The backend validates magic bytes, caps at 8 MiB, and rejects unknown
    /// trigger_type values (see backend/app/api/v1/agent.py).
    ///
    /// Returns true on HTTP 2xx, false otherwise. We do not throw on
    /// non-success — the caller (HeartbeatLoop) only logs and moves on.
    /// </summary>
    public async Task<bool> UploadScreenshotAsync(byte[] jpeg, string triggerType, CancellationToken ct = default)
    {
        Auth();
        using var form = new MultipartFormDataContent("----FSScreenshot" + Guid.NewGuid().ToString("N"));
        form.Add(new ByteArrayContent(jpeg), "file", $"screen-{DateTime.UtcNow:yyyyMMddHHmmss}.jpg");
        form.Add(new StringContent(triggerType ?? "parent_now"), "trigger_type");
        var resp = await _http.PostAsync("/api/v1/agent/screenshot", form, ct);
        return resp.IsSuccessStatusCode;
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

public sealed class SyncParentPasswordRequest
{
    [JsonPropertyName("hash")] public string Hash { get; set; } = "";
    [JsonPropertyName("salt")] public string Salt { get; set; } = "";
    [JsonPropertyName("iterations")] public int Iterations { get; set; }
}
