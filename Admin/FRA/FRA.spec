# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.building.build_main import Analysis, PYZ, EXE

APP_DIR = r'D:\Projects\FaxRetriever\Admin\FRA'
IMG_DIR = APP_DIR + r'\images'

qt_hidden = [
    'PyQt5.QtWidgets',
    'PyQt5.QtGui',
    'PyQt5.QtCore',
]

a = Analysis(
    ['FRA.py'],
    pathex=[APP_DIR],
    binaries=[],
    datas=[(IMG_DIR, 'images')],   # << fix: pairs, not Tree()
    hiddenimports=qt_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

# fix: include a.zipped_data, move optimize here
pyz = PYZ(a.pure, a.zipped_data, optimize=0)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FRA',
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
    icon=APP_DIR + r'\images\logo.ico',  # << fix: string, not list
)
