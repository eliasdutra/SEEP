@echo off
cd /d "%~dp0"
if not exist python-embed\python.exe (
  echo python-embed nao encontrado nesta pasta.
  echo Se voce copiou o projeto de outra maquina, confirme que a
  echo pasta python-embed foi copiada junto ^(ela e grande, mas e
  echo o que permite rodar sem instalar Python aqui^).
  echo Se esta e a maquina original, rode build_portatil.bat primeiro.
  pause
  exit /b 1
)
python-embed\python.exe app.py
pause
