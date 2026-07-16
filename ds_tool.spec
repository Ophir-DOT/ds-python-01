# PyInstaller spec for the Design Specification Tool GUI.
#
# Build (from python/):   pyinstaller ds_tool.spec
# Output:                 dist/ds-tool-gui/
#
# Notes / known risks:
#   * WeasyPrint needs GTK native libs (Pango/Cairo/GObject) which PyInstaller
#     cannot bundle reliably on Windows. The app degrades to HTML output when
#     they are missing, so PDF is best-effort in the frozen build. Install the
#     GTK runtime on the host to get PDFs.
#   * The Salesforce `sf` CLI is NOT bundled — it is invoked via subprocess.
#     The frozen app requires Salesforce CLI installed on PATH.

from PyInstaller.utils.hooks import collect_all, collect_data_files

datas = collect_data_files("ds_tool", includes=["pdf/templates/**/*", "gui/assets/**/*"])
binaries = []
hiddenimports = ["ds_tool.gui"]

for pkg in ("zeep", "weasyprint"):
    pkg_datas, pkg_binaries, pkg_hidden = collect_all(pkg)
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports += pkg_hidden


a = Analysis(
    ["ds_tool/gui/__main__.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "PySide6.QtQuick", "PySide6.Qt3DCore"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ds-tool-gui",
    console=False,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="ds-tool-gui",
)
