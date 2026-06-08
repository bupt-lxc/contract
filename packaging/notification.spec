from pathlib import Path

project_root = Path(SPECPATH).parent

a = Analysis(
    [str(project_root / "sc_gr_app" / "notification" / "__main__.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=[
        (str(project_root / "sc_gr_app" / "db" / "schema.sql"), "sc_gr_app/db"),
    ],
    hiddenimports=[
        "win32com",
        "win32com.client",
        "pythoncom",
    ],
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
    name="SC-GR-Notification",
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
    name="SC-GR-Notification",
)
