; Inno Setup script for FamilySafety
; Compile with: iscc installer\FamilySafety.iss
;
; Output: installer\Output\FamilySafetySetup-1.0.0.exe
;
; Note: this installer ONLY places files. Configuration (backendUrl + parent
; password) is done by the parent running FsConfigUI.exe after install —
; either by the desktop shortcut, or manually via:
;   PS> .\installer\Install-FamilySafety.ps1 -BackendUrl "http://host:8000"
;
; Do NOT add a [Run] step that invokes scripts\Install.ps1 here — that
; file does not exist and the legacy reference was the source of bugs.

[Setup]
AppName=FamilySafety Agent
AppVersion=1.0.0
DefaultDirName={autopf}\FamilySafety
DefaultGroupName=FamilySafety
OutputBaseFilename=FamilySafetySetup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=admin
UninstallDisplayIcon={app}\FsTray.exe
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\src\FsWatchdogService\bin\Release\net8.0-windows\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "..\src\FsAgent\bin\Release\net8.0-windows\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "..\src\FsMonitor\bin\Release\net8.0-windows\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "..\src\FsQuiz\bin\Release\net8.0-windows\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "..\src\FsTray\bin\Release\net8.0-windows\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "..\src\FsCommon\bin\Release\net8.0-windows\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "..\src\FsConfigUI\bin\Release\net8.0-windows\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "..\src\FsHook\bin\Release\net8.0-windows\FsHook.dll"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{commondesktop}\FamilySafety 家长配置"; Filename: "{app}\FsConfigUI.exe"; IconFilename: "{app}\FsTray.exe"; Comment: "修改 FamilySafety 后台地址和重置家长密码"
Name: "{group}\FamilySafety 家长配置"; Filename: "{app}\FsConfigUI.exe"; IconFilename: "{app}\FsTray.exe"

[UninstallRun]
; Best-effort: try to stop the service on uninstall. The actual cleanup of
; the service registration is done by Uninstall-FamilySafety.ps1, which the
; user runs separately. sc.exe here just stops a running service so the
; uninstaller can replace its binary without leaving orphaned children.
Filename: "sc.exe"; Parameters: "stop FamilySafety"; Flags: runhidden; RunOnceId: "FsStopSvc"