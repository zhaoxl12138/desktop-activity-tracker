# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


spec_root = Path(SPECPATH) if 'SPECPATH' in globals() else Path.cwd()
stale_onefile_exe = spec_root / 'dist' / 'DayLens.exe'
if stale_onefile_exe.exists():
    stale_onefile_exe.unlink()


a = Analysis(
    ['src\\daylens\\main.py'],
    pathex=[],
    binaries=[],
    datas=[('config', 'config'), ('assets', 'assets')],
    hiddenimports=['pycaw', 'comtypes', 'comtypes.gen', 'comtypes.stream', 'psutil'],
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
    name='DayLens',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\icon.ico'],
    exclude_binaries=True,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    a.zipfiles,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DayLens',
)
