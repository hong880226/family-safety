using FsCommon;

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
