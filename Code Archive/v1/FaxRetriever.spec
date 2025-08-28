# -*- mode: python ; coding: utf-8 -*-


block_cipher = None


a = Analysis(
    ['AboutDialog.py', 'ArchiveManager.py', 'AutoUpdate.py', 'Customizations.py', 'FaxStatusDialog.py',
     'main.py', 'Options.py', 'ProgressBars.py', 'RetrieveFax.py', 'RetrieveNumbers.py', 'RetrieveToken.py',
     'SaveManager.py', 'SendFax.py', 'SystemLog.py', 'Validation.py', 'WhatsNew.py'],
    pathex=['D:\\Projects\\FaxRetriever'],
    binaries=[],
    datas=[
        ('images', 'images'),
        ('readme.md', '.'),
        ('poppler', 'poppler'),
        ('changes.md', '.'),
        ('integrations', 'integrations'),
    ],
    hiddenimports=['pdf2image', 'pdf2image.backends', 'pdf2image.backends.poppler', 'plyer', 'plyer.notification',
    'fitz', 'pymupdf', 'pyinsane2', 'docx', 'python-docx'],
    hookspath=['./hooks'],
    runtime_hooks=[],
    excludes=['Source Files', 'Archive', 'Scanned Docs', 'Testing Apps', 'Testing Data'],
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
    icon=['D:\\Projects\\FaxRetriever\\images\\logo.ico'],
)
