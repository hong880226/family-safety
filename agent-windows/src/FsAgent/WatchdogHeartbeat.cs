using FsCommon;
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
