# -*- mode: python ; coding: utf-8 -*-
block_cipher = None

import os
from PyInstaller.building.build_main import Analysis, PYZ, EXE
from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import collect_submodules, collect_all

# Keep src importable; don't ship it as data
pathex = [os.path.abspath('.'), os.path.abspath('src')]

# --- Hidden imports / plugin trees ---
# Only Windows plyer backend to avoid jnius (Android) warnings
plyer_win_hidden = collect_submodules('plyer.platforms.win')

# pdf2image backends (safe to collect all)
pdf2image_backends = collect_submodules('pdf2image.backends')

# Packages that often need data/backends (guarded to avoid crashes if not installed)
try:
    pyinsane2_datas, pyinsane2_bins, pyinsane2_hidden = collect_all('pyinsane2')
except Exception:
    pyinsane2_datas, pyinsane2_bins, pyinsane2_hidden = ([], [], [])

try:
    docx_datas, docx_bins, docx_hidden = collect_all('docx')
except Exception:
    docx_datas, docx_bins, docx_hidden = ([], [], [])

# Explicitly collect PyMuPDF (fitz) to ensure MuPDF binaries and resources are bundled, if present
try:
    fitz_datas, fitz_bins, fitz_hidden = collect_all('fitz')
except Exception:
    fitz_datas, fitz_bins, fitz_hidden = ([], [], [])

# Optionally include certifi (helps 'requests' TLS on some machines)
try:
    certifi_datas, certifi_bins, certifi_hidden = collect_all('certifi')
except Exception:
    certifi_datas, certifi_bins, certifi_hidden = ([], [], [])

base_hiddenimports = [
    'fitz',                 # PyMuPDF import name
    'jwt',                  # keep since you saw a miss
    'logging.handlers',     # keep since you saw a miss
    'winotify',             # dynamically imported in receiver notifications
    'win10toast',           # dynamically imported in receiver notifications
]
all_hiddenimports = (
    base_hiddenimports
    + pdf2image_backends
    + plyer_win_hidden
    + pyinsane2_hidden
    + docx_hidden
    + certifi_hidden
    + fitz_hidden
)

# 'binaries' must be list of (src, dest) pairs ONLY (no Tree objects here)
base_binaries = pyinsane2_bins + docx_bins + certifi_bins + fitz_bins

# 'datas' must be list of (src, dest) pairs
# Include Markdown documentation so Help -> Read Me / What's New work in bundled app
base_datas = [('images', 'images'), ('src/docs', 'src/docs')] + pyinsane2_datas + docx_datas + certifi_datas + fitz_datas

a = Analysis(
    ['main.py'],
    pathex=pathex,
    binaries=base_binaries,     # pairs only
    datas=base_datas,           # pairs only
    hiddenimports=all_hiddenimports,
    hookspath=['./hooks'],
    runtime_hooks=[],
    excludes=[],                # Only real module names here if needed
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)


pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='FaxRetriever',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['images\\logo.ico'],
)
