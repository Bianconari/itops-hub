# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for ITOps Hub (onedir build).
#
# Evolves with milestones: charts (PyQtGraph) land in v0.4; the local FastAPI
# service in v1.5. The console window stays enabled for early builds so
# selftest output is visible; it is disabled when packaging hardens in v1.0
# (log files always capture output regardless).

import os

block_cipher = None

a = Analysis(
    ["run.py"],
    pathex=[os.path.abspath(".")],
    binaries=[],
    datas=[("resources", "resources")],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
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
    [],
    exclude_binaries=True,
    name="ITOpsHub",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,  # switch to False at v1.0 packaging hardening
    disable_windowed_traceback=False,
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
