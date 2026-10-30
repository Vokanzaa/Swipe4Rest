; Inno Setup script — per-user install, no admin rights needed.
#define AppVersion GetEnv("DS_VERSION")
#if AppVersion == ""
  #define AppVersion "0.1.0"
#endif
#define AppBundle GetEnv("SWIPE4REST_BUNDLE")
#if AppBundle == ""
  #define AppBundle "..\dist\Swipe4Rest"
#endif
#define AppCompression GetEnv("DS_COMPRESSION")
#if AppCompression == ""
  #define AppCompression "lzma2/ultra64"
#endif

[Setup]
AppId={{5869AE85-3CEF-4542-95E8-5FCB23B02A83}
AppName=Swipe4Rest
AppVersion={#AppVersion}
AppPublisher=Vokanzaa
DefaultDirName={localappdata}\Programs\Swipe4Rest
DefaultGroupName=Swipe4Rest
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Swipe4Rest-Setup
SetupIconFile=..\dragshift\assets\dragshift.ico
UninstallDisplayIcon={app}\Swipe4Rest.exe
Compression={#AppCompression}
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=yes
UsePreviousLanguage=no

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[CustomMessages]
en.AutoStart=Start Swipe4Rest when I sign in to Windows
ru.AutoStart=Запускать Swipe4Rest при входе в Windows
en.ContextMenu=Add Swipe4Rest to the right-click menu for files
ru.ContextMenu=Добавить Swipe4Rest в контекстное меню файлов
en.DesktopIcon=Create a desktop shortcut
ru.DesktopIcon=Создать ярлык на рабочем столе
en.LaunchNow=Launch Swipe4Rest now
ru.LaunchNow=Запустить Swipe4Rest

[Tasks]
Name: "autostart"; Description: "{cm:AutoStart}"; Flags: unchecked
Name: "contextmenu"; Description: "{cm:ContextMenu}"; Flags: unchecked
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; Flags: unchecked

[Files]
Source: "{#AppBundle}\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\Swipe4Rest"; Filename: "{app}\Swipe4Rest.exe"
Name: "{autodesktop}\Swipe4Rest"; Filename: "{app}\Swipe4Rest.exe"; Tasks: desktopicon
Name: "{usersendto}\Swipe4Rest"; Filename: "{app}\Swipe4Rest.exe"

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Swipe4Rest"; ValueData: """{app}\Swipe4Rest.exe"" --quiet"; Tasks: autostart; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\*\shell\Swipe4Rest"; ValueType: string; ValueName: "MUIVerb"; ValueData: "Swipe4Rest…"; Tasks: contextmenu; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\*\shell\Swipe4Rest"; ValueType: string; ValueName: "Icon"; ValueData: "{app}\Swipe4Rest.exe"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\*\shell\Swipe4Rest"; ValueType: string; ValueName: "MultiSelectModel"; ValueData: "Player"; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Classes\*\shell\Swipe4Rest\command"; ValueType: string; ValueName: ""; ValueData: """{app}\Swipe4Rest.exe"" ""%1"""; Tasks: contextmenu
Root: HKCU; Subkey: "Software\Swipe4Rest"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Swipe4Rest\Swipe4Rest"; ValueType: string; ValueName: "language"; ValueData: "{language}"; Check: not IsUpdateInstall

[INI]
Filename: "{app}\data\settings.ini"; Section: "General"; Key: "language"; String: "{language}"; Flags: createkeyifdoesntexist

[Run]
Filename: "{app}\Swipe4Rest.exe"; Description: "{cm:LaunchNow}"; Flags: nowait postinstall skipifsilent
Filename: "{app}\Swipe4Rest.exe"; Parameters: "--quiet"; Flags: nowait; Check: IsUpdateInstall

[UninstallRun]
Filename: "{cmd}"; Parameters: "/C taskkill /F /IM Swipe4Rest.exe"; Flags: runhidden; RunOnceId: "KillSwipe4Rest"

[Code]
function IsUpdateInstall: Boolean;
begin
  Result := ExpandConstant('{param:DRAGSHIFTUPDATE|0}') = '1';
end;
