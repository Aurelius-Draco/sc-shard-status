# PyInstaller build of SC Shard Status (a folder with SC Shard Status.exe and everything it needs, no Python
# required). The installer workflow runs: pyinstaller installer/sc-shard-status.spec
# Warm the OCR engine up first (python -c "from rapidocr import RapidOCR; RapidOCR()") so its model files are
# downloaded into the rapidocr package and get bundled; nothing is downloaded on the player's PC.
import os

from PyInstaller.utils.hooks import collect_all

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
PKG = os.path.join(ROOT, "scstatus")

datas = [(os.path.join(PKG, d), os.path.join("scstatus", d)) for d in ("static", "assets", "library")]
binaries, hidden = [], []
for name in ("rapidocr",):
    d, b, h = collect_all(name)
    datas += d
    binaries += b
    hidden += h

a = Analysis(
    [os.path.join(ROOT, "status.py")],
    pathex=[ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden + ["scstatus.migrate", "scstatus.updater"],
    # Other OCR back ends rapidocr can use but this app doesn't, and big libraries nothing here needs
    excludes=["tkinter", "matplotlib", "PyQt5", "PySide6", "IPython", "pytest", "scipy", "pandas", "torch",
              "paddle", "openvino", "tensorrt", "sklearn"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SC Shard Status",
    icon=os.path.join(PKG, "assets", "status.ico"),
    console=True,                 # the window players already know: close it to stop the app
    version=os.path.join(SPECPATH, "version_info.txt") if os.path.exists(os.path.join(SPECPATH, "version_info.txt")) else None,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="SC Shard Status", upx=False)
