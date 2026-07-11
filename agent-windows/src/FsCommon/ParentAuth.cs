using System.Security.Cryptography;
using System.Text;

namespace FsCommon;

/// <summary>
/// DPAPI-encrypted PBKDF2-SHA256 password storage for the parent-auth wall.
///
/// File format (%ProgramData%\FamilySafety\parents.bin):
///   [ 4 bytes magic = "FSP1" ][ 16 bytes salt ][ 4 bytes iter LE ][ 32 bytes hash ]
///   The whole structure is encrypted via ProtectedData.Protect(scope=LocalMachine)
///   so only Windows administrators on this machine can read or modify it.
///
/// Threat model:
///   - Kid logs in as a normal (non-admin) user: cannot decrypt (DPAPI key is
///     per-machine + per-admin).
///   - Kid deletes the file: ParentAuth.IsSet() returns false; the watchdog
///     service refuses to start until the parent re-runs FsConfigUI.
///   - Filesystem is wiped / OS reinstalled: password must be re-entered.
///     There is intentionally no recovery backdoor — the password is the gate.
/// </summary>
public static class ParentAuth
{
    private const uint Magic = 0x31505346; // "FSP1" little-endian
    private const int SaltLen = 16;
    private const int HashLen = 32;
    private const int HeaderLen = 4 + SaltLen + 4; // magic + salt + iter

    public static string FilePath => Path.Combine(AgentConfig.ConfigDir, "parents.bin");

    public static bool IsSet() => File.Exists(FilePath);

    public static void SetPassword(string password)
    {
        if (string.IsNullOrEmpty(password))
            throw new ArgumentException("password must not be empty", nameof(password));
        if (password.Length < 8)
            throw new ArgumentException("password must be at least 8 characters", nameof(password));

        var salt = RandomNumberGenerator.GetBytes(SaltLen);
        const int iterations = 100_000;
        var hash = Pbkdf2(password, salt, iterations, HashLen);

        var plain = new byte[HeaderLen + HashLen];
        BitConverter.GetBytes(Magic).CopyTo(plain, 0);
        salt.CopyTo(plain, 4);
        BitConverter.GetBytes(iterations).CopyTo(plain, 4 + SaltLen);
        hash.CopyTo(plain, HeaderLen);

        var protectedBytes = ProtectedData.Protect(
            plain,
            optionalEntropy: null,
            scope: DataProtectionScope.LocalMachine);

        Directory.CreateDirectory(AgentConfig.ConfigDir);
        File.WriteAllBytes(FilePath, protectedBytes);

        Audit("set-password", $"iter={iterations}");
    }

    /// <summary>Constant-time verification; returns false on any error.</summary>
    public static bool Verify(string password)
    {
        try
        {
            if (!File.Exists(FilePath)) return false;
            if (string.IsNullOrEmpty(password)) return false;

            var protectedBytes = File.ReadAllBytes(FilePath);
            var plain = ProtectedData.Unprotect(
                protectedBytes,
                optionalEntropy: null,
                scope: DataProtectionScope.LocalMachine);

            if (plain.Length < HeaderLen + HashLen) return false;
            var magic = BitConverter.ToUInt32(plain, 0);
            if (magic != Magic) return false;

            var salt = new byte[SaltLen];
            Buffer.BlockCopy(plain, 4, salt, 0, SaltLen);
            var iter = BitConverter.ToInt32(plain, 4 + SaltLen);
            var expected = new byte[HashLen];
            Buffer.BlockCopy(plain, HeaderLen, expected, 0, HashLen);

            var actual = Pbkdf2(password, salt, iter, HashLen);
            return CryptographicOperations.FixedTimeEquals(actual, expected);
        }
        catch (Exception ex)
        {
            Logger.Warn("ParentAuth", $"Verify failed: {ex.GetType().Name}: {ex.Message}");
            return false;
        }
    }

    /// <summary>
    /// Reads the current hash + salt for cloud-sync (without revealing password).
    /// Returns null if the file is missing or unreadable.
    /// </summary>
    public static ParentPasswordBlob? ExportForSync()
    {
        try
        {
            if (!File.Exists(FilePath)) return null;
            var protectedBytes = File.ReadAllBytes(FilePath);
            var plain = ProtectedData.Unprotect(
                protectedBytes,
                optionalEntropy: null,
                scope: DataProtectionScope.LocalMachine);
            if (plain.Length < HeaderLen + HashLen) return null;
            if (BitConverter.ToUInt32(plain, 0) != Magic) return null;

            var salt = new byte[SaltLen];
            Buffer.BlockCopy(plain, 4, salt, 0, SaltLen);
            var iter = BitConverter.ToInt32(plain, 4 + SaltLen);
            var hash = new byte[HashLen];
            Buffer.BlockCopy(plain, HeaderLen, hash, 0, HashLen);

            return new ParentPasswordBlob
            {
                HashBase64 = Convert.ToBase64String(hash),
                SaltBase64 = Convert.ToBase64String(salt),
                Iterations = iter,
            };
        }
        catch (Exception ex)
        {
            Logger.Warn("ParentAuth", $"ExportForSync failed: {ex.Message}");
            return null;
        }
    }

    private static byte[] Pbkdf2(string password, byte[] salt, int iterations, int length)
    {
        using var deriver = new Rfc2898DeriveBytes(
            Encoding.UTF8.GetBytes(password), salt, iterations, HashAlgorithmName.SHA256);
        return deriver.GetBytes(length);
    }

    private static void Audit(string action, string detail)
    {
        try
        {
            var dir = Path.Combine(AgentConfig.ConfigDir, "logs");
            Directory.CreateDirectory(dir);
            var line = $"{DateTime.Now:yyyy-MM-dd HH:mm:ss.fff} [{action}] {detail}{Environment.NewLine}";
            File.AppendAllText(Path.Combine(dir, "auth.log"), line, Encoding.UTF8);
        }
        catch { /* ignore */ }
    }
}

public sealed class ParentPasswordBlob
{
    public string HashBase64 { get; set; } = "";
    public string SaltBase64 { get; set; } = "";
    public int Iterations { get; set; }
}