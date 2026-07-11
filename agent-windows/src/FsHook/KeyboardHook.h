#pragma once

#include <Windows.h>
#include <vcclr.h>

namespace FsHook {

/// <summary>
/// Low-level keyboard hook (WH_KEYBOARD_LL). Blocks dangerous key combos
/// during quiz mode:
///   - Alt+F4        (close window)
///   - Alt+Tab       (switch app)
///   - Alt+Esc
///   - Ctrl+Esc      (start menu)
///   - Win key       (start menu / task view)
///   - Ctrl+Shift+Esc (task manager)
/// </summary>
public ref class KeyboardHook
{
public:
    static bool Install(System::IntPtr hwndNotepad);
    static void Uninstall();
    static bool IsInstalled();
    static void Suspend();   // temporarily allow keys (e.g. when user types an answer)
    static void Resume();

private:
    static HHOOK s_hHook;
    static gcroot<HWND> s_targetHwnd;
    static bool s_suspended;

    static LRESULT CALLBACK LowLevelKeyboardProc(int nCode, WPARAM wParam, LPARAM lParam);
};

} // namespace FsHook
