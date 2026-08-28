# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = ['psutil', 'tkinter', 'tkinter.ttk', 'uuid', 'json', 'hashlib', 'socket', 'platform', 'subprocess', 'shutil', 'zipfile', 'webbrowser', 'datetime']
hiddenimports += collect_submodules('core')


a = Analysis(
    ['d:\\QCC\\test_engine\\agent\\agent_runner.py'],
    pathex=[],
    binaries=[],
    datas=[('d:\\QCC\\test_engine\\core', 'core'), ('d:\\QCC\\test_engine\\script_registry.json', '.'), ('d:\\QCC\\test_engine\\scripts', 'scripts')],
    hiddenimports=hiddenimports,
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
    name='QCC_Test_Agent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='QCC_Test_Agent',
)
