"""Widgets for the PC window: Windows 11 acrylic glass, translucent cards, the QR code."""

from __future__ import annotations

import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

import segno
from PySide6.QtCore import QByteArray, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

ACCENT = "#FF7A59"
INK = "#2B0F06"
OK = "#4FD18B"
WEB = Path(__file__).with_name("web")

QSS = f"""
* {{ font-family: 'Segoe UI Variable Text', 'Segoe UI'; font-size: 13px; color: #EAF0F6; }}
QWidget#root {{ background: transparent; }}

QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; border: none; }}
QFrame#card {{ background: rgba(255,255,255,0.055); border: 1px solid rgba(255,255,255,0.09); border-radius: 14px; }}
QFrame#drop {{ border: 1.5px dashed rgba(255,122,89,0.55); border-radius: 12px; background: rgba(255,122,89,0.06); }}
QFrame#drop[hot="true"] {{ background: rgba(255,122,89,0.18); }}
QFrame#banner {{ background: rgba(255,186,73,0.13); border: 1px solid rgba(255,186,73,0.45); border-radius: 12px; }}
QFrame#row {{ background: transparent; border: none; border-top: 1px solid rgba(255,255,255,0.07); }}
QLabel#title {{ font-size: 22px; font-weight: 600; }}
QLabel#h {{ font-size: 12px; font-weight: 600; color: rgba(234,240,246,0.62); }}
QLabel#muted, QLabel#sub {{ color: rgba(234,240,246,0.6); }}
QLabel#sub {{ font-size: 12px; }}
QLabel#ok {{ color: {OK}; font-size: 12px; }}
QLabel#bad {{ color: #FF6B78; font-size: 12px; }}
QLabel#code {{ font-size: 26px; font-weight: 600; letter-spacing: 3px; }}
QLabel#url {{ font-family: 'Cascadia Mono', Consolas; font-size: 12px; color: rgba(234,240,246,0.8); }}
QComboBox, QLineEdit, QSpinBox {{ background: rgba(0,0,0,0.28); border: 1px solid rgba(255,255,255,0.12);
    border-radius: 8px; padding: 6px 9px; min-height: 20px; }}
QComboBox:hover, QLineEdit:hover {{ border-color: rgba(255,255,255,0.25); }}
QLineEdit:focus {{ border-color: rgba(255,122,89,0.7); }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{ background: #18232F; border: 1px solid rgba(255,255,255,0.12);
    selection-background-color: rgba(255,122,89,0.28); outline: none; padding: 4px; }}
QPushButton {{ background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.12); border-radius: 8px;
    padding: 6px 14px; }}
QPushButton:hover {{ background: rgba(255,255,255,0.14); }}
QPushButton:disabled {{ color: rgba(234,240,246,0.35); }}
QPushButton#primary {{ background: {ACCENT}; color: {INK}; border: none; font-weight: 600; }}
QPushButton#primary:hover {{ background: #FF9476; }}
QPushButton#flat {{ background: transparent; border: none; padding: 4px 8px; color: rgba(234,240,246,0.7); }}
QPushButton#flat:hover {{ color: #FFFFFF; background: rgba(255,255,255,0.08); }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid rgba(255,255,255,0.3);
    background: rgba(0,0,0,0.25); }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QProgressBar {{ background: rgba(255,255,255,0.1); border: none; border-radius: 2px; max-height: 4px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}
QScrollBar:vertical {{ background: transparent; width: 8px; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.18); border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QToolTip {{ background: #18232F; border: 1px solid rgba(255,255,255,0.12); padding: 4px 8px; }}
QMenu {{ background: #18232F; border: 1px solid rgba(255,255,255,0.12); padding: 4px; }}
QMenu::item {{ padding: 6px 18px; border-radius: 6px; }}
QMenu::item:selected {{ background: rgba(255,122,89,0.25); }}
"""


def icon_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    QSvgRenderer(QByteArray((WEB / "icon.svg").read_bytes())).render(p, QRectF(0, 0, size, size))
    p.end()
    return pm


def app_icon() -> QIcon:
    icon = QIcon()
    for s in (16, 20, 24, 32, 40, 48, 64, 128, 256):
        icon.addPixmap(icon_pixmap(s))
    return icon


def png_bytes(pm: QPixmap | QImage, fmt: str = "PNG", quality: int = -1) -> bytes:
    from PySide6.QtCore import QBuffer, QIODevice
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pm.save(buf, fmt, quality)
    return bytes(data)


SOLID = "\nQWidget#root { background: #0F1B27; }"


def acrylic_possible() -> bool:
    """The system backdrop needs Windows 11 22H2 and a real desktop (not the offscreen test platform)."""
    from PySide6.QtGui import QGuiApplication
    return (sys.platform == "win32" and sys.getwindowsversion().build >= 22621
            and QGuiApplication.platformName() == "windows")


def prepare_glass(widget: QWidget) -> None:
    """Call before the window is first shown: see-through only where acrylic will fill it."""
    widget.setObjectName("root")
    widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
    widget.setStyleSheet(QSS + ("" if acrylic_possible() else SOLID))
    if acrylic_possible():
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)


def glass(widget: QWidget) -> None:
    """Dark title bar and acrylic backdrop on Windows 11; a plain dark window elsewhere."""
    ok = False
    if not acrylic_possible():
        try:
            v = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(int(widget.winId())), 20, ctypes.byref(v), 4)
        except (OSError, AttributeError):
            pass
        return
    try:
        hwnd = wintypes.HWND(int(widget.winId()))
        dwm = ctypes.windll.dwmapi

        def attr(key: int, value: int) -> int:
            v = ctypes.c_int(value)
            return dwm.DwmSetWindowAttribute(hwnd, key, ctypes.byref(v), ctypes.sizeof(v))

        attr(20, 1)  # DWMWA_USE_IMMERSIVE_DARK_MODE
        ok = attr(38, 3) == 0  # DWMWA_SYSTEMBACKDROP_TYPE = transient (acrylic)

        class MARGINS(ctypes.Structure):
            _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int), ("t", ctypes.c_int), ("b", ctypes.c_int)]
        if ok:
            dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(MARGINS(-1, -1, -1, -1)))
    except (OSError, AttributeError):
        ok = False
    if not ok and SOLID not in widget.styleSheet():  # the backdrop was refused: paint a solid one
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        widget.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, False)
        widget.setStyleSheet(widget.styleSheet() + SOLID)


def card(title: str = "") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("card")
    col = QVBoxLayout(frame)
    col.setContentsMargins(16, 14, 16, 16)
    col.setSpacing(10)
    if title:
        h = QLabel(title.upper())
        h.setObjectName("h")
        col.addWidget(h)
    return frame, col


def label(text: str = "", name: str = "", wrap: bool = False) -> QLabel:
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    return lab


def button(text: str, name: str = "", tip: str = "") -> QPushButton:
    b = QPushButton(text)
    if name:
        b.setObjectName(name)
    if tip:
        b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def size_text(n: float) -> str:
    if n < 1024:
        return f"{int(n)} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if n >= 100 else f"{n:.1f} {unit}" if n >= 10 else f"{n:.2f} {unit}"
    return f"{n:.1f} TB"


def ago(t: float) -> str:
    s = time.time() - t
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{int(s // 60)} min ago"
    if s < 86400:
        return f"{int(s // 3600)} h ago"
    return time.strftime("%d %b", time.localtime(t))


class QrCode(QWidget):
    """The pairing QR code on a white rounded tile, with a quiet zone the camera needs."""

    def __init__(self, size: int = 248):
        super().__init__()
        self.setFixedSize(size, size)
        self.matrix: list = []
        self.text = ""

    def set_text(self, text: str) -> None:
        if text == self.text:
            return
        self.text = text
        self.matrix = [list(row) for row in segno.make(text, error="m", micro=False).matrix] if text else []
        self.setToolTip("")
        self.update()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#FFFFFF"))
        p.drawRoundedRect(self.rect(), 16, 16)
        if not self.matrix:
            p.end()
            return
        n = len(self.matrix)
        quiet = 3
        cell = int(self.width() / (n + 2 * quiet))
        off = (self.width() - cell * n) // 2
        p.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        p.setBrush(QColor("#0B1622"))
        for y, row in enumerate(self.matrix):
            for x, v in enumerate(row):
                if v:
                    p.drawRect(off + x * cell, off + y * cell, cell, cell)
        p.end()


class DropZone(QFrame):
    """Dashed area that takes files and folders from Explorer."""
    dropped = Signal(list)

    def __init__(self):
        super().__init__()
        self.setObjectName("drop")
        self.setAcceptDrops(True)
        self.setMinimumHeight(96)

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


class Row(QFrame):
    """One line in a list card: title, small text, optional progress and buttons."""

    def __init__(self, title: str, sub: str = "", glyph: str = ""):
        super().__init__()
        self.setObjectName("row")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 8, 2, 8)
        lay.setSpacing(10)
        if glyph:
            g = QLabel(glyph)
            g.setFixedWidth(22)
            g.setAlignment(Qt.AlignmentFlag.AlignCenter)
            g.setStyleSheet(f"color: {ACCENT}; font-size: 15px; font-weight: 600;")
            lay.addWidget(g)
        col = QVBoxLayout()
        col.setSpacing(3)
        self.title = QLabel(title)
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignAbsolute | Qt.AlignmentFlag.AlignVCenter)
        self.title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.full_title = title
        col.addWidget(self.title)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 1000)
        self.bar.hide()
        col.addWidget(self.bar)
        self.sub = label(sub, "sub")
        self.sub.setTextFormat(Qt.TextFormat.PlainText)
        self.sub.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        col.addWidget(self.sub)
        lay.addLayout(col, 1)
        self.buttons = QHBoxLayout()
        self.buttons.setSpacing(6)
        lay.addLayout(self.buttons)

    def add_button(self, text: str, slot, tip: str = "") -> QPushButton:
        b = button(text, "flat", tip)
        b.clicked.connect(slot)
        self.buttons.addWidget(b)
        return b

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        fm = self.title.fontMetrics()
        # LRM: an Arabic name keeps its extension on the right, as Explorer shows it
        self.title.setText("‎" + fm.elidedText(self.full_title, Qt.TextElideMode.ElideMiddle,
                                                     max(40, self.title.width())))


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


class Toast(QWidget):
    """A small glass card at the bottom-right of the screen that asks one question."""
    answered = Signal(bool)

    def __init__(self, title: str, sub: str, yes: str, no: str, timeout_s: float):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet(QSS)
        frame = QFrame(self)
        frame.setObjectName("card")
        frame.setStyleSheet("QFrame#card { background: rgba(20,32,45,0.97); border: 1px solid rgba(255,122,89,0.55);"
                            " border-radius: 14px; }")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(frame)
        col = QVBoxLayout(frame)
        col.setContentsMargins(18, 16, 18, 16)
        col.setSpacing(6)
        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icon_pixmap(28))
        head.addWidget(logo)
        t = label(title, "")
        t.setStyleSheet("font-size: 15px; font-weight: 600;")
        t.setWordWrap(True)
        head.addWidget(t, 1)
        col.addLayout(head)
        col.addWidget(label(sub, "muted", wrap=True))
        row = QHBoxLayout()
        row.addStretch(1)
        b_no = button(no)
        b_yes = button(yes, "primary")
        b_no.clicked.connect(lambda: self._answer(False))
        b_yes.clicked.connect(lambda: self._answer(True))
        row.addWidget(b_no)
        row.addWidget(b_yes)
        col.addSpacing(6)
        col.addLayout(row)
        self.setFixedWidth(360)
        self._done = False
        QTimer.singleShot(int(timeout_s * 1000), self.close)

    def _answer(self, yes: bool) -> None:
        if not self._done:
            self._done = True
            self.answered.emit(yes)
        self.close()

    def show_near_tray(self, index: int = 0) -> None:
        from PySide6.QtGui import QGuiApplication
        self.adjustSize()
        geo = QGuiApplication.primaryScreen().availableGeometry()
        self.move(geo.right() - self.width() - 16, geo.bottom() - self.height() - 16 - index * (self.height() + 10))
        self.show()
        self.raise_()
        self.activateWindow()


def grid_form() -> QGridLayout:
    g = QGridLayout()
    g.setHorizontalSpacing(12)
    g.setVerticalSpacing(10)
    return g


__all__ = ["ACCENT", "QSS", "QSize", "DropZone", "QrCode", "Row", "Speed", "Toast", "app_icon", "button", "card",
           "glass", "grid_form", "icon_pixmap", "label", "png_bytes", "size_text", "ago"]
