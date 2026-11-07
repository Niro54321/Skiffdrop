"""Draws the Microsoft Store logos from the Skiffdrop mark (vector, so every size is sharp).

    .venv\\Scripts\\python.exe store\\logos.py <out-folder>

- app-tile-icon-300.png      1:1 app tile icon, 300 x 300, transparent (the brass app icon)
- box-art-1080.png / -2160   1:1 box art
- poster-art-720x1080.png / -1440x2160   2:3 poster art
- hero-1920x1080.png / -3840x2160        16:9 hero image
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QPA_FONTDIR", "C:/Windows/Fonts")

from PySide6.QtCore import QByteArray, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen  # noqa: E402
from PySide6.QtSvg import QSvgRenderer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

APP = QApplication.instance() or QApplication([])

from skiffdrop import theme as T  # noqa: E402
from skiffdrop.ui import brass_tile_svg, load_fonts, mark_svg  # noqa: E402

load_fonts()
TAGLINE = "Your files, sailing home."


def svg(p: QPainter, text: str, r: QRectF) -> None:
    QSvgRenderer(QByteArray(text.encode())).render(p, r)


def canvas(w: int, h: int) -> tuple[QImage, QPainter]:
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(QColor(T.INK))
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    return img, p


def waves(p: QPainter, w: int, h: int, y: float, unit: float) -> None:
    """Three quiet wave lines across the bottom, in the deep-hull blue."""
    for i, alpha in enumerate((70, 45, 25)):
        pen = QPen(QColor(216, 180, 106, alpha), unit * 0.9)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        yy = y + i * unit * 3.2
        x = -unit * 2 + (i % 2) * unit * 2.2
        step = unit * 4.4
        while x < w:
            from PySide6.QtGui import QPainterPath
            path = QPainterPath()
            path.moveTo(x, yy)
            path.quadTo(x + step / 4, yy - unit * 0.9, x + step / 2, yy)
            path.quadTo(x + step * 3 / 4, yy + unit * 0.9, x + step, yy)
            p.drawPath(path)
            x += step


def wordmark(p: QPainter, r: QRectF, size: float, tagline: bool = True, align=Qt.AlignmentFlag.AlignHCenter) -> None:
    f = QFont("Instrument Serif")
    f.setPixelSize(int(size))
    p.setFont(f)
    p.setPen(QColor(T.IVORY))
    top = QRectF(r.x(), r.y(), r.width(), size * 1.15)
    p.drawText(top, align | Qt.AlignmentFlag.AlignTop, "Skiffdrop")
    if tagline:
        g = QFont("Instrument Serif")
        g.setPixelSize(int(size * 0.34))
        p.setFont(g)
        p.setPen(QColor(T.BRASS))
        p.drawText(QRectF(r.x(), r.y() + size * 1.18, r.width(), size * 0.5), align | Qt.AlignmentFlag.AlignTop, TAGLINE)


def tile(p: QPainter, cx: float, cy: float, side: float) -> None:
    """The mark on its Deep Hull tile with a brass hairline, as on the brand sheet."""
    svg(p, mark_svg(T.DARK.mark, T.HULL, "rgba(216,180,106,0.45)"), QRectF(cx - side / 2, cy - side / 2, side, side))


def app_tile(out: Path) -> None:
    img = QImage(300, 300, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    svg(p, brass_tile_svg(300), QRectF(0, 0, 300, 300))
    p.end()
    img.save(str(out / "app-tile-icon-300.png"))


def box_art(out: Path, s: int) -> None:
    img, p = canvas(s, s)
    u = s / 100
    waves(p, s, s, s * 0.86, u)
    tile(p, s / 2, s * 0.40, s * 0.38)
    wordmark(p, QRectF(0, s * 0.62, s, s * 0.3), s * 0.11)
    p.end()
    img.save(str(out / f"box-art-{s}.png"))


def poster(out: Path, w: int, h: int) -> None:
    img, p = canvas(w, h)
    u = w / 100
    waves(p, w, h, h * 0.88, u)
    tile(p, w / 2, h * 0.36, w * 0.5)
    wordmark(p, QRectF(0, h * 0.56, w, h * 0.3), w * 0.16)
    p.end()
    img.save(str(out / f"poster-art-{w}x{h}.png"))


def hero(out: Path, w: int, h: int) -> None:
    img, p = canvas(w, h)
    u = w / 192
    waves(p, w, h, h * 0.84, u)
    tile(p, w * 0.70, h * 0.44, h * 0.46)
    wordmark(p, QRectF(w * 0.10, h * 0.33, w * 0.45, h * 0.4), h * 0.16, True, Qt.AlignmentFlag.AlignLeft)
    p.end()
    img.save(str(out / f"hero-{w}x{h}.png"))


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "store" / "logos"
    out.mkdir(parents=True, exist_ok=True)
    app_tile(out)
    for s in (1080, 2160):
        box_art(out, s)
    poster(out, 720, 1080)
    poster(out, 1440, 2160)
    hero(out, 1920, 1080)
    hero(out, 3840, 2160)
    print("logos in", out)


if __name__ == "__main__":
    main()
