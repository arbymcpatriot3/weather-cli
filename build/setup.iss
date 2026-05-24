; CleanShotSetup.iss -- Inno Setup 6 script for Clean Shot
; Run: "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" setup.iss
; Output: ..\dist\CleanShotSetup.exe

#define AppName      "Clean Shot"
#define AppVersion   "3.0.6"
#define AppPublisher "CleanShotHQ LLC"
#define AppURL       "https://cleanshothq.com"
#define AppExeName   "cleanshot.exe"
#define ExeSource    "..\dist\cleanshot.exe"
#define LicenseFile  "..\assets\LICENSE.txt"
#define BannerBmp    "..\assets\wizard_banner.bmp"
#define SmallBmp     "..\assets\wizard_icon.bmp"
#define AppIcon      "..\assets\cleanshot.ico"

[Setup]
; Unique GUID -- do NOT change after first release (controls upgrades/uninstall)
AppId={{F3A47B12-8C9E-4D05-B621-E7F2A30C1587}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL=mailto:support@cleanshothq.com
AppUpdatesURL={#AppURL}

DefaultDirName={autopf}\Clean Shot
DefaultGroupName={#AppName}
AllowNoIcons=no

LicenseFile={#LicenseFile}
SetupIconFile={#AppIcon}
WizardStyle=classic
WizardImageFile={#BannerBmp}
WizardSmallImageFile={#SmallBmp}

OutputDir=..\dist
OutputBaseFilename=CleanShotSetup
Compression=lzma2/ultra64
SolidCompression=yes

PrivilegesRequiredOverridesAllowed=dialog

VersionInfoVersion={#AppVersion}.0
VersionInfoCompany={#AppPublisher}
VersionInfoDescription={#AppName} Installer -- Road Intelligence for Truck Drivers
VersionInfoCopyright=Copyright (C) 2026 CleanShotHQ LLC

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
; Desktop shortcut -- checked ON by default
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#ExeSource}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Comment: "Road intelligence for truck drivers"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Comment: "Road intelligence for truck drivers"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(AppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
