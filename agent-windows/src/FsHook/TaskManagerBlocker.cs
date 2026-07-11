using System.Runtime.InteropServices;

namespace FsHook;

/// <summary>
/// C# wrapper around the native Task Manager blocker.
/// </summary>
public static class TaskManagerBlocker
{
    public static bool Block() => Native_Block();
    public static bool Unblock() => Native_Unblock();
    public static bool IsBlocked() => Native_IsBlocked();

    [DllImport("FsHook.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern bool Native_Block();
    [DllImport("FsHook.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern bool Native_Unblock();
    [DllImport("FsHook.dll", CallingConvention = CallingConvention.Cdecl)]
    private static extern bool Native_IsBlocked();
}
