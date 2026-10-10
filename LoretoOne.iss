#define MyAppName "Loreto One"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Loreto Labs"
#define MyAppExeName "LoretoOne.exe"

[Setup]
AppId={{A58E5E25-B2B5-4DA8-99EA-1E47B0F65A52}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\Loreto One
DefaultGroupName=Loreto One
DisableProgramGroupPage=yes
OutputDir=Instalador_Final
OutputBaseFilename=LoretoOne_Setup_1.0.0_x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
MinVersion=10.0.17763
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}
SetupIconFile=assets\loretoone.ico
WizardImageFile=assets\installer-large.bmp
WizardSmallImageFile=assets\installer-small.bmp
CloseApplications=force
RestartApplications=no
UsePreviousAppDir=yes

[Files]
Source: "dist\LoretoOne\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Loreto One"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Loreto One"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el escritorio"; GroupDescription: "Accesos directos:"; Flags: checkedonce

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir Loreto One"; Flags: nowait postinstall skipifsilent
