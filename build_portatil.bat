@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
echo ============================================================
echo SEEP - Criar versao portatil (Python embutido)
echo ============================================================
echo Isso baixa um Python 3.12 "embutido" (nao precisa instalar nada
echo no Windows) e coloca TODAS as bibliotecas dentro da pasta
echo python-embed\ - sem adivinhacao de import, porque leva tudo.
echo.
echo Precisa de internet SO NESTA MAQUINA, SO AGORA. A pasta gerada
echo depois roda sem internet em qualquer PC Windows.
echo.

set PYVER=3.12.7
set PYURL=https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-embed-amd64.zip
set GETPIPURL=https://bootstrap.pypa.io/get-pip.py

if exist python-embed (
  echo python-embed ja existe. Apagando para recomecar do zero...
  rmdir /s /q python-embed
)
mkdir python-embed

echo [1/5] Baixando Python %PYVER% embutido...
curl -L -o python-embed.zip %PYURL%
if errorlevel 1 goto :erro_internet

echo [2/5] Extraindo...
tar -xf python-embed.zip -C python-embed
if errorlevel 1 goto :erro

REM O Python embutido vem com o site-packages desligado por padrao.
REM Precisa habilitar editando o arquivo ._pth para o pip funcionar.
echo [3/5] Habilitando site-packages no Python embutido...
for %%f in (python-embed\python*._pth) do (
  powershell -Command "(Get-Content '%%f') -replace '#import site', 'import site' | Set-Content '%%f'"
)

echo [4/5] Instalando pip dentro do Python embutido...
curl -L -o get-pip.py %GETPIPURL%
if errorlevel 1 goto :erro_internet
python-embed\python.exe get-pip.py --no-warn-script-location
if errorlevel 1 goto :erro

echo [5/5] Instalando as bibliotecas do projeto (Flask, Pandapower, etc.)...
python-embed\python.exe -m pip install --no-warn-script-location -r requirements.txt
if errorlevel 1 goto :erro

del python-embed.zip get-pip.py 2>nul

echo.
echo ============================================================
echo Pronto! Pasta portatil criada.
echo ============================================================
echo Para rodar aqui mesmo:   run_portatil.bat
echo.
echo Para levar para OUTRA maquina Windows (sem instalar nada la):
echo   Copie a pasta do projeto INTEIRA (incluindo python-embed\)
echo   e rode run_portatil.bat na maquina nova. Nao precisa de
echo   internet nem de Python instalado la.
pause
exit /b 0

:erro_internet
echo.
echo ERRO: nao consegui baixar o Python/pip. Precisa de internet
echo funcionando NESTA maquina para montar a versao portatil
echo (so nesta etapa - depois de pronta, roda sem internet).
pause
exit /b 1

:erro
echo.
echo ERRO durante a montagem. Copie o texto do terminal e envie
echo para analise.
pause
exit /b 1
