; Font Wizard — Inno Setup installer script.
; Requires Inno Setup 6 (ISCC.exe). Built via App\build.bat.
; Source exe (dist\FontWizard.exe) is produced by PyInstaller first.

#define MyAppName "Font Wizard"
#define MyAppExeName "FontWizard.exe"
#ifndef MyAppVersion
#define MyAppVersion "6.0.0"
#endif
#ifndef MyAppVersionFull
#define MyAppVersionFull "6.0.0.0"
#endif
#define MyAppPublisher "karnyadavdev"
#define MyAppURL "https://github.com/karnyadavdev/FontWizard"

[Setup]
AppId={{8980A84E-5425-40CF-9222-DD3BD3C0F70E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
AppComments=Customize Windows 11 & 10 system font completely with 100% system coverage
DefaultDirName={autopf}\Font Wizard
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyMemo=yes
SetupIconFile=src\assets\font-wizard.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=dist
OutputBaseFilename=Font Wizard 6.0 Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern dynamic
WizardImageFile=src\assets\wizard-image.png
WizardImageFileDynamicDark=src\assets\wizard-image.png
WizardSmallImageFile=src\assets\wizard-small.png
WizardSmallImageFileDynamicDark=src\assets\wizard-small.png
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.10240
CloseApplications=yes
RestartApplications=no
VersionInfoVersion={#MyAppVersionFull}
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCopyright=Copyright (c) 2026 {#MyAppPublisher}
VersionInfoOriginalFilename=Font Wizard 6.0 Setup.exe

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\third-party-notices.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; AppUserModelID: "karnyadavdev.FontWizard"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon; AppUserModelID: "karnyadavdev.FontWizard"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent runascurrentuser
