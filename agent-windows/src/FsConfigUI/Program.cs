using FsCommon;

namespace FsConfigUI;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        Logger.Init("FsConfigUI");
        Application.SetHighDpiMode(HighDpiMode.SystemAware);
        Application.Run(new MainForm());
    }
}