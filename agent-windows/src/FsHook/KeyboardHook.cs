using System.Runtime.InteropServices;

namespace FsHook;

/// <summary>
/// C# wrapper around the native FsHook.dll low-level keyboard hook.
/// Add the FsHook.dll native binary to the project as Content (CopyToOutput).
/// </summary>
public static class KeyboardHook
{
    public static bool Install() => Native_Install();
    public static void Uninstall() => Native_Uninstall();
    public static bool IsInstalled() => Native_IsInstalled();
    public static void Suspend() => Native_Suspend();
    public static void Resume() => Native_Resume();

    [DllImport("FsHook.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern bool Native_Install();
    [DllImport("FsHook.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern void Native_Uninstall();
    [DllImport("FsHook.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern bool Native_IsInstalled();
    [DllImport("FsHook.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern void Native_Suspend();
    [DllImport("FsHook.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern void Native_Resume();
}
