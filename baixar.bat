@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "APP_PYTHON="

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" --version >nul 2>&1
    if not errorlevel 1 set "APP_PYTHON=.venv\Scripts\python.exe"
)

if not defined APP_PYTHON (
    py -3 --version >nul 2>&1
    if not errorlevel 1 set "APP_PYTHON=py -3"
)

if not defined APP_PYTHON (
    python --version >nul 2>&1
    if not errorlevel 1 set "APP_PYTHON=python"
)

if not defined APP_PYTHON (
    echo Python não foi encontrado. Instale o Python 3.10 ou mais recente.
    echo Download oficial: https://www.python.org/downloads/windows/
    pause
    exit /b 1
)

%APP_PYTHON% -c "import yt_dlp, rich, questionary" >nul 2>&1
if errorlevel 1 (
    echo Instalando as dependências necessárias pela primeira vez...
    %APP_PYTHON% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Não foi possível instalar as dependências.
        pause
        exit /b 1
    )
)

if /i "%~1"=="--check" (
    %APP_PYTHON% -c "import yt_dlp; print('Iniciador verificado. yt-dlp ' + yt_dlp.version.__version__)"
    exit /b 0
)

echo Verificando atualizações do motor de download...
%APP_PYTHON% -m pip install --disable-pip-version-check --quiet --upgrade yt-dlp
if errorlevel 1 echo Aviso: não foi possível verificar atualizações. Continuando com a versão instalada.

%APP_PYTHON% interface.py
if errorlevel 1 pause
