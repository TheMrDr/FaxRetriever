# -*- mode: python ; coding: utf-8 -*-

# Optimized PyInstaller spec for FRAAPI (FaxRetriever Admin API)
# Produces 2 executables:
#   - FRAAPI.exe (windowed host)
#   - FRAAPI_console.exe (console for easy log viewing)

from PyInstaller.building.build_main import Analysis, PYZ, EXE
from PyInstaller.utils.hooks import collect_submodules

APP_DIR = r"D:\Projects\FaxRetriever\Admin\FRAAPI"

# ---- Hidden imports ---------------------------------------------------------
# Only the truly dynamic ones or those imported by string paths.
base_hidden = [
    # PyQt host (if your host shows a small window / tray)
    'PyQt5.QtWidgets', 'PyQt5.QtGui', 'PyQt5.QtCore',

    # FastAPI/Uvicorn stack (top-level packages; their internals are found automatically)
    'uvicorn', 'fastapi', 'starlette', 'pydantic',

    # Common libs your code references dynamically
    'requests', 'jwt', 'cryptography', 'pymongo', 'bson',

    # Your FastAPI app and its directly-referenced modules (imported by string in uvicorn)
    'api_app',
    'routes.init_route', 'routes.bearer_route', 'routes.assignments_route', 'routes.admin_route',
    'db.mongo_interface',
    'core.logger',
    'auth.token_utils', 'auth.crypto_utils',
    'utils.fax_user_utils',
    'tasks.token_refresher',
]

# Collect all modules under your own packages to cover any extra routers/helpers added later.
base_hidden += collect_submodules('routes')
base_hidden += collect_submodules('db')
base_hidden += collect_submodules('auth')
base_hidden += collect_submodules('core')
base_hidden += collect_submodules('utils')
base_hidden += collect_submodules('tasks')

# ---- Optional excludes to trim size / avoid platform issues -----------------
# Uvicorn will *attempt* to use these if present, but you typically don't need
# them in production on Windows. Excluding keeps the bundle smaller and avoids
# binary headaches.
excluded = [
    'uvloop',        # not supported on Windows
    'watchfiles',    # dev-time auto-reload
    'watchgod',      # older dev-time auto-reload
    # 'httptools',   # optional; exclude ONLY if you don't use it
    # 'websockets',  # needed if your app serves websockets
]

a = Analysis(
    ['fraapi_host.py'],
    pathex=[APP_DIR],
    binaries=[],
    datas=[],                    # add datas here if you later ship templates/static files
    hiddenimports=base_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, optimize=0)

# Windowed build (no console window). Good for a GUI host.
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FRAAPI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,               # windowed
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,                   # no icon available
)

# Console build (great for tailing logs in a cmd window)
exe_console = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='FRAAPI_console',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,                # console enabled
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
