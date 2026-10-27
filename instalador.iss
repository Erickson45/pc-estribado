; Instalador do PC Estribado (Inno Setup 6.7+). Gerado pelo gerar_instalador.bat.
#define Versao "1.0.0"
#define Nome "PC Estribado"
#define Exe "PC Estribado.exe"

[Setup]
AppId={{8F3C2A71-5B4D-4E2A-9C6F-7D1E0B9A4C55}
AppName={#Nome}
AppVersion={#Versao}
AppVerName={#Nome} {#Versao}
AppPublisher=Erickson Queiroz
AppPublisherURL=https://github.com/Erickson45/pc-estribado
AppSupportURL=https://github.com/Erickson45/pc-estribado/issues
AppUpdatesURL=https://github.com/Erickson45/pc-estribado/releases
VersionInfoVersion={#Versao}
VersionInfoDescription={#Nome} - limpeza, saúde e atualizações do Windows
DefaultDirName={autopf}\{#Nome}
DefaultGroupName={#Nome}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
OutputDir=instalador\saida
OutputBaseFilename=PC Estribado {#Versao} - Instalador
SetupIconFile=icone.ico
UninstallDisplayIcon={app}\{#Exe}
UninstallDisplayName={#Nome}
WizardStyle=modern dark
WizardImageFile=instalador\lateral100.bmp,instalador\lateral150.bmp,instalador\lateral200.bmp
WizardSmallImageFile=instalador\icone100.bmp,instalador\icone150.bmp,instalador\icone200.bmp
Compression=lzma2/ultra64
SolidCompression=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Messages]
pt.WelcomeLabel1=Bem-vindo ao {#Nome}!
pt.WelcomeLabel2=Vamos deixar seu Windows leve, liso e sem travar.%n%nO {#Nome} vai ser instalado no seu computador, com atalho no menu Iniciar. Ele sempre abre como administrador, pra todas as ferramentas funcionarem.%n%nFeche outros programas antes de continuar.
pt.FinishedHeadingLabel=Prontinho, tá estribado!

[Tasks]
Name: "atalho"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "dist\{#Nome}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#Nome}"; Filename: "{app}\{#Exe}"; Comment: "Limpeza, saúde e atualizações do Windows"
Name: "{autodesktop}\{#Nome}"; Filename: "{app}\{#Exe}"; Tasks: atalho

[Run]
; runascurrentuser: abre com o admin do instalador (sem isso o Windows recusa com erro 740, porque o programa exige admin)
Filename: "{app}\{#Exe}"; Description: "Abrir o {#Nome} agora"; Flags: nowait postinstall skipifsilent runascurrentuser
; atualização automática roda o instalador em modo silencioso; no fim, reabre o programa sozinho
Filename: "{app}\{#Exe}"; Flags: nowait skipifnotsilent runascurrentuser

[UninstallRun]
; tira a manutenção automática do Agendador de Tarefas antes de apagar os arquivos
Filename: "{app}\{#Exe}"; Parameters: "--desinstalar"; Flags: runhidden waituntilterminated; RunOnceId: "RemoverTarefa"
