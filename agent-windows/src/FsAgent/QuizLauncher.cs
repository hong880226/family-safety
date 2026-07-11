using FsCommon;
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
