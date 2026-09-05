; Font Wizard — Inno Setup installer script.
; Requires Inno Setup 6 (ISCC.exe). Built via App\build.bat.
; Source exe (dist\FontWizard.exe) is produced by PyInstaller first.

#define MyAppName "Font Wizard"
#define MyAppExeName "FontWizard.exe"
#ifndef MyAppVersion
#define MyAppVersion "3.0.0"
#endif
#ifndef MyAppVersionFull
#define MyAppVersionFull "3.0.0.0"
#endif
#define MyAppPublisher "karnyadavdev"
#define MyAppURL "https://github.com/karnyadavdev/fontwizard"

[Setup]
AppId={{8980A84E-5425-40CF-9222-DD3BD3C0F70E}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={autopf}\Font Wizard
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE
SetupIconFile=src\assets\font-wizard.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
OutputDir=dist
OutputBaseFilename=FontWizard-Setup-{#MyAppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
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

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\third-party-notices.txt"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
