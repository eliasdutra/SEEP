@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo SEEP - Setup Windows
echo ============================================================

py -3.12 --version >nul 2>&1
if errorlevel 1 (
  echo Python 3.12 nao encontrado.
  echo Instale com:
  echo   winget install -e --id Python.Python.3.12
  echo Depois feche e abra o VS Code e execute este arquivo novamente.
  pause
  exit /b 1
)

if not exist .venv (
  echo [1/3] Criando ambiente virtual...
  py -3.12 -m venv .venv
) else (
  echo [1/3] Ambiente .venv ja existe.
)

echo [2/3] Atualizando pip...
.venv\Scripts\python.exe -m pip install --upgrade pip
if errorlevel 1 goto :erro

echo [3/3] Instalando dependencias...
.venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 goto :erro

echo.
echo Setup concluido.
echo Execute run_windows.bat ou use:
echo   .venv\Scripts\python.exe app.py
pause
exit /b 0

:erro
echo.
echo ERRO durante a instalacao. Copie o terminal e envie para analise.
pause
exit /b 1
