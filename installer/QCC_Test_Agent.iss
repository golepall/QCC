; QCC 离线测试工作台 - Inno Setup 安装脚本
; 版本: 1.1.0
; 日期: 2026-07-15

#define MyAppName "QCC 离线测试工作台"
#define MyAppNameEn "QCC Test Agent"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "QCC 测试团队"
#define MyAppURL "https://qcc.example.com"
#define MyAppExeName "QCC_Test_Agent.exe"

[Setup]
; 注册表信息
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; 安装目录
DefaultDirName={autopf}\QCC_Test_Agent
DefaultGroupName={#MyAppName}
LicenseFile=

; 安装程序选项
OutputDir=d:\QCC\installer\output
OutputBaseFilename=QCC_Test_Agent_Setup_{#MyAppVersion}
SetupIconFile=d:\QCC\installer\icon.ico
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern

; 系统要求
MinVersion=10.0
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; 语言
ShowLanguageDialog=yes
UsePreviousLanguage=no

; 卸载
UninstallDisplayName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}

[Languages]
Name: "chinesesimplified"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "quicklaunchicon"; Description: "{cm:CreateQuickLaunchIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked; OnlyBelowVersion: 6.1

[Files]
; 主程序
Source: "d:\QCC\test_engine\QCC_Test_Agent_Portable\Agent\QCC_Test_Agent.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "d:\QCC\test_engine\QCC_Test_Agent_Portable\Agent\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; 测试数据模板
Source: "d:\QCC\installer\templates\*"; DestDir: "{app}\TestData"; Flags: ignoreversion recursesubdirs createallsubdirs

; 文档
Source: "d:\QCC\installer\docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
; 开始菜单
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{group}\使用说明"; Filename: "{app}\docs\README.txt"

; 桌面快捷方式
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

; 快速启动栏
Name: "{userappdata}\Microsoft\Internet Explorer\Quick Launch\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: quicklaunchicon

[Run]
; 安装完成后运行
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[Registry]
; 注册文件关联
Root: HKCR; Subkey: ".qccresult"; ValueType: string; ValueName: ""; ValueData: "QCCResultFile"; Flags: uninsdeletevalue
Root: HKCR; Subkey: "QCCResultFile"; ValueType: string; ValueName: ""; ValueData: "QCC 测试结果文件"; Flags: uninsdeletekey
Root: HKCR; Subkey: "QCCResultFile\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\{#MyAppExeName},0"
Root: HKCR; Subkey: "QCCResultFile\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\{#MyAppExeName}"" ""%1"""

; 注册环境变量
Root: HKLM; Subkey: "SYSTEM\CurrentControlSet\Control\Session Manager\Environment"; ValueType: expandsz; ValueName: "QCC_TEST_AGENT"; ValueData: "{app}"; Flags: uninsdeletevalue

[UninstallDelete]
; 卸载时删除的文件
Type: filesandordirs; Name: "{app}\logs"
Type: filesandordirs; Name: "{app}\temp"

[Code]
// 检查是否已安装
function IsAppInstalled(): Boolean;
begin
  Result := RegKeyExists(HKLM, 'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\{#SetupSetting("AppId")}_is1');
end;

// 安装前检查
function InitializeSetup(): Boolean;
begin
  Result := True;
  
  // 检查是否已运行
  if IsAppInstalled() then
  begin
    if MsgBox('检测到已安装 {#MyAppName}，是否继续安装？这将覆盖现有安装。', 
              mbConfirmation, MB_YESNO) = IDNO then
    begin
      Result := False;
      Exit;
    end;
  end;
end;

// 安装完成
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // 创建测试数据目录
    CreateDir(ExpandConstant('{app}\TestData'));
    CreateDir(ExpandConstant('{app}\logs'));
    CreateDir(ExpandConstant('{app}\temp'));
  end;
end;

[Messages]
; 自定义中文消息
chinesesimplified.WelcomeLabel1=欢迎使用 [name] 安装向导
chinesesimplified.WelcomeLabel2=这将安装 [name/ver] 到您的计算机。%n%n建议在安装前关闭所有其他应用程序。
chinesesimplified.FinishedLabel=安装程序已完成 [name] 的安装。%n%n您可以通过桌面上的快捷方式启动程序。
