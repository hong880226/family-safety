#include "TaskManagerBlocker.h"
#include <Windows.h>

using namespace FsHook;

static const wchar_t* kPolicyKey =
    L"Software\\Microsoft\\Windows\\CurrentVersion\\Policies\\System";

bool TaskManagerBlocker::Block()
{
    HKEY hKey;
    LONG r = RegCreateKeyExW(HKEY_CURRENT_USER, kPolicyKey, 0, NULL,
        REG_OPTION_NON_VOLATILE, KEY_SET_VALUE, NULL, &hKey, NULL);
    if (r != ERROR_SUCCESS) return false;

    DWORD val = 1;
    r = RegSetValueExW(hKey, L"DisableTaskMgr", 0, REG_DWORD,
        (const BYTE*)&val, sizeof(val));
    RegCloseKey(hKey);
    return r == ERROR_SUCCESS;
}

bool TaskManagerBlocker::Unblock()
{
    HKEY hKey;
    LONG r = RegOpenKeyExW(HKEY_CURRENT_USER, kPolicyKey, 0, KEY_SET_VALUE, &hKey);
    if (r != ERROR_SUCCESS) return true;  // already absent
    RegDeleteValueW(hKey, L"DisableTaskMgr");
    RegCloseKey(hKey);
    return true;
}

bool TaskManagerBlocker::IsBlocked()
{
    HKEY hKey;
    LONG r = RegOpenKeyExW(HKEY_CURRENT_USER, kPolicyKey, 0, KEY_READ, &hKey);
    if (r != ERROR_SUCCESS) return false;
    DWORD val = 0, sz = sizeof(val);
    r = RegQueryValueExW(hKey, L"DisableTaskMgr", NULL, NULL, (LPBYTE)&val, &sz);
    RegCloseKey(hKey);
    return (r == ERROR_SUCCESS && val == 1);
}
