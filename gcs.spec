# -*- mode: python ; coding: utf-8 -*-
"""
GCS tek dosya paketleme tanimi.

Linux:
  pyinstaller --noconfirm --clean gcs.spec

Windows (ayni spec):
  pyinstaller --noconfirm --clean gcs.spec

Cikti: dist/GCS  (Linux/macOS) veya dist/GCS.exe (Windows)

Paketleme her kod degisikliginden sonra tekrarlanmalidir; bu yuzden
gelistirme yol haritasinda (YOL_HARITASI.md) en son adimdir.

QtWebEngine icu/pak/resource dosyalari collect_all(PyQt5) ile alinir.
"""

import os
import sys

from PyInstaller.building.build_main import EXE, PYZ, Analysis
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas = []
binaries = []
hiddenimports = [
    "PyQt5.QtWebEngineWidgets",
    "PyQt5.QtWebEngine",
    "PyQt5.QtWebEngineCore",
    "PyQt5.sip",
    "matplotlib.backends.backend_qt5agg",
    "matplotlib.backends.backend_qtagg",
    "pymavlink.dialects.v20.ardupilotmega",
    "serial",
    "serial.tools.list_ports",
    "core.drone_telemetry",
    "core.flight_logger",
    "core.app_paths",
    "core.exporters",
    "core.voice_alerts",
    "ui.map_widget_v3",
    "ui.mission_panel",
    "ui.safety_panel",
    "ui.stat_card",
    "ui.event_log_panel",
    "ui.connection_dialog",
    "ui.artificial_horizon",
    "ui.replay_panel",
    "ui.mission_mode_selector",
    "ui.preflight_checklist_dialog",
    "ui.flight_summary_dialog",
    "ui.flight_graph_dialog",
    "ui.parameter_editor_dialog",
    "ui.calibration_dialog",
]

for pkg in ("PyQt5", "matplotlib", "pymavlink"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden

hiddenimports += collect_submodules("pymavlink")

block_cipher = None

a = Analysis(
    ["main_v7.py"],
    pathex=[os.path.abspath(".")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="GCS",
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
