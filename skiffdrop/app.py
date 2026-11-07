"""The PC side: the Harbor window with the QR code, a tray icon, and the server behind them."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QImageReader
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
                               QLineEdit, QMenu, QScrollArea, QSizePolicy, QSpinBox, QSystemTrayIcon,
                               QVBoxLayout, QWidget)

from . import __version__, netutil
from . import theme as T
from . import ui
from .config import APP, Devices, Settings, config_dir
from .history import History
from .i18n import LANGUAGES, RTL, set_language, tr
from .server import PAIR_TTL, Hub, Listener, PairRequest, Transfer
from .ui import (Ask, Boat, CodeKeys, DropZone, MessageRow, NativeFrameWindow, QrCode, Row, Speed, TitleBar, Toast, ago,
                 app_icon,
                 button, icon_pixmap, icon_tile, label, panel, png_bytes, set_icon, size_text)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
THUMB_EXT = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"}


def thumbnail(path: Path) -> bytes | None:
    """A small JPEG for the phone's list; runs on a server thread (QImage is fine off the GUI thread)."""
    if path.suffix.lower() not in THUMB_EXT:
        return None
    r = QImageReader(str(path))
    r.setAutoTransform(True)
    size = r.size()
    if not size.isValid():
        return None
    scale = 200 / max(size.width(), size.height(), 1)
    if scale < 1:
        r.setScaledSize(QSize(max(1, int(size.width() * scale)), max(1, int(size.height() * scale))))
    img = r.read()
    return png_bytes(img, "JPEG", 82) if not img.isNull() else None


class Bridge(QObject, Listener):
    """Server threads -> Qt signals (queued onto the GUI thread)."""
    pair = Signal(object)
    devices = Signal()
    transfer_sig = Signal(object)
    text = Signal(object, str)
    code = Signal()

    def pair_requested(self, req):
        self.pair.emit(req)

    def devices_changed(self):
        self.devices.emit()

    def transfer(self, t):
        self.transfer_sig.emit(t)

    def text_received(self, device, text):
        self.text.emit(device, text)

    def code_changed(self):
        self.code.emit()


def palette_for(choice: str) -> T.Palette:
    if choice == "dark":
        return T.DARK
    if choice == "light":
        return T.LIGHT
    return T.LIGHT if QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Light else T.DARK


def startup_command() -> str | None:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --background'
    return None


def startup_enabled() -> bool:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP)
            return True
    except OSError:
        return False


def set_startup(on: bool) -> None:
    import winreg
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
        if on and startup_command():
            winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(k, APP)
            except OSError:
                pass


def listening_program() -> str:
    """The process that owns the socket (the firewall rule is per program)."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return getattr(sys, "_base_executable", sys.executable)


def reveal(path: Path) -> None:
    if path.is_file():
        subprocess.Popen(["explorer", "/select,", str(path)])
    else:
        os.startfile(str(path if path.exists() else path.parent))  # noqa: S606


def section(title: str) -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("panel")
    col = QVBoxLayout(frame)
    col.setContentsMargins(20, 16, 20, 18)
    col.setSpacing(10)
    col.addWidget(label(title, "strong"))
    return frame, col


class SettingsDialog(QDialog):
    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self.main = parent
        s = parent.settings
        self.setWindowTitle(tr("settings"))
        self.setObjectName("root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setMinimumWidth(560)
        col = QVBoxLayout(self)
        col.setContentsMargins(20, 20, 20, 20)
        col.setSpacing(12)
        col.addWidget(label(tr("settings"), "title"))

        frame, c = section(tr("appearance"))
        g = QHBoxLayout()
        g.setSpacing(10)
        g.addWidget(label(tr("theme"), "muted"))
        self.theme = QComboBox()
        for key in ("system", "dark", "light"):
            self.theme.addItem(tr(f"theme_{key}"), key)
        self.theme.setCurrentIndex(max(0, self.theme.findData(s.theme)))
        self.theme.currentIndexChanged.connect(self._theme)
        g.addWidget(self.theme)
        g.addSpacing(12)
        g.addWidget(label(tr("language"), "muted"))
        self.lang = QComboBox()
        self.lang.addItem(tr("lang_system"), "")
        for code, name in LANGUAGES.items():
            self.lang.addItem(name, code)
        self.lang.setCurrentIndex(max(0, self.lang.findData(s.lang)))
        self.lang.currentIndexChanged.connect(self._lang)
        g.addWidget(self.lang)
        g.addStretch(1)
        c.addLayout(g)
        r = QHBoxLayout()
        self.lang_note = label(tr("restart_note"), "sub")
        r.addWidget(self.lang_note, 1)
        self.restart = button(tr("restart_now"), "", "", "refresh")
        self.restart.clicked.connect(parent.restart)
        r.addWidget(self.restart)
        c.addLayout(r)
        self.lang_note.hide()
        self.restart.hide()
        col.addWidget(frame)

        frame, c = section(tr("save_to"))
        row = QHBoxLayout()
        self.folder = label(str(s.folder), "url")
        self.folder.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.folder.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        row.addWidget(self.folder, 1)
        b = button(tr("change"), "", "", "folder")
        b.clicked.connect(self._folder)
        row.addWidget(b)
        c.addLayout(row)
        col.addWidget(frame)

        frame, c = section(tr("security"))
        c.addWidget(label(tr("security_text"), "muted", wrap=True))
        row = QHBoxLayout()
        self.pin = QLineEdit()
        self.pin.setPlaceholderText(tr("pin_ph_on") if s.has_pin else tr("pin_ph_off"))
        self.pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin.setMaxLength(12)
        row.addWidget(self.pin, 1)
        b = button(tr("set_pin"), "", "", "lock")
        b.clicked.connect(self._set_pin)
        row.addWidget(b)
        self.pin_off = button(tr("pin_off"), "danger")
        self.pin_off.setEnabled(s.has_pin)
        self.pin_off.clicked.connect(self._pin_off)
        row.addWidget(self.pin_off)
        c.addLayout(row)
        col.addWidget(frame)

        frame, c = section(tr("behaviour"))
        for text, attr in ((tr("copy_text"), "copy_text"), (tr("notify"), "notify")):
            box = QCheckBox(text)
            box.setChecked(getattr(s, attr))
            box.toggled.connect(lambda v, a=attr: self._set(a, v))
            c.addWidget(box)
        self.startup = QCheckBox(tr("startup"))
        self.startup.setChecked(startup_enabled())
        self.startup.setEnabled(startup_command() is not None)
        self.startup.toggled.connect(set_startup)
        c.addWidget(self.startup)
        g = QHBoxLayout()
        g.addWidget(label(tr("port"), "muted"))
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(s.port)
        self.port.valueChanged.connect(lambda v: self._set("port", v))
        g.addWidget(self.port)
        g.addWidget(label(tr("port_note"), "sub"))
        g.addStretch(1)
        c.addLayout(g)
        col.addWidget(frame)

        frame, c = section(tr("firewall"))
        c.addWidget(label(tr("firewall_text"), "muted", wrap=True))
        row = QHBoxLayout()
        self.fw = label("", "sub")
        row.addWidget(self.fw, 1)
        b = button(tr("allow_fw"), "", tr("allow_fw_tip"), "shield")
        b.clicked.connect(parent.fix_firewall)
        row.addWidget(b)
        c.addLayout(row)
        col.addWidget(frame)

        foot = QHBoxLayout()
        foot.addWidget(label(f"Skiffdrop {__version__} · MIT · github.com/Niro54321/Skiffdrop", "sub"), 1)
        close = button(tr("done"), "primary")
        close.clicked.connect(self.accept)
        foot.addWidget(close)
        col.addLayout(foot)
        self.refresh()

    def refresh(self) -> None:
        self.fw.setText(tr("rule_ok") if self.main.rule_ok else tr("rule_missing"))

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        ui.dark_frame(self)

    def _set(self, name: str, value) -> None:
        setattr(self.main.settings, name, value)
        self.main.settings.save()

    def _theme(self) -> None:
        self._set("theme", self.theme.currentData())
        ui.apply_look(palette_for(self.main.settings.theme))

    def _lang(self) -> None:
        self._set("lang", self.lang.currentData())
        self.lang_note.show()
        self.restart.show()

    def _folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("folder_dialog"), str(self.main.settings.folder))
        if d:
            self._set("save_dir", d)
            self.folder.setText(d)
            self.main.empty_path.setText(d)

    def _set_pin(self) -> None:
        pin = self.pin.text().strip()
        if not (pin.isdigit() and 4 <= len(pin) <= 12):
            Ask.inform(self, "PIN", tr("pin_digits"), tr("ok"), "lock")
            return
        self.main.settings.set_pin(pin)
        self.main.settings.save()
        self.pin.clear()
        self.pin.setPlaceholderText(tr("pin_ph_on"))
        self.pin_off.setEnabled(True)
        self.main.refresh_qr()

    def _pin_off(self) -> None:
        self.main.settings.set_pin("")
        self.main.settings.save()
        self.pin.setPlaceholderText(tr("pin_ph_off"))
        self.pin_off.setEnabled(False)
        self.main.refresh_qr()


class MainWindow(NativeFrameWindow):
    net_checked = Signal(str, str, bool)   # network category, network name, firewall rule exists

    def __init__(self, hub: Hub, settings: Settings, bridge: Bridge, restart=None):
        super().__init__()
        self.hub, self.settings, self.bridge = hub, settings, bridge
        self._restart = restart
        self.rule_ok = True
        self.category = ""
        self.network_name = ""
        self.phone_reached = False
        self.history = History(settings.path.parent if settings.path else config_dir())
        self.rows: dict[str, Row] = {}
        self.speeds: dict[str, Speed] = {}
        self.shared_rows: dict[str, Row] = {}
        self.toasts: list[Toast] = []
        self.received_batch: list[tuple[str, str]] = []
        self.quitting = False
        self.dialog: SettingsDialog | None = None
        self._framed = False

        self.setWindowTitle("Skiffdrop")
        self.setWindowIcon(app_icon())
        self.setObjectName("root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setAcceptDrops(True)
        self.resize(1160, 900)
        self.setMinimumSize(960, 780)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.titlebar = TitleBar(self, self.open_settings)
        root.addWidget(self.titlebar)
        body = QHBoxLayout()
        body.setContentsMargins(24, 20, 24, 24)
        body.setSpacing(20)
        root.addLayout(body, 1)

        # ---------------------------------------------------------- left: pairing and devices
        left = QVBoxLayout()
        left.setSpacing(20)
        frame, c = panel(tr("pair_title"), label(tr("pair_meta"), "meta"))
        c.setSpacing(12)
        self.qr = QrCode(212)
        c.addWidget(self.qr, 0, Qt.AlignmentFlag.AlignHCenter)
        self.url = label("", "url")
        self.url.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.url.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        c.addWidget(self.url)
        hint = label(tr("or_type"), "muted")
        hint.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        c.addWidget(hint)
        self.code = CodeKeys()
        c.addWidget(self.code)
        self.addr = QComboBox()
        self.addr.setToolTip(tr("addr_tip"))
        self.addr.currentIndexChanged.connect(self._address_picked)
        c.addWidget(self.addr)
        renew = button(tr("new_code"), "", tr("new_code_tip"), "refresh")
        renew.setMinimumHeight(40)
        renew.clicked.connect(self.hub.renew_code)
        c.addWidget(renew)
        self.pin_note = label(tr("pin_on"), "sub")
        self.pin_note.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        c.addWidget(self.pin_note)
        frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        left.addWidget(frame)

        self.paired_meta = label("", "meta")
        frame, c = panel(tr("devices"), self.paired_meta)
        c.setSpacing(6)
        self.devices_box = QVBoxLayout()
        self.devices_box.setSpacing(4)
        holder = QWidget()
        hb = QVBoxLayout(holder)
        hb.setContentsMargins(0, 0, 0, 0)
        hb.addLayout(self.devices_box)
        hb.addStretch(1)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(holder)
        c.addWidget(scroll, 1)
        self.no_devices = label(tr("no_devices"), "muted", wrap=True)
        c.addWidget(self.no_devices)
        left.addWidget(frame, 1)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(340)
        body.addWidget(lw)

        # ---------------------------------------------------------- right: warning, send, activity
        right = QVBoxLayout()
        right.setSpacing(20)
        self.banner = self._banner()
        right.addWidget(self.banner)

        stays = QWidget()
        sl = QHBoxLayout(stays)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(6)
        lock = label()
        set_icon(lock, "lock", "text2", 15)
        sl.addWidget(lock)
        sl.addWidget(label(tr("stays"), "meta"))
        frame, c = panel(tr("send_title"), stays)
        self.drop = DropZone()

        dl = QVBoxLayout(self.drop)
        dl.setContentsMargins(16, 18, 16, 18)
        dl.setSpacing(6)
        circle = icon_tile("upload", 40, "text", "circle")
        dl.addWidget(circle, 0, Qt.AlignmentFlag.AlignHCenter)
        dl.addSpacing(4)
        t = label(tr("drop_title"), "strong")
        t.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        dl.addWidget(t)
        s = label(tr("drop_sub"), "muted")
        s.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        dl.addWidget(s)
        dl.addSpacing(8)
        btns = QHBoxLayout()
        btns.setSpacing(10)
        btns.addStretch(1)
        b = button(tr("add_files"), "", "", "file_plus")
        b.clicked.connect(self._add_files)
        btns.addWidget(b)
        b = button(tr("add_folder"), "", "", "folder")
        b.clicked.connect(self._add_folder)
        btns.addWidget(b)
        self.clear_shared = button(tr("remove_all"), "ghost")
        self.clear_shared.clicked.connect(lambda: self.hub.unshare(None))
        btns.addWidget(self.clear_shared)
        btns.addStretch(1)
        dl.addLayout(btns)
        self.drop.dropped.connect(self.share)
        c.addWidget(self.drop)
        self.shared_box = QVBoxLayout()
        self.shared_box.setSpacing(2)
        sw = QWidget()
        sw.setLayout(self.shared_box)
        self.shared_scroll = QScrollArea()
        self.shared_scroll.setWidgetResizable(True)
        self.shared_scroll.setWidget(sw)
        self.shared_scroll.hide()
        c.addWidget(self.shared_scroll)
        trow = QHBoxLayout()
        trow.setSpacing(10)
        self.text = QLineEdit()
        self.text.setPlaceholderText(tr("text_ph"))
        self.text.returnPressed.connect(self._send_text)
        trow.addWidget(self.text, 1)
        b = button(tr("paste"), "", tr("paste_tip"), "clipboard")
        b.setMinimumHeight(42)
        b.clicked.connect(self._send_clipboard)
        trow.addWidget(b)
        rtl = ui.LANG in RTL
        send = button(tr("send"), "primary", "", "arrow_left" if rtl else "arrow_right", "ink")
        send.setMinimumHeight(42)
        # the arrow trails the word, in reading order
        send.setLayoutDirection(Qt.LayoutDirection.LeftToRight if rtl else Qt.LayoutDirection.RightToLeft)
        send.clicked.connect(self._send_text)
        trow.addWidget(send)
        c.addLayout(trow)
        frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        right.addWidget(frame)

        lists = QHBoxLayout()
        lists.setSpacing(20)
        tools = QWidget()
        tl = QHBoxLayout(tools)
        tl.setContentsMargins(0, 0, 0, 0)
        b = button(tr("clear"), "ghost", tr("clear_msgs_tip"))
        b.clicked.connect(self._clear_messages)
        tl.addWidget(b)
        frame, c = panel(tr("messages"), tools)
        empty = QWidget()
        el = QVBoxLayout(empty)
        el.setSpacing(8)
        el.addStretch(1)
        el.addWidget(icon_tile("text", 40), 0, Qt.AlignmentFlag.AlignHCenter)
        t = label(tr("no_messages"), "strong")
        t.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        el.addWidget(t)
        t = label(tr("no_messages_sub"), "muted", wrap=True)
        t.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        el.addWidget(t)
        el.addStretch(1)
        self.msg_list, self.msg_scroll, self.msg_empty = self._list_well(c, empty)
        lists.addWidget(frame, 5)

        tools = QWidget()
        tl = QHBoxLayout(tools)
        tl.setContentsMargins(0, 0, 0, 0)
        tl.setSpacing(2)
        self.total = label("", "meta")
        tl.addWidget(self.total)
        b = button("", "x", tr("open_folder"), "folder", "text", 16)
        b.clicked.connect(lambda: reveal(self.settings.folder))
        tl.addWidget(b)
        b = button(tr("clear"), "ghost", tr("clear_files_tip"))
        b.clicked.connect(self._clear_files)
        tl.addWidget(b)
        frame, c = panel(tr("files"), tools)
        empty = QWidget()
        el = QVBoxLayout(empty)
        el.setSpacing(8)
        el.addStretch(1)
        el.addWidget(Boat(), 0, Qt.AlignmentFlag.AlignHCenter)
        et = label(tr("empty_title"), "strong", wrap=True)
        et.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        el.addWidget(et)
        es = label(tr("empty_sub"), "muted", wrap=True)
        es.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        el.addWidget(es)
        self.empty_path = label(str(self.settings.folder), "path")
        self.empty_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        el.addWidget(self.empty_path, 0, Qt.AlignmentFlag.AlignHCenter)
        el.addStretch(1)
        self.file_list, self.file_scroll, self.file_empty = self._list_well(c, empty)
        lists.addWidget(frame, 6)
        right.addLayout(lists, 1)
        body.addLayout(right, 1)

        # ---------------------------------------------------------- wiring
        bridge.pair.connect(self.ask_pair)
        bridge.devices.connect(self.refresh_devices)
        bridge.transfer_sig.connect(self.on_transfer)
        bridge.text.connect(self.on_text)
        bridge.code.connect(self.refresh_qr)
        self.net_checked.connect(self._net_result)
        self._last_shared_version = -1
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.timer.start(1000)
        self.notify_timer = QTimer(self)
        self.notify_timer.setSingleShot(True)
        self.notify_timer.timeout.connect(self._notify_received)
        self.net_timer = QTimer(self)
        self.net_timer.timeout.connect(self.check_network)  # notices when the network is switched to Private
        self.net_timer.start(45_000)
        self.load_addresses()
        self.refresh_devices()
        self.refresh_shared()
        for m in self.history.messages:
            self._message_row(m)
        for f in self.history.files:
            self._file_row(f)

    # ---------------------------------------------------------------- frame and tray behaviour
    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        if not self._framed:
            self._framed = True
            self.install_frame()
        ui.dark_frame(self)

    def changeEvent(self, e) -> None:  # noqa: N802
        super().changeEvent(e)
        if e.type() == e.Type.WindowStateChange:
            self.titlebar.refresh()

    def closeEvent(self, e) -> None:  # noqa: N802
        if self.quitting:
            return super().closeEvent(e)
        e.ignore()
        self.hide()
        app = QApplication.instance()
        if not getattr(app, "_told_tray", False) and getattr(app, "tray", None):
            app._told_tray = True
            app.tray.showMessage(tr("still_on_title"), tr("still_on"), app_icon(), 4000)

    def bring_up(self) -> None:
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()

    def restart(self) -> None:
        if self._restart:
            self._restart()

    # ---------------------------------------------------------------- network + QR
    def load_addresses(self) -> None:
        self.addresses = netutil.addresses()
        self.addr.blockSignals(True)
        self.addr.clear()
        for a in self.addresses:
            self.addr.addItem(a.label(), a.ip)
        if not self.addresses:
            self.addr.addItem(tr("no_network"), "")
        pick = next((i for i, a in enumerate(self.addresses) if a.ip == self.settings.ip), 0)
        self.addr.setCurrentIndex(pick)
        self.addr.blockSignals(False)
        self.addr.setVisible(len(self.addresses) != 1)
        self.refresh_qr()
        self.check_network()

    def _address_picked(self, i: int) -> None:
        if 0 <= i < len(self.addresses):
            self.settings.ip = self.addresses[i].ip
            self.settings.save()
        self.refresh_qr()
        self.check_network()

    def current_address(self):
        i = self.addr.currentIndex()
        return self.addresses[i] if 0 <= i < len(self.addresses) else None

    def refresh_qr(self) -> None:
        a = self.current_address()
        if not a:
            self.qr.set_text("")
            self.url.setText(tr("no_network"))
            self.code.set_code("")
            return
        self.qr.set_text(self.hub.url(a.ip))
        self.url.setText(self.hub.url(a.ip, with_key=False).rstrip("/"))
        self.code.set_code(self.hub.code)
        self.pin_note.setVisible(self.settings.has_pin)
        app = QApplication.instance()
        if getattr(app, "tray", None):
            app.tray.setToolTip(f"Skiffdrop · {a.ip}:{self.hub.port}")

    def check_network(self) -> None:
        a = self.current_address()

        def work():
            cat, name = netutil.network_profile(a.if_index) if a else ("", "")
            self.net_checked.emit(cat, name, netutil.firewall_rule_exists())
        threading.Thread(target=work, daemon=True).start()

    def _net_result(self, category: str, name: str, rule: bool) -> None:
        self.category, self.network_name, self.rule_ok = category, name, rule
        self._update_banner()
        if self.dialog:
            self.dialog.refresh()

    def _update_banner(self) -> None:
        a = self.current_address()
        public = self.category == "Public"
        quiet = bool(self.network_name) and self.network_name in self.settings.quiet_networks
        show = (public or not self.rule_ok) and not quiet and not self.phone_reached
        self.banner_public.setVisible(public)
        self.banner_rule.setVisible(not self.rule_ok)
        self.banner.setVisible(show)
        if public and a:
            self.banner_text.setText(tr("public", name=self.network_name or a.adapter))
        elif not self.rule_ok:
            self.banner_text.setText(tr("no_rule"))

    def _hide_banner(self) -> None:
        """You know better: a phone got through, or this network is fine for you."""
        if self.network_name and self.network_name not in self.settings.quiet_networks:
            self.settings.quiet_networks.append(self.network_name)
            self.settings.save()
        self.banner.hide()

    def _banner(self) -> QFrame:
        f = QFrame()
        f.setObjectName("banner")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(16, 14, 14, 14)
        lay.setSpacing(14)
        lay.addWidget(icon_tile("shield", 40, "coral", "shield"))
        self.banner_text = label("", "", wrap=True, rich=True)
        lay.addWidget(self.banner_text, 1)
        self.banner_public = button(tr("net_settings"))
        self.banner_public.clicked.connect(self._open_network_settings)
        lay.addWidget(self.banner_public)
        self.banner_rule = button(tr("allow_fw"), "", tr("allow_fw_tip"), "shield")
        self.banner_rule.clicked.connect(self.fix_firewall)
        lay.addWidget(self.banner_rule)
        recheck = button(tr("check_again"), "link")
        recheck.clicked.connect(self.check_network)
        lay.addWidget(recheck)
        close = button("", "x", tr("hide_banner"), "close", "text2")
        close.clicked.connect(self._hide_banner)
        lay.addWidget(close)
        f.hide()
        return f

    def _open_network_settings(self) -> None:
        a = self.current_address()
        page = "network-ethernet" if a and a.kind == "Ethernet" else "network-wifi"
        QDesktopServices.openUrl(QUrl(f"ms-settings:{page}"))

    def fix_firewall(self) -> None:
        port = self.hub.port

        def work():
            netutil.add_firewall_rule(listening_program(), port)
            a = self.current_address()
            cat, name = netutil.network_profile(a.if_index) if a else ("", "")
            self.net_checked.emit(cat, name, netutil.firewall_rule_exists())
        threading.Thread(target=work, daemon=True).start()
        self.settings.firewall_asked = True
        self.settings.save()

    # ---------------------------------------------------------------- pairing
    def ask_pair(self, req: PairRequest) -> None:
        toast = Toast(tr("wants", name=req.name), tr("wants_sub", ip=req.ip), tr("allow"), tr("deny"), PAIR_TTL,
                      "laptop" if req.kind == "desktop" else "phone")
        toast.answered.connect(lambda yes, rid=req.id: self.hub.resolve_pair(rid, yes))
        toast.destroyed.connect(lambda *_: self.toasts.remove(toast) if toast in self.toasts else None)
        self.toasts.append(toast)
        toast.show_near_tray(len(self.toasts) - 1)
        QApplication.alert(self)

    def refresh_devices(self) -> None:
        while self.devices_box.count():
            w = self.devices_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        devs = self.hub.devices.all()
        for d in devs:
            on = self.hub.online(d)
            r = Row(d.name, "", "laptop" if d.kind == "desktop" else "phone")
            if on:
                r.set_sub(tr("connected"), "ok", d.ip)
            else:
                r.set_sub(tr("seen", ago=ago(d.last_seen)), "sub", d.ip)
            r.set_on(on)
            r.add_button("", lambda _=False, i=d.id, n=d.name: self._remove_device(i, n), tr("remove_tip"), "close")
            self.devices_box.addWidget(r)
        self.no_devices.setVisible(not devs)
        self.paired_meta.setText(tr("paired", n=len(devs)) if devs else "")
        mine = {a.ip for a in getattr(self, "addresses", [])}
        reached = any(self.hub.online(d) and d.ip and d.ip not in mine and not d.ip.startswith("127.") for d in devs)
        if reached != self.phone_reached:
            self.phone_reached = reached
            self._update_banner()

    def _remove_device(self, dev_id: str, name: str) -> None:
        if Ask.confirm(self, tr("remove_title"), tr("remove_q", name=name), tr("remove_btn"), tr("cancel"), True,
                       "phone"):
            self.hub.revoke(dev_id)

    # ---------------------------------------------------------------- sharing
    def share(self, paths: list[Path]) -> None:
        self.hub.share([Path(p) for p in paths])
        self.refresh_shared()

    def dragEnterEvent(self, e) -> None:  # noqa: N802
        if e.mimeData().hasUrls():
            e.acceptProposedAction()

    def dropEvent(self, e) -> None:  # noqa: N802
        paths = [Path(u.toLocalFile()) for u in e.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.share(paths)

    def _add_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, tr("send_title"))
        if files:
            self.share([Path(f) for f in files])

    def _add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, tr("send_title"))
        if d:
            self.share([Path(d)])

    def refresh_shared(self) -> None:
        with self.hub.lock:
            items = sorted(self.hub.shared.values(), key=lambda s: s.added)
            self._last_shared_version = self.hub.version
        for sid in list(self.shared_rows):
            if sid not in {s.id for s in items}:
                self.shared_rows.pop(sid).deleteLater()
        for s in items:
            if s.id not in self.shared_rows:
                r = Row(s.rel, size_text(s.size), "file", 32)
                r.add_button("", lambda _=False, i=s.id: (self.hub.unshare(i), self.refresh_shared()),
                             tr("unshare_tip"), "close")
                self.shared_rows[s.id] = r
                self.shared_box.addWidget(r)
        self.shared_scroll.setFixedHeight(min(len(items), 3) * 60 + 4)
        self.shared_scroll.setVisible(bool(items))
        self.clear_shared.setVisible(bool(items))

    def _send_text(self) -> None:
        text = self.text.text()
        if text.strip():
            self.hub.send_text(text)
            self.text.clear()
            self._message_row(self.history.add_message("out", "", text))

    def _send_clipboard(self) -> None:
        cb = QGuiApplication.clipboard()
        md = cb.mimeData()
        if md and md.hasUrls() and all(u.isLocalFile() for u in md.urls()):
            self.share([Path(u.toLocalFile()) for u in md.urls()])  # files copied in Explorer
            return
        text = cb.text()
        if text.strip():
            self.hub.send_text(text)
            self._message_row(self.history.add_message("out", "", text))

    # ---------------------------------------------------------------- messages and files
    def _list_well(self, col: QVBoxLayout, empty: QWidget):
        well = QFrame()
        well.setObjectName("well")
        wl = QVBoxLayout(well)
        wl.setContentsMargins(6, 6, 6, 6)
        box = QVBoxLayout()
        box.setSpacing(2)
        box.addStretch(1)
        holder = QWidget()
        holder.setLayout(box)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setWidget(holder)
        scroll.hide()
        wl.addWidget(scroll)
        wl.addWidget(empty)
        col.addWidget(well, 1)
        return box, scroll, empty

    @staticmethod
    def _when(t: float) -> str:
        same_day = time.strftime("%Y%m%d", time.localtime(t)) == time.strftime("%Y%m%d")
        return time.strftime("%H:%M" if same_day else "%Y-%m-%d %H:%M", time.localtime(t))

    def _put(self, box: QVBoxLayout, scroll: QScrollArea, empty: QWidget, row: QWidget) -> None:
        box.insertWidget(0, row)  # newest on top
        empty.hide()
        scroll.show()

    def _message_row(self, m: dict) -> None:
        out = m.get("dir") == "out"
        who = tr("you_sent") if out else tr("dev_sent", dev=m.get("device", ""))
        when = self._when(m.get("t", time.time())) + (f" · {tr('copied')}" if m.get("copied") else "")
        text = m.get("text", "")
        r = MessageRow(who, when, text, out)
        r.add_button(lambda _=False, s=text: QGuiApplication.clipboard().setText(s), tr("copy"), "copy")
        one = " ".join(text.split())
        if one.startswith(("http://", "https://")) and " " not in one:
            r.add_button(lambda _=False, s=one: QDesktopServices.openUrl(QUrl(s)), tr("open_link"), "external")
        self._put(self.msg_list, self.msg_scroll, self.msg_empty, r)

    def _clear_messages(self) -> None:
        self.history.clear_messages()
        for i in reversed(range(self.msg_list.count())):
            w = self.msg_list.itemAt(i).widget()
            if w:
                w.deleteLater()
        self.msg_scroll.hide()
        self.msg_empty.show()

    def _file_sub(self, f: dict) -> tuple[str, str]:
        who = tr("from_dev", dev=f["device"]) if f["dir"] == "in" else tr("to_dev", dev=f["device"])
        when = self._when(f.get("t") or time.time())
        state = f.get("state")
        if state == "done":  # the arrow already says which way it went
            gone = f.get("path") and not Path(f["path"]).exists()
            text = f"{size_text(f['size'])} · {who} · {when}" + (f" · {tr('gone')}" if gone else "")
            return text, "sub" if gone else "ok"
        return f"{tr('stopped' if state == 'failed' else 'cancelled')} · {who} · {when}", "bad"

    def _file_buttons(self, r: Row, path: str) -> None:
        if path and Path(path).exists() and not getattr(r, "_buttons", False):
            r._buttons = True
            p = Path(path)
            r.add_button("", lambda _=False, q=p: os.startfile(str(q)), tr("open"), "external")  # noqa: S606
            r.add_button("", lambda _=False, q=p: reveal(q), tr("show_tip"), "folder")

    def _file_row(self, f: dict) -> Row:
        """A finished transfer from the history file."""
        r = Row(Path(f["path"]).name if f.get("path") and f["dir"] == "in" else f["name"], "",
                "down" if f["dir"] == "in" else "up")
        text, state = self._file_sub(f)
        r.set_sub(text, state)
        if state != "bad":
            self._file_buttons(r, f.get("path", ""))
        self.rows[f["id"]] = r
        self._put(self.file_list, self.file_scroll, self.file_empty, r)
        return r

    def on_transfer(self, t: Transfer) -> None:
        r = self.rows.get(t.id)
        if r is None:
            r = Row(t.name, "", "down" if t.direction == "in" else "up")
            r.bar.show()
            self.rows[t.id] = r
            self.speeds[t.id] = Speed()
            self._put(self.file_list, self.file_scroll, self.file_empty, r)
        if getattr(r, "_logged", False):
            return
        sp = self.speeds.setdefault(t.id, Speed()).add(t.done)
        r.bar.setValue(int((t.done / t.size if t.size else 1.0) * 1000))
        who = tr("from_dev", dev=t.device) if t.direction == "in" else tr("to_dev", dev=t.device)
        if t.state == "active":
            speed = f" · {size_text(sp)}/s" if sp > 0 else ""
            r.set_sub(f"{who} · {tr('progress', done=size_text(t.done), total=size_text(t.size))}{speed}")
            return
        r._logged = True  # finished: write it down once, it stays after a restart
        r.bar.hide()
        entry = {"id": t.id, "dir": t.direction, "device": t.device, "name": t.name, "path": t.path,
                 "size": t.size, "t": t.finished or time.time(), "state": t.state}
        self.history.put_file(entry)
        text, state = self._file_sub(entry)
        r.set_sub(text, state)
        secs = max(0.001, (t.finished or time.time()) - t.started)
        if t.state == "done" and t.size > 4 << 20:
            r.setToolTip(tr("average", speed=size_text(t.size / secs)))
        if t.state == "done":
            if t.direction == "in" and t.path and Path(t.path).name != t.name:
                r.set_title(Path(t.path).name)
            self._file_buttons(r, t.path)
            if t.direction == "in":
                self.received_batch.append((t.device, Path(t.path).name if t.path else t.name))
                self.notify_timer.start(1500)

    def _notify_received(self) -> None:
        batch, self.received_batch = self.received_batch, []
        app = QApplication.instance()
        if not batch or not self.settings.notify or not getattr(app, "tray", None) or self.isActiveWindow():
            return
        who = batch[0][0]
        title = tr("files_from", n=len(batch), dev=who) if len(batch) > 1 else tr("file_from", dev=who)
        app.tray.showMessage(title, ", ".join(n for _, n in batch[:4]) + ("…" if len(batch) > 4 else ""),
                             app_icon(), 5000)

    def on_text(self, device, text: str) -> None:
        copied = False
        if self.settings.copy_text:
            QGuiApplication.clipboard().setText(text)
            copied = True
        self._message_row(self.history.add_message("in", device.name, text, copied))
        app = QApplication.instance()
        if self.settings.notify and getattr(app, "tray", None) and not self.isActiveWindow():
            app.tray.showMessage(tr("text_from", dev=device.name), text[:200], app_icon(), 4000)

    def _clear_files(self) -> None:
        """Forgets the list; every file stays where it was saved."""
        self.history.clear_files()
        for tid, r in list(self.rows.items()):
            t = self.hub.transfers.get(tid)
            if t and t.state == "active":
                continue
            self.rows.pop(tid).deleteLater()
            self.speeds.pop(tid, None)
        if not self.rows:
            self.file_scroll.hide()
            self.file_empty.show()

    def _tick(self) -> None:
        if self.hub.version != self._last_shared_version:
            self.refresh_shared()
        active = [t for t in list(self.hub.transfers.values()) if t.state == "active"]
        for t in active:
            self.on_transfer(t)  # keeps the speed fresh when bytes stop coming
        self.total.setText(tr("moving", n=len(active)) if active else "")
        if int(time.time()) % 15 == 0:
            self.refresh_devices()

    # ---------------------------------------------------------------- settings
    def open_settings(self) -> None:
        if not self.dialog:
            self.dialog = SettingsDialog(self)
            self.dialog.finished.connect(lambda *_: setattr(self, "dialog", None))
        self.dialog.show()
        self.dialog.raise_()


def _single_instance(name: str, args: list[str]) -> QLocalServer | None:
    """Hands our arguments to a Skiffdrop that is already running; returns None if there is one."""
    sock = QLocalSocket()
    sock.connectToServer(name)
    if sock.waitForConnected(400):
        sock.write(("\n".join(args) or "--show").encode("utf-8"))
        sock.flush()
        sock.waitForBytesWritten(1000)
        sock.disconnectFromServer()
        return None
    QLocalServer.removeServer(name)
    server = QLocalServer()
    server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
    server.listen(name)
    return server


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    background = "--background" in argv
    files = [a for a in argv[1:] if not a.startswith("--") and Path(a).exists()]
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Niro54321.Skiffdrop")
    except (OSError, AttributeError):
        pass
    app = QApplication(argv)
    app.setApplicationName(APP)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())
    instance = _single_instance(f"Skiffdrop-{os.environ.get('USERNAME', 'user')}", files)
    if instance is None:
        return 0

    settings = Settings.load()
    lang = set_language(settings.lang)
    ui.load_fonts()
    if lang in RTL:
        app.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
    ui.apply_look(palette_for(settings.theme), lang)
    QGuiApplication.styleHints().colorSchemeChanged.connect(
        lambda *_: settings.theme == "system" and ui.apply_look(palette_for("system")))

    devices = Devices()
    bridge = Bridge()
    hub = Hub(settings, devices, bridge, thumbnail)
    hub.extra["/icon-180.png"] = (png_bytes(icon_pixmap(180)), "image/png")
    try:
        hub.start(os.environ.get("SKIFFDROP_HOST", "0.0.0.0"))  # the tests bind 127.0.0.1
    except OSError as e:
        Ask.inform(None, "Skiffdrop", f"{tr('server_error')}\n{e}", tr("ok"))
        return 1

    tray = QSystemTrayIcon(app_icon())
    app.tray = tray

    def quit_all():
        win.quitting = True
        tray.hide()
        hub.stop()
        app.quit()

    def restart():
        instance.close()  # free the single-instance name and the port before the new copy starts
        hub.stop()
        program, args = (sys.executable, []) if getattr(sys, "frozen", False) else \
            (sys.executable, ["-m", "skiffdrop"])
        QProcess.startDetached(program, args, str(Path.cwd()))
        win.quitting = True
        tray.hide()
        app.quit()

    win = MainWindow(hub, settings, bridge, restart)
    menu = QMenu()
    show = QAction(tr("tray_open"), menu)
    show.triggered.connect(win.bring_up)
    menu.addAction(show)
    folder = QAction(tr("tray_folder"), menu)
    folder.triggered.connect(lambda: reveal(settings.folder))
    menu.addAction(folder)
    menu.addSeparator()
    quit_action = QAction(tr("tray_quit"), menu)
    quit_action.triggered.connect(quit_all)
    menu.addAction(quit_action)
    tray.setContextMenu(menu)
    tray.activated.connect(lambda reason: win.bring_up()
                           if reason in (QSystemTrayIcon.ActivationReason.Trigger,
                                         QSystemTrayIcon.ActivationReason.DoubleClick) else None)
    tray.messageClicked.connect(win.bring_up)
    tray.show()
    win.refresh_qr()

    def on_message():
        conn = instance.nextPendingConnection()
        if not conn:
            return

        def read():
            data = bytes(conn.readAll()).decode("utf-8", "replace")
            paths = [Path(p) for p in data.splitlines() if p and not p.startswith("--") and Path(p).exists()]
            if paths:
                win.share(paths)
            win.bring_up()
        conn.readyRead.connect(read)
    instance.newConnection.connect(on_message)
    app.aboutToQuit.connect(lambda: hub.server and hub.stop())

    if files:
        win.share([Path(f) for f in files])
    if not background or files:
        win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
