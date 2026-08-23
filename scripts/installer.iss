; ITOps Hub — Inno Setup installer script (v1.5)
; Build on windows-latest (or a local Windows machine) with:
;   1. pyinstaller itopshub.spec --noconfirm        -> dist\ITOpsHub\
;   2. iscc scripts\installer.iss                   -> dist\ITOpsHub-Setup.exe
; The GitHub Actions build-windows workflow automates both steps.

#define MyAppName "ITOps Hub"
#define MyAppVersion "1.5.0"
#define MyAppPublisher "ITOps Hub Contributors"
#define MyAppExeName "ITOpsHub.exe"

[Setup]
AppId={{7C1B6E9A-52C4-4B7D-9A34-ITOPSHUB15}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=dist
OutputBaseFilename=ITOpsHub-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
; Unsigned builds (zero-cost budget): SmartScreen will warn on first run.
; Add SignTool configuration here once a certificate is approved.

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "dist\ITOpsHub\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; User data (database, logs, exports) lives in %LOCALAPPDATA%\ITOpsHub and is
; deliberately NOT removed by the uninstaller — it may contain history the
; user wants to keep. The folder is mentioned in the uninstall notes instead.
Type: filesandordirs; Name: "{app}"
