using System.IO.Pipes;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace FsCommon;

/// <summary>
/// Client side for the FsWatchdog control pipe. Used by FsTray, FsConfigUI,
/// and the CLI subcommand to ask the running FsWatchdogService to perform
/// a privileged action (currently: graceful_stop) without going through
/// sc.exe (which triggers UAC and forces the parent into an admin shell).
///
/// Wire format (single line of UTF-8 JSON):
///     { "type": "graceful_stop", "password_hash": "<b64>",
///       "salt": "<b64>", "iterations": 100000 }
///
/// The caller PBKDF2-hashes the entered plaintext with the salt it just
/// read from <see cref="ParentAuth.ExportForSync"/> and ships only the
/// resulting hash over the pipe. The watchdog re-derives PBKDF2 from its
/// own copy of the stored hash/salt and compares constant-time — the
/// plaintext never crosses the pipe boundary.
/// </summary>
public static class ServicePipeClient
{
    private const int ConnectTimeoutMs = 2000;

    public static bool SendGracefulStop(string passwordHashBase64,
                                        string saltBase64,
                                        int iterations)
    {
        var payload = JsonSerializer.Serialize(new GracefulStopMessage
        {
            Type = "graceful_stop",
            PasswordHash = passwordHashBase64 ?? "",
            Salt = saltBase64 ?? "",
            Iterations = iterations,
        });

        try
        {
            using var pipe = new NamedPipeClientStream(
                ".",
                ProcessNames.WatchdogControlPipe,
                PipeDirection.Out,
                PipeOptions.None);

            pipe.Connect(ConnectTimeoutMs);
            using var writer = new StreamWriter(pipe, new UTF8Encoding(false));
            writer.AutoFlush = true;
            writer.WriteLine(payload);
            return true;
        }
        catch (TimeoutException)
        {
            Logger.Warn("ServicePipeClient", "Watchdog control pipe not reachable (timeout)");
            return false;
        }
        catch (Exception ex)
        {
            Logger.Warn("ServicePipeClient",
                $"SendGracefulStop failed: {ex.GetType().Name}: {ex.Message}");
            return false;
        }
    }

    /// <summary>
    /// Convenience: derive the PBKDF2 hash of <paramref name="enteredPassword"/>
    /// using the same parameters exported from <see cref="ParentAuth"/> and
    /// ship it. Returns false if no password is configured yet.
    /// </summary>
    public static bool SendGracefulStop(string enteredPassword)
    {
        var blob = ParentAuth.ExportForSync();
        if (blob == null) return false;

        // Mirror ParentAuth.Pbkdf2 (SHA-256, 32 bytes) but using the caller-
        // supplied plaintext and the stored salt/iterations.
        byte[] derived;
        using (var deriver = new Rfc2898DeriveBytes(
            Encoding.UTF8.GetBytes(enteredPassword ?? ""),
            Convert.FromBase64String(blob.SaltBase64),
            blob.Iterations,
            HashAlgorithmName.SHA256))
        {
            derived = deriver.GetBytes(32);
        }
        var hashB64 = Convert.ToBase64String(derived);

        return SendGracefulStop(hashB64, blob.SaltBase64, blob.Iterations);
    }

    private sealed class GracefulStopMessage
    {
        [JsonPropertyName("type")] public string Type { get; set; } = "";
        [JsonPropertyName("password_hash")] public string PasswordHash { get; set; } = "";
        [JsonPropertyName("salt")] public string Salt { get; set; } = "";
        [JsonPropertyName("iterations")] public int Iterations { get; set; }
    }
}
