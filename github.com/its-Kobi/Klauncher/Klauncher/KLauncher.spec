# -*- mode: python ; coding: utf-8 -*-
# PyInstaller OneDir spec — clean Windows build, no hardcoded paths
# Build: pyinstaller KLauncher.spec
# Output: dist/KLauncher/KLauncher.exe
import os
from pathlib import Path

block_cipher = None

# PyInstaller 6.x no longer defines __file__ while executing the spec file.
try:
    base = Path(__file__).resolve().parent
except NameError:
    base = Path(globals().get("SPECPATH") or os.getcwd()).resolve()

a = Analysis(
    ['main.py'],
    pathex=[str(base)],
    binaries=[],
    datas=[
        ('Assets', 'Assets'),
        ('themes', 'themes'),
        ('launcher', 'launcher'),
        ('ui', 'ui'),
    ],
    hiddenimports=[
        'launcher.auth.manager',
        'launcher.providers.registry',
        'launcher.targets.registry',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tests', 'tkinter.test', 'sqlite3'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='KLauncher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(base / 'Assets' / 'Icons' / 'Klauncher_logo.ico') if (base / 'Assets' / 'Icons' / 'Klauncher_logo.ico').exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='KLauncher',
)
