# -*- mode: python ; coding: utf-8 -*-

import re
from pathlib import Path

from PyInstaller.building.build_main import Analysis, EXE, PYZ
from PyInstaller.utils.hooks import collect_submodules


version_text = Path("app/version.py").read_text(encoding="utf-8")
version_match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', version_text)
if version_match is None:
    raise RuntimeError("Could not find __version__ in app/version.py")
version = version_match.group(1)

hiddenimports = []
for package in ("app", "core", "desktop", "uvicorn", "anyio", "requests"):
    hiddenimports.extend(collect_submodules(package))

hiddenimports.extend([
    "pystray",
    "pystray._win32",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
])

a = Analysis(
    ["run_formflow.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("app/static", "app/static"),
        ("app/resources", "app/resources"),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "scipy", "tkinter"],
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
    name=f"FormFlow_v{version}",
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
)
