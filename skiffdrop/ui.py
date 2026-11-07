"""Harbor Edition widgets for the PC window: the mark, line icons, the QR tile, the code keycaps,
list rows, the pairing card, and a window that keeps the Windows frame but draws its own title bar."""

from __future__ import annotations

import ctypes
import html
import re
import sys
import time
import weakref
from ctypes import wintypes
from pathlib import Path

import segno
from PySide6.QtCore import QByteArray, QObject, QPoint, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QCursor, QFontDatabase, QGuiApplication, QIcon, QPainter, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QAbstractButton, QApplication, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QProgressBar, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from . import theme as T
from .i18n import RTL, tr

WEB = Path(__file__).with_name("web")
FONTS = ("InstrumentSerif-Regular.ttf", "Manrope-wght.ttf", "JetBrainsMono-wght.ttf")


class _Look(QObject):
    changed = Signal()


LOOK = _Look()          # emits after a palette switch, so painted widgets can repaint
P: T.Palette = T.DARK   # the palette in use
LANG = "en"
_ICONED: "weakref.WeakKeyDictionary[QWidget, tuple]" = weakref.WeakKeyDictionary()


# ------------------------------------------------------------------ colors
def qc(css: str) -> QColor:
    m = re.match(r"rgba\(([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)\)", css)
    if m:
        r, g, b, a = (float(x) for x in m.groups())
        return QColor(int(r), int(g), int(b), int(a * 255))
    return QColor(css)


def role(name: str) -> str:
    return {"text": P.text, "text2": P.text2, "text3": P.text3, "ink": T.INK, "brass": P.brass_text,
            "sea": P.sea, "coral": P.coral, "ivory": T.IVORY}.get(name, name)


def _svg_paint(css: str) -> str:
    c = qc(css)
    return f'stroke="{c.name()}" stroke-opacity="{c.alphaF():.3f}"'


# ------------------------------------------------------------------ the mark
def mark_svg(colors: dict, tile: str | None = None, tile_line: str | None = None, wave: bool = True) -> str:
    """Two sails of different heights (the two devices), the hull and the wave line."""
    if wave:
        g = "translate(32 33) scale(.8) translate(-32 -33)"
    elif tile:
        g = "translate(32 32) scale(.92) translate(-32 -30)"
    else:
        g = "translate(32 32) scale(.95) translate(-32 -30)"
    parts = [f'<path d="M33.5 12V37H49Z" fill="{colors["right"]}"/>',
             f'<path d="M30.5 20V37H18Z" fill="{colors["left"]}"/>',
             f'<path d="M12 41H52L46.5 48H17.5Z" fill="{colors["hull"]}"/>']
    if wave:
        parts.append(f'<path d="M14 54.5q4.5-3 9 0t9 0t9 0t9 0" fill="none" stroke="{colors["wave"]}" '
                     'stroke-width="2.6" stroke-linecap="round"/>')
    back = ""
    if tile:
        line = ""
        if tile_line:
            c = qc(tile_line)
            line = f' stroke="{c.name()}" stroke-opacity="{c.alphaF():.2f}"'
        back = f'<rect x=".5" y=".5" width="63" height="63" rx="14.5" fill="{tile}"{line}/>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">{back}'
            f'<g transform="{g}">{"".join(parts)}</g></svg>')


def svg_pixmap(svg: str, size: int, dpr: float = 2.0) -> QPixmap:
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray(svg.encode())).render(p, QRectF(0, 0, pm.width(), pm.height()))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def brass_tile_svg(size: int) -> str:
    """The app icon: dark mark on a brass tile; the wave drops below 32 px."""
    colors = {"left": "#675A3E", "right": T.INK, "hull": T.INK, "wave": T.INK}
    return mark_svg(colors, T.BRASS, None, wave=size >= 32)


def app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(svg_pixmap(brass_tile_svg(s), s, 1.0))
    return icon


def icon_pixmap(size: int) -> QPixmap:
    """The brass app icon at one size (installer .ico, the phone's home-screen icon)."""
    return svg_pixmap(brass_tile_svg(size), size, 1.0)


def tile_mark(size: int) -> QPixmap:
    """The mark on its panel-colored tile, as in the title bar."""
    return svg_pixmap(mark_svg(P.mark, P.tile, P.tile_line, wave=size >= 28), size)


def png_bytes(pm, fmt: str = "PNG", quality: int = -1) -> bytes:
    from PySide6.QtCore import QBuffer, QIODevice
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pm.save(buf, fmt, quality)
    return bytes(data)


# ------------------------------------------------------------------ line icons (24 px grid, 1.75 stroke)
ICONS = {
    "settings": '<path d="M4 7h9M17 7h3M4 12h3M11 12h9M4 17h11M19 17h1"/><circle cx="15" cy="7" r="2"/>'
                '<circle cx="9" cy="12" r="2"/><circle cx="17" cy="17" r="2"/>',
    "min": '<path d="M6 12h12"/>',
    "max": '<rect x="6" y="6" width="12" height="12" rx="1.5"/>',
    "restore": '<rect x="5" y="8.5" width="10.5" height="10.5" rx="1.5"/>'
               '<path d="M8.5 8.5V6.5A1.5 1.5 0 0 1 10 5h7.5A1.5 1.5 0 0 1 19 6.5V14a1.5 1.5 0 0 1-1.5 1.5h-2"/>',
    "close": '<path d="M6.5 6.5l11 11M17.5 6.5l-11 11"/>',
    "refresh": '<path d="M19.5 10A8 8 0 0 0 5.6 7"/><path d="M5 3.5V8h4.5"/><path d="M4.5 14a8 8 0 0 0 13.9 3"/>'
               '<path d="M19 20.5V16h-4.5"/>',
    "laptop": '<rect x="5" y="5" width="14" height="10" rx="1.5"/><path d="M3 18.5h18"/>',
    "phone": '<rect x="7" y="3" width="10" height="18" rx="2.5"/><path d="M11 17.5h2"/>',
    "shield": '<path d="M12 3.5l7 2.8v5.2c0 4.3-2.9 7.6-7 9-4.1-1.4-7-4.7-7-9V6.3z"/><path d="M12 8.5v4"/>'
              '<path d="M12 15.8v.2"/>',
    "lock": '<rect x="5.5" y="11" width="13" height="9" rx="2"/><path d="M8.5 11V8a3.5 3.5 0 0 1 7 0v3"/>',
    "upload": '<path d="M12 15V4.5"/><path d="M7.5 9L12 4.5 16.5 9"/>'
              '<path d="M5 14v4.5A1.5 1.5 0 0 0 6.5 20h11a1.5 1.5 0 0 0 1.5-1.5V14"/>',
    "file_plus": '<path d="M14 3.5H7.5A1.5 1.5 0 0 0 6 5v14a1.5 1.5 0 0 0 1.5 1.5h9A1.5 1.5 0 0 0 18 19V7.5z"/>'
                 '<path d="M14 3.5v4h4"/><path d="M12 11v6M9 14h6"/>',
    "file": '<path d="M14 3.5H7.5A1.5 1.5 0 0 0 6 5v14a1.5 1.5 0 0 0 1.5 1.5h9A1.5 1.5 0 0 0 18 19V7.5z"/>'
            '<path d="M14 3.5v4h4"/>',
    "folder": '<path d="M3.5 7A1.5 1.5 0 0 1 5 5.5h4.3l2 2.5H19A1.5 1.5 0 0 1 20.5 9.5v8A1.5 1.5 0 0 1 19 19H5'
              'a1.5 1.5 0 0 1-1.5-1.5z"/>',
    "clipboard": '<rect x="8.5" y="3" width="7" height="4" rx="1"/><path d="M8.5 5H7a1.5 1.5 0 0 0-1.5 1.5v13'
                 'A1.5 1.5 0 0 0 7 21h10a1.5 1.5 0 0 0 1.5-1.5v-13A1.5 1.5 0 0 0 17 5h-1.5"/>',
    "arrow_right": '<path d="M5 12h14"/><path d="M13 6l6 6-6 6"/>',
    "arrow_left": '<path d="M19 12H5"/><path d="M11 6l-6 6 6 6"/>',
    "down": '<path d="M12 4v11"/><path d="M7 10.5l5 5 5-5"/><path d="M5 20h14"/>',
    "up": '<path d="M12 20V9"/><path d="M7 13.5l5-5 5 5"/><path d="M5 4h14"/>',
    "text": '<path d="M4 6a1.5 1.5 0 0 1 1.5-1.5h13A1.5 1.5 0 0 1 20 6v8.5a1.5 1.5 0 0 1-1.5 1.5H10l-6 4z"/>',
    "copy": '<rect x="9" y="9" width="11" height="11" rx="2"/>'
            '<path d="M15 9V5.5A1.5 1.5 0 0 0 13.5 4h-8A1.5 1.5 0 0 0 4 5.5v8A1.5 1.5 0 0 0 5.5 15H9"/>',
    "external": '<path d="M14 4h6v6"/><path d="M20 4l-9 9"/>'
                '<path d="M18 14v4.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 4 18.5v-11A1.5 1.5 0 0 1 5.5 6H10"/>',
}


def line_pixmap(name: str, color: str, size: int = 16, dpr: float = 2.0) -> QPixmap:
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" {_svg_paint(color)} '
           f'stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">{ICONS[name]}</svg>')
    return svg_pixmap(svg, size, dpr)


def set_icon(widget: QWidget, name: str, color_role: str = "text2", size: int = 16) -> None:
    """Gives a button or label a line icon in a palette role; it follows theme switches."""
    _ICONED[widget] = (name, color_role, size)
    pm = line_pixmap(name, role(color_role), size)
    if isinstance(widget, QAbstractButton):
        widget.setIcon(QIcon(pm))
        widget.setIconSize(QSize(size, size))
    elif isinstance(widget, QLabel):
        widget.setPixmap(pm)


# ------------------------------------------------------------------ fonts and the style sheet
def load_fonts() -> None:
    for f in FONTS:
        QFontDatabase.addApplicationFont(str(WEB / "fonts" / f))


def qss() -> str:
    ui, disp, mono = T.ui_family(LANG), T.display_family(LANG), T.mono_family(LANG)
    title_px = T.display_size(LANG, 26)
    return f"""
* {{ font-family: {ui}; font-size: 14px; color: {P.text}; }}
QWidget#root, QDialog#root {{ background: {P.ground}; }}
QWidget#titlebar {{ background: {P.ground}; border-bottom: 1px solid {P.line}; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QFrame#panel {{ background: {P.panel}; border: 1px solid {P.line}; border-radius: 18px; }}
QFrame#well {{ background: {P.well}; border: 1px solid {P.line}; border-radius: 14px; }}
QFrame#drop {{ background: transparent; border: 1px dashed {P.line2}; border-radius: 14px; }}
QFrame#drop[hot="true"] {{ background: rgba(216,180,106,0.08); border: 1px dashed {T.BRASS}; }}
QFrame#banner {{ background: {P.banner}; border: 1px solid {P.banner_line}; border-radius: 18px; }}
QFrame#row {{ background: transparent; border: none; border-radius: 12px; }}
QFrame#row[on="true"] {{ background: {P.raised}; }}
QFrame#sep {{ background: {P.line2}; border: none; max-width: 1px; min-width: 1px; }}
QLabel#wordmark {{ font-family: 'Instrument Serif'; font-size: 31px; }}
QLabel#title {{ font-family: {disp}; font-size: {title_px}px; }}
QLabel#tagline, QLabel#meta, QLabel#muted {{ color: {P.text2}; font-size: 14px; }}
QLabel#strong {{ font-size: 16px; font-weight: 600; }}
QLabel#name {{ font-size: 14px; font-weight: 600; }}
QLabel#sub {{ color: {P.text2}; font-size: 13px; }}
QLabel#ok {{ color: {P.sea}; font-size: 13px; }}
QLabel#bad {{ color: {P.coral}; font-size: 13px; }}
QLabel#url {{ font-family: {mono}; font-size: 13px; color: {P.text2}; }}
QLabel#path {{ font-family: {mono}; font-size: 13px; color: {P.text}; background: {P.panel};
    border: 1px solid {P.line}; border-radius: 8px; padding: 5px 10px; }}
QLabel#tile {{ background: {P.well}; border: 1px solid {P.line}; border-radius: 10px; }}
QLabel#shield {{ background: rgba(240,138,108,0.14); border: 1px solid rgba(240,138,108,0.25); border-radius: 10px; }}
QLabel#circle {{ background: {P.well}; border: 1px solid {P.line2}; border-radius: 20px; }}
QPushButton {{ background: {P.raised}; border: 1px solid {P.line}; border-radius: 10px; padding: 8px 14px;
    font-weight: 600; }}
QPushButton:hover {{ background: {P.raised_hi}; border-color: {P.line2}; }}
QPushButton:pressed {{ background: {P.well}; }}
QPushButton:disabled {{ color: {P.text3}; background: transparent; border-color: {P.line}; }}
QPushButton#primary {{ background: {T.BRASS}; color: {T.INK}; border: none; padding: 9px 18px; }}
QPushButton#primary:hover {{ background: #E2C27F; }}
QPushButton#primary:pressed {{ background: #C9A55C; }}
QPushButton#ghost {{ background: transparent; border: none; padding: 6px 8px; }}
QPushButton#ghost:hover {{ background: {P.raised}; }}
QPushButton#link {{ background: transparent; border: none; padding: 6px 8px; color: {P.brass_text}; }}
QPushButton#link:hover {{ background: {P.raised}; }}
QPushButton#danger {{ background: rgba(240,138,108,0.12); border: 1px solid rgba(240,138,108,0.28); color: {P.coral}; }}
QPushButton#x {{ background: transparent; border: none; padding: 0; min-width: 28px; max-width: 28px;
    min-height: 28px; max-height: 28px; border-radius: 8px; }}
QPushButton#x:hover {{ background: {P.raised_hi}; }}
QPushButton#winctl {{ background: transparent; border: none; border-radius: 8px; padding: 0; min-width: 44px;
    max-width: 44px; min-height: 36px; max-height: 36px; }}
QPushButton#winctl:hover {{ background: {P.raised}; }}
QPushButton#winclose {{ background: transparent; border: none; border-radius: 8px; padding: 0; min-width: 44px;
    max-width: 44px; min-height: 36px; max-height: 36px; }}
QPushButton#winclose:hover {{ background: #C42B1C; }}
QLineEdit, QSpinBox {{ background: {P.field}; border: 1px solid {P.line2}; border-radius: 12px; padding: 10px 14px;
    selection-background-color: rgba(216,180,106,0.4); }}
QLineEdit:focus, QSpinBox:focus {{ border-color: {T.BRASS}; }}
QComboBox {{ background: {P.field}; border: 1px solid {P.line2}; border-radius: 10px; padding: 7px 12px; }}
QComboBox:hover {{ border-color: {T.BRASS}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {P.panel}; border: 1px solid {P.line2}; outline: none; padding: 4px;
    selection-background-color: {P.raised}; selection-color: {P.text}; }}
QCheckBox {{ spacing: 10px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {P.line2};
    background: {P.field}; }}
QCheckBox::indicator:checked {{ background: {T.BRASS}; border-color: {T.BRASS}; }}
QProgressBar {{ background: {P.line}; border: none; border-radius: 2px; max-height: 4px; min-height: 4px; }}
QProgressBar::chunk {{ background: {T.BRASS}; border-radius: 2px; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {P.scroll}; border-radius: 3px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{ height: 0; background: none; }}
QToolTip {{ background: {P.panel}; color: {P.text}; border: 1px solid {P.line2}; padding: 6px 8px; }}
QMenu {{ background: {P.panel}; border: 1px solid {P.line2}; padding: 6px; }}
QMenu::item {{ padding: 7px 18px; border-radius: 8px; }}
QMenu::item:selected {{ background: {P.raised}; }}
QMenu::separator {{ height: 1px; background: {P.line}; margin: 4px 8px; }}
"""


def apply_look(palette: T.Palette, lang: str | None = None) -> None:
    """Switches palette (and type for a language) everywhere, live."""
    global P, LANG
    P = palette
    if lang:
        LANG = lang
    app = QApplication.instance()
    app.setStyleSheet(qss())
    for w, (name, color_role, size) in list(_ICONED.items()):
        set_icon(w, name, color_role, size)
    for w in app.topLevelWidgets():
        dark_frame(w)
    LOOK.changed.emit()


def dark_frame(widget: QWidget) -> None:
    """Native frame and caption colors that match the palette (Windows 11; harmless elsewhere)."""
    if sys.platform != "win32" or not widget.isWindow() or not widget.testAttribute(Qt.WidgetAttribute.WA_WState_Created):
        return
    try:
        hwnd = wintypes.HWND(int(widget.winId()))
        v = ctypes.c_int(1 if P.dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(v), 4)  # immersive dark mode
        c = qc(P.ground)
        cref = ctypes.c_uint(c.red() | c.green() << 8 | c.blue() << 16)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(cref), 4)  # caption color
    except (OSError, AttributeError):
        pass


# ------------------------------------------------------------------ small building blocks
def label(text: str = "", name: str = "", wrap: bool = False, rich: bool = False) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    lab.setTextFormat(Qt.TextFormat.RichText if rich else Qt.TextFormat.PlainText)
    return lab


def button(text: str = "", kind: str = "", tip: str = "", icon: str = "", icon_role: str = "",
           icon_size: int = 16) -> QPushButton:
    b = QPushButton(text)
    if kind:
        b.setObjectName(kind)
    if tip:
        b.setToolTip(tip)
    if icon:
        set_icon(b, icon, icon_role or ("ink" if kind == "primary" else "text"), icon_size)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def panel(title: str, meta: QWidget | None = None, margins: int = 20) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("panel")
    col = QVBoxLayout(frame)
    col.setContentsMargins(margins, 16, margins, margins)
    col.setSpacing(14)
    head = QHBoxLayout()
    head.setSpacing(8)
    head.addWidget(label(title, "title"))
    head.addStretch(1)
    if meta is not None:
        head.addWidget(meta)
    col.addLayout(head)
    return frame, col


def icon_tile(name: str, size: int = 36, color_role: str = "text2", kind: str = "tile") -> QLabel:
    t = QLabel()
    t.setObjectName(kind)
    t.setFixedSize(size, size)
    t.setAlignment(Qt.AlignmentFlag.AlignCenter)
    set_icon(t, name, color_role, 18)
    return t


def size_text(n: float) -> str:
    """"46.9 KB", kept in that order inside right-to-left text (LRI ... PDI)."""
    if n < 1024:
        return f"⁦{int(n)} B⁩"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024
        if n < 1024 or unit == "TB":
            num = f"{n:.0f}" if n >= 100 else f"{n:.1f}" if n >= 10 else f"{n:.2f}"
            return f"⁦{num} {unit}⁩"
    return f"⁦{n:.1f} TB⁩"


def ago(t: float) -> str:
    s = time.time() - t
    if s < 60:
        return tr("just_now")
    if s < 3600:
        return tr("min_ago", n=int(s // 60))
    if s < 86400:
        return tr("h_ago", n=int(s // 3600))
    return time.strftime("%Y-%m-%d", time.localtime(t))


class Speed:
    """Bytes per second over the last few seconds."""

    def __init__(self):
        self.samples: list[tuple[float, int]] = []

    def add(self, done: int) -> float:
        t = time.monotonic()
        self.samples.append((t, done))
        self.samples = [s for s in self.samples if t - s[0] < 3.0]
        (t0, d0), (t1, d1) = self.samples[0], self.samples[-1]
        return (d1 - d0) / (t1 - t0) if t1 > t0 else 0.0


class ElideLabel(QLabel):
    """A one-line label that shortens its text with … to fit, at the end or in the middle."""

    def __init__(self, text: str = "", name: str = "", middle: bool = False):
        super().__init__()
        if name:
            self.setObjectName(name)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.mode = Qt.TextElideMode.ElideMiddle if middle else Qt.TextElideMode.ElideRight
        self.full = text
        self._fit()

    def setFullText(self, text: str) -> None:  # noqa: N802
        self.full = text
        self.setToolTip(text if len(text) > 40 else "")
        self._fit()

    def _fit(self) -> None:
        # LRM: an Arabic name keeps its extension on the right in a left-to-right list, as Explorer shows it
        # (RLM in Arabic: a Latin name still starts on the right, like the rest of the line)
        mark = "‏" if LANG in RTL else "‎"
        self.setText(mark + self.fontMetrics().elidedText(self.full, self.mode, max(24, self.width())))

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        self._fit()

    def changeEvent(self, e) -> None:  # noqa: N802
        super().changeEvent(e)
        if e.type() in (e.Type.FontChange, e.Type.StyleChange):
            self._fit()


class Dot(QWidget):
    def __init__(self, color_role: str = "sea", size: int = 8):
        super().__init__()
        self.color_role = color_role
        self.setFixedSize(size, size)
        LOOK.changed.connect(self.update)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(role(self.color_role)))
        p.drawEllipse(self.rect())
        p.end()


class Row(QFrame):
    """One line in a list: an icon tile, a name, a small line with an optional status dot,
    an optional progress bar, and quiet buttons at the end."""

    def __init__(self, title: str, sub: str = "", icon: str = "file", tile: int = 36):
        super().__init__()
        self.setObjectName("row")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 8, 6, 8)
        lay.setSpacing(12)
        self.tile = icon_tile(icon, tile)
        lay.addWidget(self.tile)
        col = QVBoxLayout()
        col.setSpacing(4)
        self.title = ElideLabel(title, "name", middle=True)
        col.addWidget(self.title)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1000)
        self.bar.hide()
        col.addWidget(self.bar)
        subrow = QHBoxLayout()
        subrow.setSpacing(6)
        self.dot = Dot()
        self.dot.hide()
        subrow.addWidget(self.dot, 0, Qt.AlignmentFlag.AlignVCenter)
        self.sub = ElideLabel(sub, "sub")
        subrow.addWidget(self.sub, 1)
        self.rich = label("", "sub", wrap=True, rich=True)  # status + address, may wrap to a second line
        self.rich.hide()
        subrow.addWidget(self.rich, 1)
        col.addLayout(subrow)
        lay.addLayout(col, 1)
        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(2)
        lay.addLayout(self.buttons)

    def set_sub(self, text: str, state: str = "sub", addr: str = "") -> None:
        """state: "sub" (plain), "ok" (sea glass, with a dot), "bad" (coral); addr goes after it in mono."""
        target = self.rich if addr else self.sub
        self.sub.setVisible(not addr)
        self.rich.setVisible(bool(addr))
        if addr:  # addresses in the mono face, as the brand asks
            mono = T.mono_family(LANG).replace("'", "")
            self.rich.setText(f"{html.escape(text)} · <span style=\"font-family:{mono}; font-size:12px\">"
                              f"{html.escape(addr)}</span>")
        else:
            self.sub.setFullText(text)
        if target.objectName() != state:
            target.setObjectName(state)
            target.style().unpolish(target)
            target.style().polish(target)
        self.dot.setVisible(state == "ok")

    def set_on(self, on: bool) -> None:
        self.setProperty("on", on)
        self.style().unpolish(self)
        self.style().polish(self)

    def add_button(self, text: str, slot, tip: str = "", icon: str = "") -> QPushButton:
        b = button(text, "x" if not text else "ghost", tip, icon, "text2")
        b.clicked.connect(slot)
        self.buttons.addWidget(b)
        return b

    def set_title(self, text: str) -> None:
        self.title.setFullText(text)


# ------------------------------------------------------------------ the QR tile and the code
class QrCode(QWidget):
    """The pairing QR on an ivory tile inside a hairline frame, with the mark in the middle."""

    def __init__(self, size: int = 212):
        super().__init__()
        self.setFixedSize(size, size)
        self.matrix: list = []
        self.text = ""
        LOOK.changed.connect(self.update)

    def set_text(self, text: str) -> None:
        if text == self.text:
            return
        self.text = text
        # level H: the mark in the middle hides a few modules and the code still reads
        self.matrix = [list(r) for r in segno.make(text, error="h", micro=False, boost_error=False).matrix] \
            if text else []
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(qc(P.line2), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r, 20, 20)
        inner = r.adjusted(8, 8, -8, -8)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(P.qr_bg))
        p.drawRoundedRect(inner, 14, 14)
        if self.matrix:
            n = len(self.matrix)
            cell = int((inner.width() - 20) / n)
            off_x = inner.x() + (inner.width() - cell * n) / 2
            off_y = inner.y() + (inner.height() - cell * n) / 2
            p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            p.setBrush(qc(T.INK))
            for y, row in enumerate(self.matrix):
                for x, v in enumerate(row):
                    if v:
                        p.drawRect(int(off_x + x * cell), int(off_y + y * cell), cell, cell)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            badge = int(cell * n * 0.24)
            bx, by = self.width() / 2 - badge / 2, self.height() / 2 - badge / 2
            p.setBrush(qc(P.qr_bg))
            p.drawRoundedRect(QRectF(bx - 4, by - 4, badge + 8, badge + 8), 12, 12)
            dark = {"left": "#8E7B55", "right": T.BRASS, "hull": T.IVORY, "wave": T.BRASS}
            QSvgRenderer(QByteArray(mark_svg(dark, T.HULL, None).encode())).render(p, QRectF(bx, by, badge, badge))
        p.end()


class CodeKeys(QWidget):
    """The 6-digit code as keycaps with a brass edge: 905 – 145."""

    def __init__(self):
        super().__init__()
        self.code = ""
        self.setFixedHeight(48)
        self.setMinimumWidth(250)
        LOOK.changed.connect(self.update)

    def set_code(self, code: str) -> None:
        self.code = code
        self.setToolTip(code)
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        if len(self.code) != 6:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h, gap, dash = 34, 44, 6, 18
        total = 6 * w + 4 * gap + dash
        x = (self.width() - total) / 2
        f = self.font()
        f.setFamilies(["JetBrains Mono"])
        f.setPixelSize(21)
        f.setWeight(f.Weight.Medium)
        p.setFont(f)
        for i, ch in enumerate(self.code):  # digits always read left to right
            if i == 3:
                p.setPen(QPen(qc(P.text3), 1.5))
                p.drawLine(int(x + 4), int(h / 2 + 1), int(x + dash - 4), int(h / 2 + 1))
                x += dash
            rect = QRectF(x, 1, w, h - 2)
            p.setPen(QPen(qc(P.line2), 1))
            p.setBrush(qc(P.well if P.dark else P.field))
            p.drawRoundedRect(rect, 8, 8)
            p.setPen(QPen(qc(T.BRASS), 2))
            p.drawLine(int(rect.left() + 6), int(rect.bottom() - 0.5), int(rect.right() - 6), int(rect.bottom() - 0.5))
            p.setPen(qc(P.text))
            p.drawText(rect.adjusted(0, -1, 0, -1), Qt.AlignmentFlag.AlignCenter, ch)
            x += w + (gap if i not in (2, 5) else 0)
        p.end()


class DropZone(QFrame):
    """Dashed area that takes files and folders from Explorer."""
    dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setObjectName("drop")
        self.setAcceptDrops(True)

    def _hot(self, on: bool) -> None:
        self.setProperty("hot", on)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._hot(True)

    def dragLeaveEvent(self, _e) -> None:  # noqa: N802
        self._hot(False)

    def dropEvent(self, e) -> None:  # noqa: N802
        self._hot(False)
        paths = [Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.dropped.emit(paths)
            e.acceptProposedAction()


class Boat(QWidget):
    """The quiet mark for empty states, with a second wave line."""

    def __init__(self, w: int = 108, h: int = 84):
        super().__init__()
        self.setFixedSize(w, h)
        LOOK.changed.connect(self.update)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        side = float(self.height())
        x0 = (self.width() - side) / 2
        QSvgRenderer(QByteArray(mark_svg(P.muted_mark).encode())).render(p, QRectF(x0, -4, side, side))
        pen = QPen(qc(P.muted_mark["wave"]), 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        y = side - 6
        p.drawLine(int(x0 + side * 0.3), int(y), int(x0 + side * 0.7), int(y))
        p.end()


# ------------------------------------------------------------------ the pairing card that pops up
class Toast(QWidget):
    """A small card at the bottom right of the screen that asks one question."""
    answered = Signal(bool)

    def __init__(self, title: str, sub: str, yes: str, no: str, timeout_s: float, device_icon: str = "phone"):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        frame = QFrame(self)
        frame.setObjectName("toast")
        frame.setStyleSheet(f"QFrame#toast {{ background: {P.panel}; border: 1px solid rgba(216,180,106,0.55);"
                            " border-radius: 18px; }")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        col = QVBoxLayout(frame)
        col.setContentsMargins(18, 16, 18, 16)
        col.setSpacing(12)
        head = QHBoxLayout()
        head.setSpacing(12)
        head.addWidget(icon_tile(device_icon, 40, "brass"), 0, Qt.AlignmentFlag.AlignTop)
        texts = QVBoxLayout()
        texts.setSpacing(4)
        texts.addWidget(label(title, "strong", wrap=True))
        texts.addWidget(label(sub, "muted", wrap=True))
        head.addLayout(texts, 1)
        col.addLayout(head)
        row = QHBoxLayout()
        row.addStretch(1)
        b_no = button(no)
        b_yes = button(yes, "primary")
        b_no.clicked.connect(lambda: self._answer(False))
        b_yes.clicked.connect(lambda: self._answer(True))
        row.addWidget(b_no)
        row.addWidget(b_yes)
        col.addLayout(row)
        self.setFixedWidth(380)
        self._done = False
        QTimer.singleShot(int(timeout_s * 1000), self.close)

    def _answer(self, yes: bool) -> None:
        if not self._done:
            self._done = True
            self.answered.emit(yes)
        self.close()

    def show_near_tray(self, index: int = 0) -> None:
        self.adjustSize()
        geo = QGuiApplication.primaryScreen().availableGeometry()
        self.move(geo.right() - self.width() - 16, geo.bottom() - self.height() - 16 - index * (self.height() + 10))
        self.show()
        self.raise_()
        self.activateWindow()


# ------------------------------------------------------------------ our own title bar on the native frame
class TitleBar(QWidget):
    """Mark, wordmark and tagline on one side; settings and the window buttons on the other."""

    def __init__(self, window: QWidget, on_settings):
        super().__init__(window)
        self.setObjectName("titlebar")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFixedHeight(64)
        self.window_ = window
        lay = QHBoxLayout(self)
        lay.setContentsMargins(22, 0, 10, 0)
        lay.setSpacing(12)
        self.logo = QLabel()
        self.logo.setFixedSize(40, 40)
        lay.addWidget(self.logo)
        lay.addWidget(label("Skiffdrop", "wordmark"))
        lay.addSpacing(4)
        lay.addWidget(label(tr("tagline"), "tagline"), 0, Qt.AlignmentFlag.AlignVCenter)
        lay.addStretch(1)
        self.settings = button("", "winctl", tr("settings"), "settings", "text", 18)
        self.settings.clicked.connect(on_settings)
        lay.addWidget(self.settings)
        sep = QFrame()
        sep.setObjectName("sep")
        sep.setFixedHeight(22)
        lay.addSpacing(4)
        lay.addWidget(sep)
        lay.addSpacing(4)
        self.min = button("", "winctl", tr("minimize"), "min", "text", 16)
        self.max = button("", "winctl", tr("maximize"), "max", "text", 14)
        self.close = button("", "winclose", tr("close"), "close", "text", 16)
        self.min.clicked.connect(window.showMinimized)
        self.max.clicked.connect(lambda: window.showNormal() if window.isMaximized() else window.showMaximized())
        self.close.clicked.connect(window.close)
        for b in (self.min, self.max, self.close):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            lay.addWidget(b)
        self.refresh()
        LOOK.changed.connect(self.refresh)

    def refresh(self) -> None:
        self.logo.setPixmap(tile_mark(40))
        maxed = self.window_.isMaximized()
        set_icon(self.max, "restore" if maxed else "max", "text", 15 if maxed else 14)
        self.max.setToolTip(tr("restore") if maxed else tr("maximize"))


class _NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]


class _MARGINS(ctypes.Structure):
    _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int), ("t", ctypes.c_int), ("b", ctypes.c_int)]


class NativeFrameWindow(QWidget):
    """Keeps the real Windows frame (snap, shadow, rounded corners, animations) but gives the whole
    window to our widgets: WM_NCCALCSIZE drops the caption and WM_NCHITTEST says where to drag and resize."""

    title_height = 64
    edge = 6

    def install_frame(self) -> None:
        if sys.platform != "win32" or QGuiApplication.platformName() != "windows":
            return
        try:
            hwnd = wintypes.HWND(int(self.winId()))
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(_MARGINS(0, 0, 1, 0)))
            v = ctypes.c_int(2)  # DWMWCP_ROUND
            ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 33, ctypes.byref(v), 4)
            # SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED
            ctypes.windll.user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
        except (OSError, AttributeError):
            pass

    def _over_control(self, pos: QPoint) -> bool:
        w = self.childAt(pos)
        while w is not None and w is not self:
            if isinstance(w, (QAbstractButton, QComboBox, QLineEdit)):
                return True
            w = w.parentWidget()
        return False

    def nativeEvent(self, event_type, message):  # noqa: N802
        if sys.platform == "win32" and bytes(event_type) == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0083 and msg.wParam:  # WM_NCCALCSIZE: the whole window is client area
                u = ctypes.windll.user32
                if u.IsZoomed(msg.hWnd):  # a maximized window hangs over the screen edge by its frame
                    params = _NCCALCSIZE_PARAMS.from_address(msg.lParam)
                    try:
                        dpi = u.GetDpiForWindow(msg.hWnd)
                        fx = u.GetSystemMetricsForDpi(32, dpi) + u.GetSystemMetricsForDpi(92, dpi)
                        fy = u.GetSystemMetricsForDpi(33, dpi) + u.GetSystemMetricsForDpi(92, dpi)
                    except AttributeError:
                        fx = u.GetSystemMetrics(32) + u.GetSystemMetrics(92)
                        fy = u.GetSystemMetrics(33) + u.GetSystemMetrics(92)
                    r = params.rgrc[0]
                    r.left, r.top, r.right, r.bottom = r.left + fx, r.top + fy, r.right - fx, r.bottom - fy
                return True, 0
            if msg.message == 0x0084:  # WM_NCHITTEST
                pos = self.mapFromGlobal(QCursor.pos())
                x, y, w, h = pos.x(), pos.y(), self.width(), self.height()
                if not self.isMaximized():
                    e = self.edge
                    left, right, top, bottom = x < e, x >= w - e, y < e, y >= h - e
                    for hit, code in (((top and left), 13), ((top and right), 14), ((bottom and left), 16),
                                      ((bottom and right), 17), (left, 10), (right, 11), (top, 12), (bottom, 15)):
                        if hit:
                            return True, code
                if 0 <= y < self.title_height and not self._over_control(pos):
                    return True, 2  # HTCAPTION: drag, double-click to maximize, snap
        return super().nativeEvent(event_type, message)
