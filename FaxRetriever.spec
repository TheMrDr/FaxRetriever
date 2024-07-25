# -*- mode: python ; coding: utf-8 -*-


block_cipher = None


a = Analysis(
    ['AboutDialog.py', 'AutoUpdate.py', 'Customizations.py', 'FaxStatusDialog.py', 'main.py', 'options.py',
     'ProgressBars.py', 'RetrieveFax.py', 'RetrieveNumbers.py', 'SaveManager.py', 'SendFax.py', 'SystemLog.py'],
    pathex=['U:\\jfreeman\\Software Development\\FaxRetriever'],
    binaries=[],
    datas=[
        ('images', 'images'),
        ('ReadMe', '.'),
        ('poppler', 'poppler')
    ],
    hiddenimports=['pdf2image', 'pdf2image.backends', 'pdf2image.backends.poppler', 'plyer', 'plyer.notification',
    'fitz', 'pymupdf', 'pyinsane2', 'docx', 'python-docx'],
    hookspath=['./hooks'],
    runtime_hooks=[],
    excludes=[],
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
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['U:\\jfreeman\\Software Development\\FaxRetriever\\images\\logo.ico'],
)
