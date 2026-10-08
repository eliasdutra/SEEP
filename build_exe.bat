@echo off
setlocal
cd /d "%~dp0"
echo ============================================================
echo SEEP - Empacotar como executavel autocontido (PyInstaller)
echo ============================================================
echo Isso precisa ser rodado NESTA maquina, com o .venv ja funcionando
echo (ou seja: depois de setup_windows.bat + run_windows.bat terem
echo  funcionado normalmente pelo menos uma vez).
echo.

if not exist .venv (
  echo .venv nao encontrado. Rode setup_windows.bat primeiro.
  pause
  exit /b 1
)

echo [1/2] Instalando PyInstaller no ambiente virtual...
.venv\Scripts\python.exe -m pip install --upgrade pyinstaller
if errorlevel 1 goto :erro

echo [2/2] Empacotando (isso demora alguns minutos, e o pacote fica grande
echo       por causa do NumPy/SciPy/Pandas - isso e esperado)...
.venv\Scripts\python.exe -m PyInstaller seep.spec --noconfirm
if errorlevel 1 goto :erro

echo.
echo Pronto. A pasta dist\SEEP\ tem tudo que precisa.
echo Copie essa pasta inteira para a outra maquina e rode SEEP.exe direto -
echo nao precisa instalar Python la.
echo.
echo Se quiser manter os ajustes de rele/equipamento ja salvos, copie
echo tambem o arquivo data\protection.db para dentro de dist\SEEP\data\
pause
exit /b 0

:erro
echo.
echo ERRO durante o empacotamento. Copie o texto do terminal e envie
echo para analise - erros de "hidden import" do PyInstoller com o
echo Pandapower/SciPy sao comuns e costumam ter solucao rapida.
pause
exit /b 1
