#include "KeyboardHook.h"
#include <msclr\marshal.h>

using namespace FsHook;
using namespace System;

HHOOK KeyboardHook::s_hHook = NULL;
gcroot<HWND> KeyboardHook::s_targetHwnd;
bool KeyboardHook::s_suspended = false;

LRESULT CALLBACK KeyboardHook::LowLevelKeyboardProc(int nCode, WPARAM wParam, LPARAM lParam)
{
    if (nCode != HC_ACTION || s_suspended)
        return CallNextHookEx(s_hHook, nCode, wParam, lParam);

    KBDLLHOOKSTRUCT* p = (KBDLLHOOKSTRUCT*)lParam;
    bool isAlt   = (GetAsyncKeyState(VK_MENU) & 0x8000) != 0;
    bool isCtrl  = (GetAsyncKeyState(VK_CONTROL) & 0x8000) != 0;
    bool isShift = (GetAsyncKeyState(VK_SHIFT) & 0x8000) != 0;
    bool isWin   = (GetAsyncKeyState(VK_LWIN) & 0x8000) != 0
                 || (GetAsyncKeyState(VK_RWIN) & 0x8000) != 0;
    DWORD vk = p->vkCode;

    // Block Alt+F4
    if (isAlt && vk == VK_F4) return 1;
    // Block Alt+Tab, Alt+Esc
    if (isAlt && (vk == VK_TAB || vk == VK_ESCAPE)) return 1;
    // Block Ctrl+Esc, Ctrl+Shift+Esc
    if (isCtrl && vk == VK_ESCAPE) return 1;
    if (isCtrl && isShift && vk == VK_ESCAPE) return 1;
    // Block Win key (down only)
    if (vk == VK_LWIN || vk == VK_RWIN) return 1;

    return CallNextHookEx(s_hHook, nCode, wParam, lParam);
}

bool KeyboardHook::Install(System::IntPtr hwndNotepad)
{
    if (s_hHook != NULL) return true;
    s_targetHwnd = (HWND)hwndNotepad.ToPointer();
    s_hHook = SetWindowsHookEx(WH_KEYBOARD_LL, LowLevelKeyboardProc, NULL, 0);
    return s_hHook != NULL;
}

void KeyboardHook::Uninstall()
{
    if (s_hHook != NULL)
    {
        UnhookWindowsHookEx(s_hHook);
        s_hHook = NULL;
    }
}

bool KeyboardHook::IsInstalled() { return s_hHook != NULL; }
void KeyboardHook::Suspend() { s_suspended = true; }
void KeyboardHook::Resume() { s_suspended = false; }
