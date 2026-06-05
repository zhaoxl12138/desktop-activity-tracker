# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_root = Path.cwd()
stale_onefile_exe = project_root / "dist" / "DayLens.exe"
if stale_onefile_exe.exists():
    stale_onefile_exe.unlink()


a = Analysis(
    ['src\\daylens\\main.py'],
    pathex=[],
    binaries=[],
    datas=[('config', 'config'), ('assets', 'assets')],
    hiddenimports=['yaml', 'PySide6', 'psutil', 'pycaw', 'comtypes'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DayLens',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\icon.ico'],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DayLens',
)
