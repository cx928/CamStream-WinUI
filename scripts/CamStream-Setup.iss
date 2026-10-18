#define AppName "CamStream"
#define AppPublisher "CamStream"
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#define StageDir "..\artifacts\stage"
[Setup]
AppId={{8145B723-31E5-4A8B-A355-69DBE0C3A001}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL=https://space.bilibili.com/1765875510
AppSupportURL=https://www.xiaorin.cn
DefaultDirName={autopf}\CamStream
DefaultGroupName=CamStream
UninstallDisplayIcon={app}\CamStream.WinUI.exe
ArchitecturesInstallIn64BitMode=x64
ArchitecturesAllowed=x64
PrivilegesRequired=admin
OutputDir=..\artifacts
OutputBaseFilename=CamStream-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
SetupLogging=yes
[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加快捷方式："; Flags: unchecked
[Files]
Source: "{#StageDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
[Icons]
Name: "{group}\CamStream"; Filename: "{app}\CamStream.WinUI.exe"
Name: "{autodesktop}\CamStream"; Filename: "{app}\CamStream.WinUI.exe"; Tasks: desktopicon
[Run]
Filename: "{app}\WindowsAppRuntimeInstall-x64.exe"; Parameters: "/quiet /norestart"; StatusMsg: "正在安装 Windows App Runtime…"; Flags: waituntilterminated; Check: not IsRuntimeInstalled
Filename: "{app}\CamStream.WinUI.exe"; Description: "启动 CamStream"; Flags: postinstall nowait skipifsilent
[Code]
function IsRuntimeInstalled: Boolean;
var Version: String;
begin
  Result := RegQueryStringValue(HKLM64, 'SOFTWARE\Microsoft\WindowsAppRuntime\InstalledVersions\1.6\x64', 'Version', Version);
  if not Result then Result := RegQueryStringValue(HKCU64, 'SOFTWARE\Microsoft\WindowsAppRuntime\InstalledVersions\1.6\x64', 'Version', Version);
end;
