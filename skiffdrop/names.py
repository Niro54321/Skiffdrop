"""Safe file names for whatever a phone sends, and collision-free saving."""

from __future__ import annotations

import os
import shutil
import unicodedata
from pathlib import Path

_BAD = set('<>:"/\\|?*\x7f') | {chr(i) for i in range(32)}
# Bidi overrides and isolates can disguise an extension ("photo‮gpj.exe"); they never belong in a name.
_BIDI = {chr(c) for c in (*range(0x202A, 0x202F), *range(0x2066, 0x206A))}
_RESERVED = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
             *(f"COM{i}" for i in "123456789¹²³"), *(f"LPT{i}" for i in "123456789¹²³")}
MAX_LEN = 180  # characters; NTFS allows 255 UTF-16 units per name and the folder path needs room too


def safe_name(raw: str, fallback: str = "file") -> str:
    """A plain file name that can only land inside the folder it is joined to."""
    name = unicodedata.normalize("NFC", str(raw or ""))
    name = name.replace("\\", "/").split("/")[-1]
    name = "".join("_" if c in _BAD else c for c in name if c not in _BIDI)
    name = name.strip().rstrip(". ")  # Windows drops trailing dots and spaces itself
    if not name.strip("."):
        name = fallback
    stem, ext = os.path.splitext(name)
    if stem.split(".")[0].strip().upper() in _RESERVED:
        stem = "_" + stem
    if len(ext) > 32:  # not a real extension, keep it with the stem
        stem, ext = stem + ext, ""
    if len(stem) + len(ext) > MAX_LEN:
        stem = stem[:MAX_LEN - len(ext)].rstrip(". ") or fallback
    return stem + ext


def candidates(folder: Path, name: str):
    stem, ext = os.path.splitext(name)
    yield folder / name
    for i in range(1, 100000):
        yield folder / f"{stem} ({i}){ext}"


def place(src: Path, folder: Path, name: str) -> Path:
    """Moves src into folder under name, or "name (1)", "name (2)"... never over an existing file."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    root = folder.resolve()
    for dest in candidates(folder, safe_name(name)):
        if dest.resolve().parent != root:  # cannot happen after safe_name; checked anyway
            raise ValueError(f"unsafe name {name!r}")
        try:
            os.rename(src, dest)  # Windows refuses to replace an existing file
            return dest
        except FileExistsError:
            continue
        except OSError:
            if dest.exists():
                continue
            shutil.move(str(src), str(dest))  # another drive
            return dest
    raise FileExistsError(name)
