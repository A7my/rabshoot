# PyInstaller spec for the RabShoot engine sidecar. Build with: python scripts/build_engine.py
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

ROOT = Path(SPECPATH).parent
PKG = ROOT / "engine" / "rabshoot_engine"

datas = [
    (str(PKG / "templates"), "rabshoot_engine/templates"),
    (str(PKG / "assets"), "rabshoot_engine/assets"),
]
binaries = []
hiddenimports = (
    collect_submodules("rabshoot_engine")
    + collect_submodules("uvicorn")
    + collect_submodules("apscheduler")
    + collect_submodules("keyring.backends")
)
if sys.platform == "win32":
    hiddenimports += collect_submodules("win32ctypes")
else:
    hiddenimports += ["secretstorage", "jeepney"]

for package in ("tzdata",):
    d, b, h = collect_all(package)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    [str(ROOT / "packaging" / "engine_entry.py")],
    pathex=[str(ROOT / "engine")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "pytest", "PIL", "playwright", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="rabshoot-engine",
    console=True,
    upx=False,
    strip=False,
    disable_windowed_traceback=False,
)
