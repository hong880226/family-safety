using FsCommon;

namespace FsMonitor;

/// <summary>
/// Foreground window tracker using Win32 APIs.
/// </summary>
public static class WinApi
{
    public static (string App, string Title) GetForegroundInfo()
    {
        try
        {
            var hwnd = GetForegroundWindow();
            if (hwnd == IntPtr.Zero) return ("", "");
            var title = GetWindowText(hwnd);
            GetWindowThreadProcessId(hwnd, out uint pid);
            var proc = System.Diagnostics.Process.GetProcessById((int)pid);
            var appName = proc.ProcessName + ".exe";
            proc.Dispose();
            return (appName, title ?? "");
        }
        catch
        {
            return ("", "");
        }
    }

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    [System.Runtime.InteropServices.DllImport("user32.dll", CharSet = System.Runtime.InteropServices.CharSet.Unicode)]
    private static extern int GetWindowText(IntPtr hWnd, System.Text.StringBuilder lpString, int nMaxCount);

    private static string? GetWindowText(IntPtr hWnd)
    {
        var sb = new System.Text.StringBuilder(512);
        GetWindowText(hWnd, sb, sb.Capacity);
        return sb.ToString();
    }

    [System.Runtime.InteropServices.DllImport("user32.dll")]
    private static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint lpdwProcessId);
}
