# -*- mode: python ; coding: utf-8 -*-
# Spec do PyInstaller para empacotar o SEEP como uma pasta autocontida
# (modo --onedir), sem depender de Python instalado na máquina de destino.
#
# IMPORTANTE: isso precisa ser executado NA MÁQUINA WINDOWS onde o
# .venv já está funcionando (setup_windows.bat já rodado com sucesso).
# PyInstaller não faz cross-compile: rodar isso aqui não gera um .exe
# usável em outra máquina/SO.
#
# Uso:
#   .venv\Scripts\python.exe -m PyInstaller seep.spec --noconfirm
#
# Resultado: pasta dist\SEEP\ — copie essa pasta inteira pra outra
# máquina Windows e rode SEEP.exe direto, sem instalar Python lá.

from PyInstaller.utils.hooks import collect_all

datas = [("templates", "templates"), ("static", "static")]
binaries = []
hiddenimports = [
    "pandapower.shortcircuit",
    "pandapower.shortcircuit.calc_sc",
    "pandapower.pd2ppc",
    "pandapower.pd2ppc_zero",
    "pandapower.pypower.makeYbus",
    "scipy.special._cdflib",
    "scipy.sparse.csgraph._validation",
]

# pandapower e plotly carregam dados/arquivos internos (JSON, esquemas) que o
# PyInstaller não detecta sozinho — collect_all pega módulo + dados + imports
# escondidos de uma vez, evitando ficar caçando erro um por um na mão.
for pkg in ("pandapower", "plotly", "pandas", "scipy", "networkx"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SEEP",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # mantém o terminal aberto — ajuda a ver erro se algo falhar
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="SEEP",
)
