"""Builds the Windows installer.

    .venv\\Scripts\\python.exe packaging\\build.py [--skip-test]

1. icon, version info and third-party notices into build/
2. PyInstaller: dist/Skiffdrop (the app, plus a self-test exe)
3. the self-test: server, pairing, upload, download, thumbnail, zip, QR, icon in the packaged app
4. Inno Setup: dist/Skiffdrop-Setup-<version>.exe

Needs PyInstaller in the venv and Inno Setup 6 (winget install JRSoftware.InnoSetup).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD, DIST = ROOT / "build", ROOT / "dist"
sys.path.insert(0, str(ROOT))

from skiffdrop import __version__  # noqa: E402

SHIPPED = {"pyside6-essentials", "shiboken6", "segno"}


def step(text: str) -> None:
    print(f"\n== {text}", flush=True)


def prepare() -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from skiffdrop.ui import icon_pixmap, png_bytes

    BUILD.mkdir(exist_ok=True)
    prepare.qt = QApplication.instance() or QApplication(["build"])  # icons need Qt; kept alive here
    sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    pngs = [png_bytes(icon_pixmap(s)) for s in sizes]
    # An .ico is a small directory of PNG images.
    ico = b"\0\0\1\0" + len(sizes).to_bytes(2, "little")
    offset = 6 + 16 * len(sizes)
    for s, png in zip(sizes, pngs):
        ico += bytes([s % 256, s % 256, 0, 0]) + (1).to_bytes(2, "little") + (32).to_bytes(2, "little")
        ico += len(png).to_bytes(4, "little") + offset.to_bytes(4, "little")
        offset += len(png)
    (BUILD / "skiffdrop.ico").write_bytes(ico + b"".join(pngs))
    nums = ", ".join((__version__.split(".") + ["0"] * 4)[:4])
    (BUILD / "version.txt").write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers=({nums}), prodvers=({nums})),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'Niro54321'),
    StringStruct('FileDescription', 'Skiffdrop'),
    StringStruct('FileVersion', '{__version__}'),
    StringStruct('LegalCopyright', 'MIT License'),
    StringStruct('ProductName', 'Skiffdrop'),
    StringStruct('ProductVersion', '{__version__}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])])
""", encoding="utf-8")


def notices(target: Path) -> None:
    """THIRD-PARTY-NOTICES.txt and every bundled package's own licence files."""
    licenses = target / "licenses"
    shutil.rmtree(licenses, ignore_errors=True)
    lines = ["Skiffdrop is MIT licensed (see LICENSE). The installer also contains the",
             "open-source software below, each under its own licence; the full texts are",
             "in the licenses folder next to this file.", "",
             f"Python {sys.version.split()[0]}  PSF-2.0  https://www.python.org/"]
    python_license = Path(sys.base_prefix) / "LICENSE.txt"
    if python_license.is_file():
        (licenses / "Python").mkdir(parents=True, exist_ok=True)
        shutil.copy2(python_license, licenses / "Python" / "LICENSE.txt")
    for dist in sorted(metadata.distributions(), key=lambda d: d.metadata["Name"].lower()):
        name = dist.metadata["Name"]
        if name.lower().replace("_", "-") not in SHIPPED:
            continue
        licence = dist.metadata.get("License-Expression") or next(
            (c.split("::")[-1].strip() for c in dist.metadata.get_all("Classifier") or [] if c.startswith("License ::")),
            (dist.metadata.get("License") or "see licence file").splitlines()[0][:60])
        url = next((u.split(",", 1)[-1].strip() for u in dist.metadata.get_all("Project-URL") or []
                    if u.lower().startswith(("source", "repository", "homepage", "code"))),
                   dist.metadata.get("Home-page") or "")
        lines.append(f"{name} {dist.version}  {licence}  {url}".rstrip())
        for f in dist.files or []:
            if any(part.lower().startswith(("license", "licence", "copying", "notice", "authors"))
                   for part in Path(f).parts[-1:]) or "licenses" in Path(f).parts:
                src = Path(dist.locate_file(f))
                if src.is_file():
                    dest = licenses / name / Path(f).name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dest)
    lines += ["", "Bundled inside the packages above:",
              "- Qt 6 (inside PySide6), LGPL-3.0; source: https://download.qt.io/official_releases/qt/"]
    (target / "THIRD-PARTY-NOTICES.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def pyinstaller() -> Path:
    shutil.rmtree(DIST / "Skiffdrop", ignore_errors=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                    "--distpath", str(DIST), "--workpath", str(BUILD / "pyinstaller"),
                    str(ROOT / "packaging" / "skiffdrop.spec")], check=True)
    out = DIST / "Skiffdrop"
    shutil.copy2(ROOT / "LICENSE", out / "LICENSE.txt")
    notices(out)
    return out


def selftest(out: Path) -> None:
    subprocess.run([str(out / "skiffdrop-selftest.exe")], check=True)


def inno() -> Path:
    candidates = [Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Inno Setup 6/ISCC.exe",
                  Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6/ISCC.exe",
                  Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6/ISCC.exe"]
    iscc = next((c for c in candidates if c.is_file()), None) or shutil.which("ISCC")
    if not iscc:
        sys.exit("Inno Setup 6 not found: winget install JRSoftware.InnoSetup")
    subprocess.run([str(iscc), f"/DAppVersion={__version__}", str(ROOT / "packaging" / "skiffdrop.iss")],
                   check=True)
    return DIST / f"Skiffdrop-Setup-{__version__}.exe"


def main() -> None:
    step(f"Skiffdrop {__version__}: icon and version info")
    prepare()
    step("PyInstaller")
    out = pyinstaller()
    if "--skip-test" not in sys.argv:
        step("Self-test in the packaged app")
        selftest(out)
    step("Inno Setup")
    setup = inno()
    digest = hashlib.sha256(setup.read_bytes()).hexdigest()
    (setup.parent / (setup.name + ".sha256")).write_text(f"{digest}  {setup.name}\n", encoding="ascii")
    print(f"\nDone: {setup} ({setup.stat().st_size / 1e6:.0f} MB)\nSHA-256 {digest}")


if __name__ == "__main__":
    main()
