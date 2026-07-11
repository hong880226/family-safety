; Inno Setup script for FamilySafety
; Compile with: iscc installer\FamilySafety.iss
;
; Output: installer\Output\FamilySafetySetup-1.0.0.exe

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
; Requires binaries already built (`dotnet build -c Release`)
Source: "..\src\FsWatchdog\bin\Release\net8.0-windows\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "..\src\FsWatchdogService\bin\Release\net8.0-windows\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "..\src\FsAgent\bin\Release\net8.0-windows\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "..\src\FsMonitor\bin\Release\net8.0-windows\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "..\src\FsQuiz\bin\Release\net8.0-windows\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "..\src\FsTray\bin\Release\net8.0-windows\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "..\src\FsCommon\bin\Release\net8.0-windows\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs
Source: "..\src\FsHook\bin\Release\net8.0-windows\FsHook.dll"; DestDir: "{app}"; Flags: ignoreversion

[Run]
; Run the PowerShell installer to set up service + ACL
Filename: "{cmd}"; Parameters: "/c powershell -ExecutionPolicy Bypass -File ""{app}\scripts\Install.ps1"" -BackendUrl ""{code:GetBackendUrl}"""; Flags: runhidden waituntilterminate

[Code]
var BackendUrl: String;

function GetBackendUrl(Param: String): String;
begin
  Result := BackendUrl;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    { Prompt parent for backend URL during install }
    if not InputQuery('FamilySafety Setup',
      'Enter your FamilySafety backend URL (e.g. http://192.168.1.10:8000):',
      BackendUrl) then
    begin
      MsgBox('Backend URL is required.', mbError, MB_OK);
      Abort;
    end;
  end;
end;
