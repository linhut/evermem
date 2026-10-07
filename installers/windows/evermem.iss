; 恒忆 Evermem 安装版（Inno Setup）—— 安装向导 / 开始菜单快捷方式 / 卸载 /
; 卸载时询问是否保留记忆数据（%APPDATA%\EvermemData）。
;
; 构建（路径按你本机实际位置传参，不绑定任何盘符）：
;   ISCC.exe evermem.iss /DMyAppVersion="0.2.9" /DMySourceDir="<仓库>\dist\Evermem" /DMyOutputDir="<仓库>\dist"
; 数据策略：数据恒在 %APPDATA%\EvermemData（paths.py 安装版默认数据根），与程序目录分离；
; 卸载默认保留数据（六-6：卸载页询问，选择"否"即保留，重装继续使用）。

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#ifndef MySourceDir
  #define MySourceDir "..\..\dist\Evermem"
#endif
#ifndef MyOutputDir
  #define MyOutputDir "..\..\dist"
#endif

; AppId 必须固定：更新识别、注册表痕迹都靠它（切勿每次发版改 GUID）
#define MyAppId "{{8C1E3A5B-2D4F-4E6A-9B7C-1D2E3F4A5B6C}}"

[Setup]
AppId={#MyAppId}
AppName=恒忆 Evermem
AppVersion={#MyAppVersion}
AppVerName=恒忆 Evermem {#MyAppVersion}
AppPublisher=Jose-AI
AppPublisherURL=https://www.linhut.cn
AppSupportURL=https://github.com/linhut/evermem
AppUpdatesURL=https://github.com/linhut/evermem/releases
DefaultDirName={autopf}\Evermem
DefaultGroupName=恒忆 Evermem
DisableProgramGroupPage=yes
OutputDir={#MyOutputDir}
OutputBaseFilename=Evermem-setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; 品牌图标：安装向导标题栏图标 + 程序卸载项图标源；指向仓库 assets/ 的多尺寸 ICO
SetupIconFile=..\..\assets\icon.ico
; 向导横幅（左侧大图）与右上角小图：PNG 透明底，Inno Setup 6.5.2+ 支持；CI 使用 choco 安装的 6.7.x。
; 尺寸：横幅 246x471（比例 164:314，已按高 DPI 建议放大），小图 147x147（正方形）。
WizardImageFile=wizard-image.png
WizardSmallImageFile=wizard-small-image.png
; 卸载程序名（update.py 安装版检测依赖 unins000.exe 与 install.marker 双保险）
UninstallDisplayIcon={app}\Evermem.exe
UninstallDisplayName=恒忆 Evermem
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
; 安装版更新时主进程先退出再静默安装，这里兜底：exe 被占用时先关应用
SetupMutex=EvermemSetupMutex

[Languages]
; 语言文件内嵌进仓库（installers/windows/languages/）：CI 的 choco Inno 安装不带 Languages 目录，
; 用 compiler: 前缀（安装目录内）会找不到。English 是 Inno 内置默认，用 Default.isl。
Name: "chinesesimplified"; MessagesFile: "languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; 排除开发/调试残留：不随安装包分发（防御纵深，onedir 目录理论上只有运行时文件）
Source: "{#MySourceDir}\*"; DestDir: "{app}"; Excludes: "*.log,index.json,harvest_state.json,pmem_config.json,pmem_backup.json,update_state.json"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\恒忆 Evermem"; Filename: "{app}\Evermem.exe"
Name: "{group}\官网"; Filename: "https://www.linhut.cn"
Name: "{autodesktop}\恒忆 Evermem"; Filename: "{app}\Evermem.exe"; Tasks: desktopicon

[Registry]
; 记录安装版信息（paths.py 安装版检测辅助；数据根仍由代码按 marker 推断）
Root: HKCU; Subkey: "Software\Evermem"; ValueType: string; ValueName: "InstallDir"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Evermem"; ValueType: string; ValueName: "DataDir"; ValueData: "{userappdata}\EvermemData"; Flags: uninsdeletekey

[Run]
Filename: "{app}\Evermem.exe"; Description: "{cm:LaunchProgram,恒忆 Evermem}"; Flags: nowait postinstall skipifsilent

[Code]
// 安装完成：写 install.marker（paths.py 判定"安装版"→ 数据根走 %APPDATA%\EvermemData）
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
    SaveStringToFile(ExpandConstant('{app}\install.marker'), 'installer', False);
end;

// 卸载：询问是否删除记忆数据（默认保留——重装/换电脑前误删不可恢复）
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
  Msg: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    DataDir := ExpandConstant('{userappdata}\EvermemData');
    if DirExists(DataDir) then
    begin
      Msg := MsgBox(
        '是否同时删除记忆数据？' + #13#10 + #13#10 + DataDir + #13#10 + #13#10 +
        '选择"是"将永久删除全部记忆与经验数据，无法恢复；' + #13#10 +
        '选择"否"保留数据，重新安装后继续使用。' + #13#10 + #13#10 +
        '（数据不含任何程序文件）',
        mbConfirmation, MB_YESNO or MB_DEFBUTTON2);
      if Msg = IDYES then
        DelTree(DataDir, True, True, False);
    end;
  end;
end;