#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif

#define AppName "JTI Auto Bid Builder"
#define AppExeName "AutoBidBuilder.exe"

[Setup]
AppId={{D75E4A2B-EC86-4E3A-9F53-561B6AE46983}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=JTI Millwork / CaMaLabs
DefaultDirName={localappdata}\JTI\AutoBidBuilder
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist\installer
OutputBaseFilename=JTI_Auto_Bid_Builder_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\{#AppExeName}
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\Auto Bid Builder"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch Auto Bid Builder"; Flags: nowait postinstall skipifsilent
