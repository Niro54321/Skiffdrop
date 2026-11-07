# PyInstaller recipe, run by packaging/build.py. Makes dist/Skiffdrop with
# Skiffdrop.exe and skiffdrop-selftest.exe sharing one _internal folder; the
# self-test checks the build and is left out of the installer.

from pathlib import Path

ROOT = Path(SPECPATH).parent
BUILD = ROOT / "build"
DATAS = [(str(ROOT / "skiffdrop" / "web"), "skiffdrop/web")]
EXCLUDES = ["tkinter", "numpy", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtQuick",
            "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.Qt3DCore", "PySide6.QtQuick3D", "PySide6.QtCharts",
            "PySide6.QtDataVisualization", "PySide6.QtDesigner", "PySide6.QtPdf", "PySide6.QtSql",
            "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtTest", "PySide6.QtXml",
            "PySide6.QtConcurrent", "PySide6.QtDBus", "PySide6.QtPrintSupport", "PySide6.QtUiTools"]


def analysis(script):
    return Analysis([str(ROOT / "packaging" / script)], pathex=[str(ROOT)], datas=DATAS, binaries=[],
                    hiddenimports=["PySide6.QtSvg"], excludes=EXCLUDES, noarchive=False)


app = analysis("launcher.py")
test = analysis("selftest.py")

app_exe = EXE(PYZ(app.pure), app.scripts, [], exclude_binaries=True, name="Skiffdrop",
              icon=str(BUILD / "skiffdrop.ico"), version=str(BUILD / "version.txt"),
              console=False, upx=False)
test_exe = EXE(PYZ(test.pure), test.scripts, [], exclude_binaries=True, name="skiffdrop-selftest",
               icon=str(BUILD / "skiffdrop.ico"), console=True, upx=False)

COLLECT(app_exe, app.binaries, app.datas, test_exe, test.binaries, test.datas,
        name="Skiffdrop", upx=False)
