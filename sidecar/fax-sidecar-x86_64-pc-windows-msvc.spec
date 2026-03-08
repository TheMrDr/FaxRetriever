# -*- mode: python ; coding: utf-8 -*-

# PyInstaller spec for the FaxRetriever sidecar (headless JSON-RPC backend).
# Build from sidecar/ directory:
#   pyinstaller fax-sidecar-x86_64-pc-windows-msvc.spec

import os

PROJECT_ROOT = r'D:\Projects\FaxRetriever'
SIDECAR_DIR = os.path.join(PROJECT_ROOT, 'sidecar')
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')

a = Analysis(
    ['main.py'],
    pathex=[
        SIDECAR_DIR,
        SRC_DIR,
    ],
    binaries=[],
    datas=[
        # Bundle src/ modules as data so the runtime sys.path.insert finds them.
        # PyInstaller can't trace these via hiddenimports because registry.py
        # adds them to sys.path dynamically at runtime.
        (os.path.join(SRC_DIR, 'core'), 'core'),
        (os.path.join(SRC_DIR, 'fax_io'), 'fax_io'),
        (os.path.join(SRC_DIR, 'utils'), 'utils'),
        (os.path.join(SRC_DIR, 'integrations'), 'integrations'),
    ],
    hiddenimports=[
        # Handler modules (loaded via registry @register decorator)
        'handlers.system_handlers',
        'handlers.config_handlers',
        'handlers.auth_handlers',
        'handlers.fax_handlers',
        'handlers.outbox_handlers',
        'handlers.contacts_handlers',
        'handlers.send_handlers',

        # Third-party (dynamically loaded or referenced by string)
        'requests',
        'urllib3',
        'jwt',
        'cryptography',
        'fitz',
        'PIL',
        'pypdf',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Not needed in headless sidecar
        'PyQt5',
        'tkinter',
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='fax-sidecar-x86_64-pc-windows-msvc',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
