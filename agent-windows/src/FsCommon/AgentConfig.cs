using System.Text.Json;
using System.Text.Json.Serialization;

namespace FsCommon;

/// <summary>
/// Configuration loaded from %ProgramData%\FamilySafety\agent.json.
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
