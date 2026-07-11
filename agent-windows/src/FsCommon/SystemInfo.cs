using System.Management;
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
