from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


import site
import sys

project_root = Path(SPECPATH).parent

# Ensure PyInstaller can find packages in the venv's site-packages
_sitepkg = str(project_root / ".venv" / "Lib" / "site-packages")
_pathext = [str(project_root), _sitepkg]

# Collect all webview submodules — pywebview uses dynamic imports inside guilib.py
# and empty __init__.py files that PyInstaller's static analysis skips.
_hiddenimports = [
    "pystray",
    "PIL",
    "PIL.Image",
]
_hiddenimports.extend(collect_submodules("webview"))

a = Analysis(
    [str(project_root / "sc_gr_app" / "main.py")],
    pathex=_pathext,
    binaries=[],
    datas=[
        (str(project_root / "sc_gr_app" / "web"), "sc_gr_app/web"),
        (str(project_root / "sc_gr_app" / "icons"), "sc_gr_app/icons"),
        (str(project_root / "sc_gr_app" / "db" / "schema.sql"), "sc_gr_app/db"),
    ],
    hiddenimports=_hiddenimports,
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
    name="SC GR Management",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_root / "build" / "app" / "logo.ico"),
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="SC GR Management",
)
