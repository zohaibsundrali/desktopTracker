; ============================================================
;  Developer Tracker - Inno Setup installer script
;  Build: open this file in Inno Setup Compiler and press "Compile"
;         (or:  iscc installer.iss  from the command line)
;  Produces:  Output\DeveloperTracker-Setup.exe
; ============================================================

#define MyAppName "Developer Tracker"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Your Company"
#define MyAppExeName "DeveloperTracker.exe"

[Setup]
AppId={{8F3C1A20-9E4B-4C77-9B1D-DEV-TRACKER-0001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=DeveloperTracker-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
; Installs into Program Files -> needs admin. Use "lowest" for per-user install.
PrivilegesRequired=admin
; SetupIconFile=app.ico          ; uncomment if you add an app.ico

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startupicon"; Description: "Start Developer Tracker automatically when I log in"; GroupDescription: "Startup:"; Flags: unchecked

[Files]
; Grab the ENTIRE PyInstaller onedir output.
Source: "dist\DeveloperTracker\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startupicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
