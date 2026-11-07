; Skiffdrop installer for Inno Setup 6, built by packaging/build.py.
; Installs for the current user only (no admin prompt), into
; %LOCALAPPDATA%\Programs\Skiffdrop. Received files stay in Downloads\Skiffdrop.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{9C4E2A71-5B3D-4F8E-A6C2-1D7B9E3F5A08}
AppName=Skiffdrop
AppVersion={#AppVersion}
AppVerName=Skiffdrop {#AppVersion}
AppPublisher=Niro54321
AppPublisherURL=https://github.com/Niro54321/Skiffdrop
AppSupportURL=https://github.com/Niro54321/Skiffdrop/issues
AppUpdatesURL=https://github.com/Niro54321/Skiffdrop/releases
DefaultDirName={autopf}\Skiffdrop
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=Skiffdrop-Setup-{#AppVersion}
SetupIconFile=..\build\skiffdrop.ico
UninstallDisplayIcon={app}\Skiffdrop.exe
UninstallDisplayName=Skiffdrop
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no

[Tasks]
Name: "sendto"; Description: "Add Skiffdrop to the Explorer ""Send to"" menu"
Name: "startup"; Description: "Start Skiffdrop when Windows starts (it waits in the tray)"; Flags: unchecked
Name: "desktopicon"; Description: "Create a desktop shortcut"; Flags: unchecked

[Files]
Source: "..\dist\Skiffdrop\*"; DestDir: "{app}"; Excludes: "skiffdrop-selftest.exe"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Skiffdrop"; Filename: "{app}\Skiffdrop.exe"
Name: "{autodesktop}\Skiffdrop"; Filename: "{app}\Skiffdrop.exe"; Tasks: desktopicon
Name: "{usersendto}\Skiffdrop (to phone)"; Filename: "{app}\Skiffdrop.exe"; Tasks: sendto

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Skiffdrop"; ValueData: """{app}\Skiffdrop.exe"" --background"; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Skiffdrop.exe"; Description: "Start Skiffdrop now"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/IM Skiffdrop.exe /F"; Flags: runhidden; RunOnceId: "StopSkiffdrop"

[UninstallDelete]
; Settings and the list of allowed phones. Files you received are never touched.
Type: filesandordirs; Name: "{userappdata}\Skiffdrop"

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  { An older Skiffdrop may be running in the tray; close it so its files can be replaced. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM Skiffdrop.exe /F', '', SW_HIDE, ewWaitUntilTerminated, Code);
  Result := '';
end;
