# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for Phone Analysis (Windows, one-folder build).
#   cd frontend && npm ci && npm run build && cd ..
#   pyinstaller spni.spec --noconfirm
# Optional extras picked up when present:
#   resources/agent/spni-agent.apk      (Android helper app, built from android-agent/)
#   resources/platform-tools/adb.exe    (official Google platform-tools)
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [
    ("frontend/dist", "frontend/dist"),
    ("resources/fonts", "resources/fonts"),
    ("resources/icon.png", "resources"),
]
if os.path.isfile("resources/agent/spni-agent.apk"):
    datas.append(("resources/agent/spni-agent.apk", "resources/agent"))
if os.path.isdir("resources/platform-tools"):
    datas.append(("resources/platform-tools", "platform-tools"))

datas += collect_data_files("adbutils")
datas += collect_data_files("pymobiledevice3")
datas += collect_data_files("reportlab")
datas += collect_data_files("docx")

hiddenimports = (
    collect_submodules("pymobiledevice3.services")
    + collect_submodules("spni")
    + ["pillow_heif", "uharfbuzz", "iphone_backup_decrypt"]
)

a = Analysis(
    ["launcher.py"],
    pathex=["."],
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Phone Analysis",
    icon="resources/icon.ico",
    console=False,
    version=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Phone Analysis")
