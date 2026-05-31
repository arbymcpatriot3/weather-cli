; Clean Shot — Inno Setup Script
; Blue Collar Nation LLC — cleanshothq.com
; Version 3.0.13

#define AppName "Clean Shot"
#define AppVersion "3.0.13"
#define AppPublisher "Blue Collar Nation LLC"
#define AppURL "https://cleanshothq.com"
#define AppExeName "cleanshot.exe"

[Setup]
AppId={{A3F2C8B1-4D7E-4A9F-B6C2-8E1D3A5F7B4E}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} v{#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL=mailto:support@cleanshothq.com
AppUpdatesURL={#AppURL}
DefaultDirName={localappdata}\Programs\Clean Shot
DefaultGroupName={#AppName}
AllowNoIcons=yes
; No admin required — installs to user's AppData
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist
OutputBaseFilename=CleanShotSetup
SetupIconFile=..\assets\cleanshot.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
WizardImageStretch=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Windows 10 / 11 minimum
MinVersion=10.0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &Desktop shortcut"; GroupDescription: "Additional shortcuts:"
Name: "addtopath";   Description: "Add cleanshot to &PATH (run from any terminal)"; GroupDescription: "Command line:"; Flags: checkedonce

[Files]
Source: "dist\cleanshot.exe";          DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\cleanshot.ico";     DestDir: "{app}"; Flags: ignoreversion
Source: "..\assets\CleanShotHQ_Flyer_v9.pdf"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\cleanshot.ico"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{commondesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; IconFilename: "{app}\cleanshot.ico"; Tasks: desktopicon

[Registry]
; Add install dir to user PATH when task is selected
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; \
  ValueData: "{olddata};{app}"; Check: not IsInPath('{app}'); Tasks: addtopath

[Code]
function IsInPath(Dir: string): Boolean;
var
  Path: string;
begin
  if RegQueryStringValue(HKCU, 'Environment', 'Path', Path) then
    Result := Pos(LowerCase(Dir), LowerCase(Path)) > 0
  else
    Result := False;
end;

[Run]
; Launch Clean Shot after install
Filename: "{app}\{#AppExeName}"; \
  Description: "Launch {#AppName} now"; \
  Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
