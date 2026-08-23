# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for ITOps Hub (onedir, windowed) — v1.5 production build.
#
# - onedir: faster startup, AV-friendlier than onefile
# - windowed: no console window; `--selftest` still reports via exit code
#   (logs always go to %LOCALAPPDATA%\ITOpsHub\logs regardless)
# - uvicorn hidden imports are required for the embedded local API

import os

block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=[os.path.abspath(".")],
    binaries=[],
    datas=[
        ("resources", "resources"),
        # Alembic scripts are file-based (env.py/mako/versions) and are not
        # collected automatically; ship them so migrations run in the exe.
        ("app/infrastructure/db/alembic", "app/infrastructure/db/alembic"),
    ],
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ITOpsHub",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon="resources" + os.sep + "icons" + os.sep + "app.ico" if os.path.exists(
        "resources" + os.sep + "icons" + os.sep + "app.ico"
    ) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="ITOpsHub",
)
