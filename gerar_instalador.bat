@echo off
rem Gera o instalador do PC Estribado em instalador\saida
cd /d "%~dp0"
python -m pip install -r requirements.txt
python gerar_icone.py || goto erro
python -m PyInstaller --noconfirm --clean --onedir --windowed --uac-admin --name "PC Estribado" --icon icone.ico --add-data "web;web" app.py || goto erro

set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" (
  echo Inno Setup nao encontrado. Instale com: winget install JRSoftware.InnoSetup
  goto erro
)
"%ISCC%" instalador.iss || goto erro
echo.
echo Pronto! O instalador esta em: %~dp0instalador\saida
pause
exit /b 0

:erro
echo.
echo Deu erro. Veja as mensagens acima.
pause
exit /b 1
