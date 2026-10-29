; Inno Setup script for SC Shard Status. The installer workflow builds it with:
;   iscc /DAppVersion=1.1.0 installer\sc-shard-status.iss
; after PyInstaller has made dist\SC Shard Status.
;
; Installs for the current Windows user only (no admin prompt) into %LOCALAPPDATA%\Programs\SC Shard Status.
; Settings, readings and reports live in %LOCALAPPDATA%\SC Shard Status, so updates never touch them.
; The app updates itself by running a newer copy of this installer with /SILENT; it then starts the app again.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#define AppName "SC Shard Status"
#define AppExe "SC Shard Status.exe"

[Setup]
AppId={{6C1E3F0A-5B7D-4E2A-9D41-8F3A2C7B5E19}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Aurelius_Draco
AppPublisherURL=https://verseshards.com
AppSupportURL=https://github.com/Aurelius-Draco/sc-shard-status/issues
AppUpdatesURL=https://verseshards.com/app
AppComments=Shard health and what's gone wrong in Star Citizen, in plain English. Fan made, not from CIG.
VersionInfoVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
DisableReadyPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=SC-Shard-Status-Setup-{#AppVersion}
SetupIconFile=..\scstatus\assets\status.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
CloseApplications=force
RestartApplications=no
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Add a desktop shortcut"; GroupDescription: "Shortcuts:"

[InstallDelete]
; Clear out the previous version's libraries so nothing stale is left behind
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\SC Shard Status\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"; Comment: "Shard health and what's gone wrong, while you play"
Name: "{group}\{#AppName} - check"; Filename: "{app}\{#AppExe}"; Parameters: "--check --wait"; Comment: "What's gone wrong in the last 30 minutes"
Name: "{group}\{#AppName} (log only)"; Filename: "{app}\{#AppExe}"; Parameters: "--no-overlay"; Comment: "Without reading the game overlay off the screen"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon; Comment: "Shard health and what's gone wrong, while you play"

[Run]
; Ticked by default on the last page of a normal install
Filename: "{app}\{#AppExe}"; Description: "Start {#AppName} now"; Flags: nowait postinstall skipifsilent
; An update from inside the app runs this installer silently: start the new version again straight away
Filename: "{app}\{#AppExe}"; Parameters: "--after-update"; Flags: nowait skipifnotsilent; Check: LaunchAfterSilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
// /NOLAUNCH (used by the build's own install test) skips starting the app after a silent install
function LaunchAfterSilent: Boolean;
begin
  Result := Pos('/NOLAUNCH', UpperCase(GetCmdTail)) = 0;
end;

// Uninstalling asks whether to keep your readings history and settings (kept unless you say otherwise)
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{localappdata}\{#AppName}');
    if DirExists(DataDir) and not UninstallSilent then
      if MsgBox('Also delete your SC Shard Status settings, readings history and saved reports?' + #13#10#13#10 +
                'They are in ' + DataDir + '. Choose No to keep them for next time.',
                mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
        DelTree(DataDir, True, True, True);
  end;
end;
