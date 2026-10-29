# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the Inventory Dashboard.
# Build:  .venv\Scripts\python.exe -m PyInstaller app.spec --noconfirm --clean
from PyInstaller.utils.hooks import collect_all, copy_metadata

datas = []
binaries = []
hiddenimports = []

# Collect everything (modules, data files, dynamic libs) for the heavy deps.
_packages = [
    "streamlit", "pandas", "numpy", "plotly", "statsmodels", "scipy",
    "openpyxl", "pyarrow", "yaml", "altair", "narwhals", "tornado",
    "click", "blinker", "watchdog", "et_xmlfile", "dateutil", "pytz",
    "tzdata", "patsy", "packaging",
]
for _pkg in _packages:
    try:
        d, b, h = collect_all(_pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

# Some libraries read their version via importlib.metadata at runtime.
for _pkg in ["streamlit", "pandas", "numpy", "plotly", "statsmodels",
             "scipy", "openpyxl", "pyarrow", "altair", "narwhals"]:
    try:
        datas += copy_metadata(_pkg)
    except Exception:
        pass

# Our own source. Streamlit executes app.py / pages at runtime, so ship them
# as data (they are extracted next to each other inside the bundle).
datas += [
    ("app.py", "."),
    ("pages", "pages"),
    ("src", "src"),
]

a = Analysis(
    ["run_app.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="InventoryDashboard",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="InventoryDashboard",
)
