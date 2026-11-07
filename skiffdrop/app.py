"""The PC side: a glass window with the QR code, a tray icon, and the server behind them."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices, QGuiApplication, QImageReader
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QMenu, QMessageBox, QScrollArea, QSizePolicy, QSpinBox, QSystemTrayIcon, QVBoxLayout,
                               QWidget)

from . import __version__, netutil
from .config import APP, Devices, Settings
from .server import PAIR_TTL, Hub, Listener, PairRequest, Transfer
from .ui import (DropZone, QrCode, Row, Speed, Toast, ago, app_icon, button, card, glass, grid_form,
                 icon_pixmap, label, png_bytes, prepare_glass, size_text)

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


class SettingsDialog(QDialog):
    def __init__(self, parent: "MainWindow"):
        super().__init__(parent)
        self.main = parent
        s = parent.settings
        self.setWindowTitle("Skiffdrop settings")
        prepare_glass(self)
        self.setMinimumWidth(520)
        col = QVBoxLayout(self)
        col.setContentsMargins(18, 16, 18, 18)
        col.setSpacing(12)

        frame, c = card("Where files from your phone go")
        row = QHBoxLayout()
        self.folder = label(str(s.folder), "url")
        self.folder.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        row.addWidget(self.folder, 1)
        b = button("Change…")
        b.clicked.connect(self._folder)
        row.addWidget(b)
        c.addLayout(row)
        col.addWidget(frame)

        frame, c = card("Security")
        c.addWidget(label("Every new phone needs your OK on this PC. A PIN adds a second check: "
                          "the phone has to type it before you're even asked.", "muted", wrap=True))
        row = QHBoxLayout()
        self.pin = QLineEdit()
        self.pin.setPlaceholderText("PIN is on" if s.has_pin else "No PIN (4 to 12 digits)")
        self.pin.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin.setMaxLength(12)
        row.addWidget(self.pin, 1)
        b = button("Set PIN")
        b.clicked.connect(self._set_pin)
        row.addWidget(b)
        self.pin_off = button("Turn off")
        self.pin_off.setEnabled(s.has_pin)
        self.pin_off.clicked.connect(self._pin_off)
        row.addWidget(self.pin_off)
        c.addLayout(row)
        col.addWidget(frame)

        frame, c = card("Behaviour")
        self.copy = QCheckBox("Put text from the phone on the clipboard")
        self.copy.setChecked(s.copy_text)
        self.copy.toggled.connect(lambda v: self._set("copy_text", v))
        c.addWidget(self.copy)
        self.notify = QCheckBox("Show a notification when files arrive")
        self.notify.setChecked(s.notify)
        self.notify.toggled.connect(lambda v: self._set("notify", v))
        c.addWidget(self.notify)
        self.startup = QCheckBox("Start with Windows (waits in the tray)")
        self.startup.setChecked(startup_enabled())
        self.startup.setEnabled(startup_command() is not None)
        self.startup.toggled.connect(set_startup)
        c.addWidget(self.startup)
        g = grid_form()
        g.addWidget(label("Port"), 0, 0)
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(s.port)
        self.port.valueChanged.connect(lambda v: self._set("port", v))
        g.addWidget(self.port, 0, 1)
        g.addWidget(label("used after a restart of Skiffdrop", "sub"), 0, 2)
        g.setColumnStretch(2, 1)
        c.addLayout(g)
        col.addWidget(frame)

        frame, c = card("Windows Firewall")
        c.addWidget(label("Phones reach Skiffdrop through Windows Firewall. The rule allows it on private "
                          "networks only (your home Wi-Fi), never on public ones.", "muted", wrap=True))
        row = QHBoxLayout()
        self.fw = label("", "sub")
        row.addWidget(self.fw, 1)
        b = button("Allow on private networks…")
        b.clicked.connect(parent.fix_firewall)
        row.addWidget(b)
        c.addLayout(row)
        col.addWidget(frame)
        foot = QHBoxLayout()
        foot.addWidget(label(f"Skiffdrop {__version__} · MIT · github.com/Niro54321/Skiffdrop", "sub"), 1)
        close = button("Done", "primary")
        close.clicked.connect(self.accept)
        foot.addWidget(close)
        col.addLayout(foot)
        self.refresh()

    def refresh(self) -> None:
        self.fw.setText("Rule is in place." if self.main.rule_ok else "No Skiffdrop rule yet.")

    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        glass(self)

    def _set(self, name: str, value) -> None:
        setattr(self.main.settings, name, value)
        self.main.settings.save()

    def _folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Save files from your phone in", str(self.main.settings.folder))
        if d:
            self._set("save_dir", d)
            self.folder.setText(d)

    def _set_pin(self) -> None:
        pin = self.pin.text().strip()
        if not (pin.isdigit() and 4 <= len(pin) <= 12):
            QMessageBox.information(self, "PIN", "Use 4 to 12 digits.")
            return
        self.main.settings.set_pin(pin)
        self.main.settings.save()
        self.pin.clear()
        self.pin.setPlaceholderText("PIN is on")
        self.pin_off.setEnabled(True)
        self.main.refresh_qr()

    def _pin_off(self) -> None:
        self.main.settings.set_pin("")
        self.main.settings.save()
        self.pin.setPlaceholderText("No PIN (4 to 12 digits)")
        self.pin_off.setEnabled(False)
        self.main.refresh_qr()


class MainWindow(QWidget):
    net_checked = Signal(str, bool)   # network category, firewall rule exists

    def __init__(self, hub: Hub, settings: Settings, bridge: Bridge):
        super().__init__()
        self.hub, self.settings, self.bridge = hub, settings, bridge
        self.rule_ok = True
        self.category = ""
        self.rows: dict[str, Row] = {}
        self.speeds: dict[str, Speed] = {}
        self.shared_rows: dict[str, Row] = {}
        self.toasts: list[Toast] = []
        self.received_batch: list[tuple[str, str]] = []
        self.quitting = False
        self.dialog: SettingsDialog | None = None

        self.setWindowTitle("Skiffdrop")
        self.setWindowIcon(app_icon())
        prepare_glass(self)
        self.setAcceptDrops(True)
        self.resize(1040, 720)
        self.setMinimumSize(880, 600)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(18, 16, 18, 18)
        outer.setSpacing(14)

        # ---------------------------------------------------------- left: QR + phones
        left = QVBoxLayout()
        left.setSpacing(12)
        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(icon_pixmap(40))
        head.addWidget(logo)
        names = QVBoxLayout()
        names.setSpacing(0)
        names.addWidget(label("Skiffdrop", "title"))
        names.addWidget(label("Phone ⇄ PC over your Wi-Fi", "muted"))
        head.addLayout(names, 1)
        gear = button("⚙", "flat", "Settings")
        gear.setStyleSheet("font-size: 18px;")
        gear.clicked.connect(self.open_settings)
        head.addWidget(gear)
        left.addLayout(head)

        frame, c = card("Scan with your phone's camera")
        self.qr = QrCode(256)
        c.addWidget(self.qr, 0, Qt.AlignmentFlag.AlignHCenter)
        self.url = label("", "url")
        self.url.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.url.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        c.addWidget(self.url)
        coderow = QHBoxLayout()
        coderow.addStretch(1)
        coderow.addWidget(label("or type", "muted"))
        self.code = label("", "code")
        self.code.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        coderow.addWidget(self.code)
        coderow.addStretch(1)
        c.addLayout(coderow)
        row = QHBoxLayout()
        self.addr = QComboBox()
        self.addr.setToolTip("The network address in the QR code. Pick the adapter your phone's Wi-Fi is on.")
        self.addr.currentIndexChanged.connect(self._address_picked)
        row.addWidget(self.addr, 1)
        renew = button("New code", "", "Old QR codes and codes stop working. Phones you allowed stay allowed.")
        renew.clicked.connect(self.hub.renew_code)
        row.addWidget(renew)
        c.addLayout(row)
        self.pin_note = label("", "sub")
        self.pin_note.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        c.addWidget(self.pin_note)
        frame.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)  # the QR never gets squeezed
        left.addWidget(frame)

        frame, c = card("Phones")
        self.devices_box = QVBoxLayout()
        self.devices_box.setSpacing(0)
        holder = QWidget()
        outer_box = QVBoxLayout(holder)
        outer_box.setContentsMargins(0, 0, 4, 0)
        outer_box.addLayout(self.devices_box)
        outer_box.addStretch(1)
        devscroll = QScrollArea()
        devscroll.setWidgetResizable(True)
        devscroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        devscroll.setWidget(holder)
        c.addWidget(devscroll, 1)
        self.no_devices = label("No phones yet. Scan the code above with the camera app.", "muted", wrap=True)
        c.addWidget(self.no_devices)
        left.addWidget(frame, 1)
        lw = QWidget()
        lw.setLayout(left)
        lw.setFixedWidth(330)
        outer.addWidget(lw)

        # ---------------------------------------------------------- right: send, activity
        right = QVBoxLayout()
        right.setSpacing(12)
        self.banner = self._banner()
        right.addWidget(self.banner)

        frame, c = card("Send to phone")
        self.drop = DropZone()
        dl = QVBoxLayout(self.drop)
        dl.setContentsMargins(14, 12, 14, 12)
        dl.addWidget(label("Drop files or folders here", ""), 0, Qt.AlignmentFlag.AlignHCenter)
        dl.addWidget(label("They show up on every connected phone until you remove them.", "sub"), 0,
                     Qt.AlignmentFlag.AlignHCenter)
        btns = QHBoxLayout()
        btns.addStretch(1)
        b = button("Add files…")
        b.clicked.connect(self._add_files)
        btns.addWidget(b)
        b = button("Add folder…")
        b.clicked.connect(self._add_folder)
        btns.addWidget(b)
        self.clear_shared = button("Remove all")
        self.clear_shared.clicked.connect(lambda: self.hub.unshare(None))
        btns.addWidget(self.clear_shared)
        btns.addStretch(1)
        dl.addLayout(btns)
        self.drop.dropped.connect(self.share)
        c.addWidget(self.drop)
        self.shared_box = QVBoxLayout()
        self.shared_box.setSpacing(0)
        sw = QWidget()
        sw.setLayout(self.shared_box)
        self.shared_scroll = QScrollArea()
        self.shared_scroll.setWidgetResizable(True)
        self.shared_scroll.setWidget(sw)
        self.shared_scroll.setMaximumHeight(150)
        self.shared_scroll.hide()
        c.addWidget(self.shared_scroll)
        trow = QHBoxLayout()
        self.text = QLineEdit()
        self.text.setPlaceholderText("Text or link for your phone…")
        self.text.returnPressed.connect(self._send_text)
        trow.addWidget(self.text, 1)
        b = button("Paste clipboard", "", "Sends what you copied on this PC")
        b.clicked.connect(self._send_clipboard)
        trow.addWidget(b)
        b = button("Send", "primary")
        b.clicked.connect(self._send_text)
        trow.addWidget(b)
        c.addLayout(trow)
        right.addWidget(frame)

        frame, c = card("")
        top = QHBoxLayout()
        h = label("ACTIVITY", "h")
        top.addWidget(h, 1)
        self.total = label("", "sub")
        top.addWidget(self.total)
        b = button("Open folder", "flat")
        b.clicked.connect(lambda: reveal(self.settings.folder))
        top.addWidget(b)
        b = button("Clear", "flat")
        b.clicked.connect(self._clear_activity)
        top.addWidget(b)
        c.addLayout(top)
        self.activity = QVBoxLayout()
        self.activity.setSpacing(0)
        self.activity.addStretch(1)
        aw = QWidget()
        aw.setLayout(self.activity)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(aw)
        self.no_activity = label("Files and text from your phones show up here. They are saved in "
                                 f"{self.settings.folder}.", "muted", wrap=True)
        c.addWidget(self.no_activity)
        c.addWidget(scroll, 1)
        right.addWidget(frame, 1)
        outer.addLayout(right, 1)

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
        self.load_addresses()
        self.refresh_devices()
        self.refresh_shared()

    # ---------------------------------------------------------------- glass + tray behaviour
    def showEvent(self, e) -> None:  # noqa: N802
        super().showEvent(e)
        glass(self)

    def closeEvent(self, e) -> None:  # noqa: N802
        if self.quitting:
            return super().closeEvent(e)
        e.ignore()
        self.hide()
        app = QApplication.instance()
        if not getattr(app, "_told_tray", False) and getattr(app, "tray", None):
            app._told_tray = True
            app.tray.showMessage("Skiffdrop is still on", "Phones can keep sending. Quit from the tray icon.",
                                 app_icon(), 4000)

    def bring_up(self) -> None:
        self.show()
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowMinimized)
        self.raise_()
        self.activateWindow()

    # ---------------------------------------------------------------- network + QR
    def load_addresses(self) -> None:
        self.addresses = netutil.addresses()
        self.addr.blockSignals(True)
        self.addr.clear()
        for a in self.addresses:
            self.addr.addItem(a.label(), a.ip)
        if not self.addresses:
            self.addr.addItem("No network: connect to Wi-Fi", "")
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
            self.url.setText("Connect this PC to Wi-Fi or Ethernet")
            self.code.setText("")
            return
        self.qr.set_text(self.hub.url(a.ip))
        self.url.setText(self.hub.url(a.ip, with_key=False).rstrip("/"))
        self.code.setText(f"{self.hub.code[:3]} {self.hub.code[3:]}")
        self.pin_note.setText("PIN required on the phone" if self.settings.has_pin else "")
        self.pin_note.setVisible(self.settings.has_pin)
        app = QApplication.instance()
        if getattr(app, "tray", None):
            app.tray.setToolTip(f"Skiffdrop · {a.ip}:{self.hub.port}")

    def check_network(self) -> None:
        a = self.current_address()

        def work():
            cat = netutil.network_category(a.if_index) if a else ""
            self.net_checked.emit(cat, netutil.firewall_rule_exists())
        threading.Thread(target=work, daemon=True).start()

    def _net_result(self, category: str, rule: bool) -> None:
        self.category, self.rule_ok = category, rule
        a = self.current_address()
        public = category == "Public"
        self.banner_public.setVisible(public)
        self.banner_rule.setVisible(not rule)
        self.banner.setVisible(public or not rule)
        if public and a:
            self.banner_text.setText(f"Windows treats the network on “{a.adapter}” as Public, so it blocks your "
                                     "phone. If this is your home Wi-Fi, make it a Private network.")
        elif not rule:
            self.banner_text.setText("Allow Skiffdrop through Windows Firewall so phones can reach it. "
                                     "It's allowed on private networks only.")
        if self.dialog:
            self.dialog.refresh()

    def _banner(self):
        from PySide6.QtWidgets import QFrame
        f = QFrame()
        f.setObjectName("banner")
        lay = QHBoxLayout(f)
        lay.setContentsMargins(14, 10, 10, 10)
        self.banner_text = label("", "", wrap=True)
        lay.addWidget(self.banner_text, 1)
        self.banner_public = button("Network settings…")
        self.banner_public.clicked.connect(self._open_network_settings)
        lay.addWidget(self.banner_public)
        self.banner_rule = button("Allow…", "primary", "One admin prompt. Adds a rule for private networks only.")
        self.banner_rule.clicked.connect(self.fix_firewall)
        lay.addWidget(self.banner_rule)
        recheck = button("Check again", "flat")
        recheck.clicked.connect(self.check_network)
        lay.addWidget(recheck)
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
            self.net_checked.emit(netutil.network_category(a.if_index) if a else "", netutil.firewall_rule_exists())
        threading.Thread(target=work, daemon=True).start()
        self.settings.firewall_asked = True
        self.settings.save()

    # ---------------------------------------------------------------- pairing
    def ask_pair(self, req: PairRequest) -> None:
        kind = {"ios": "iPhone/iPad", "android": "Android", "desktop": "computer"}.get(req.kind, "device")
        toast = Toast(f"{req.name} wants to connect",
                      f"A {kind} at {req.ip} scanned your Skiffdrop code. Allow it to send and receive files?",
                      "Allow", "Deny", PAIR_TTL)
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
            r = Row(d.name, ("● connected" if on else ago(d.last_seen)) + (f" · {d.ip}" if d.ip else ""))
            r.sub.setObjectName("ok" if on else "sub")
            r.setToolTip(f"Allowed {time.strftime('%d %b %Y %H:%M', time.localtime(d.added))}")
            r.add_button("✕", lambda _=False, i=d.id, n=d.name: self._remove_device(i, n),
                         "Remove: this phone will need your OK again")
            self.devices_box.addWidget(r)
        self.no_devices.setVisible(not devs)

    def _remove_device(self, dev_id: str, name: str) -> None:
        if QMessageBox.question(self, "Remove phone", f"Remove {name}? It will have to scan the code and ask "
                                "again.") == QMessageBox.StandardButton.Yes:
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
        files, _ = QFileDialog.getOpenFileNames(self, "Send to phone")
        if files:
            self.share([Path(f) for f in files])

    def _add_folder(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Send a folder to phone")
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
                r = Row(s.rel, size_text(s.size), "↑")
                r.add_button("✕", lambda _=False, i=s.id: (self.hub.unshare(i), self.refresh_shared()),
                             "Stop offering this file")
                self.shared_rows[s.id] = r
                self.shared_box.addWidget(r)
        self.shared_scroll.setVisible(bool(items))
        self.clear_shared.setVisible(bool(items))

    def _send_text(self) -> None:
        text = self.text.text()
        if text.strip():
            self.hub.send_text(text)
            self.text.clear()
            self._activity_text("You sent", text)

    def _send_clipboard(self) -> None:
        cb = QGuiApplication.clipboard()
        md = cb.mimeData()
        if md and md.hasUrls() and all(u.isLocalFile() for u in md.urls()):
            self.share([Path(u.toLocalFile()) for u in md.urls()])  # files copied in Explorer
            return
        text = cb.text()
        if text.strip():
            self.hub.send_text(text)
            self._activity_text("You sent", text)

    # ---------------------------------------------------------------- activity
    def _insert(self, row: Row) -> None:
        self.activity.insertWidget(0, row)
        self.no_activity.hide()

    def on_transfer(self, t: Transfer) -> None:
        r = self.rows.get(t.id)
        if r is None:
            glyph = "↓" if t.direction == "in" else "↑"
            r = Row(t.name, "", glyph)
            r.bar.show()
            self.rows[t.id] = r
            self.speeds[t.id] = Speed()
            self._insert(r)
        sp = self.speeds[t.id].add(t.done)
        frac = t.done / t.size if t.size else 1.0
        r.bar.setValue(int(frac * 1000))
        who = f"from {t.device}" if t.direction == "in" else f"to {t.device}"
        if t.state == "active":
            r.sub.setObjectName("sub")
            speed = f" · {size_text(sp)}/s" if sp > 0 else ""
            r.sub.setText(f"{who} · {size_text(t.done)} of {size_text(t.size)}{speed}")
        else:
            r.bar.hide()
            secs = max(0.001, (t.finished or time.time()) - t.started)
            avg = f" · {size_text(t.size / secs)}/s average" if t.state == "done" and t.size > 4 << 20 else ""
            word = {"done": "received" if t.direction == "in" else "sent", "failed": "stopped",
                    "cancelled": "cancelled"}[t.state]
            r.sub.setObjectName("ok" if t.state == "done" else "bad")
            r.sub.setText(f"{who} · {size_text(t.size)} {word}{avg}")
            if t.state == "done" and t.direction == "in" and t.path and not getattr(r, "_buttons", False):
                r._buttons = True
                path = Path(t.path)
                if path.name != t.name:
                    r.full_title = path.name
                    r.title.setText(path.name)
                r.add_button("Open", lambda _=False, p=path: os.startfile(str(p)))  # noqa: S606
                r.add_button("Show", lambda _=False, p=path: reveal(p), "Show in folder")
                self.received_batch.append((t.device, path.name))
                self.notify_timer.start(1500)
        r.sub.style().unpolish(r.sub)
        r.sub.style().polish(r.sub)

    def _notify_received(self) -> None:
        batch, self.received_batch = self.received_batch, []
        app = QApplication.instance()
        if not batch or not self.settings.notify or not getattr(app, "tray", None) or self.isActiveWindow():
            return
        who = batch[0][0]
        title = f"{len(batch)} files from {who}" if len(batch) > 1 else f"File from {who}"
        app.tray.showMessage(title, ", ".join(n for _, n in batch[:4]) + ("…" if len(batch) > 4 else ""),
                             app_icon(), 5000)

    def on_text(self, device, text: str) -> None:
        copied = False
        if self.settings.copy_text:
            QGuiApplication.clipboard().setText(text)
            copied = True
        self._activity_text(f"{device.name} sent", text, copied)
        app = QApplication.instance()
        if self.settings.notify and getattr(app, "tray", None) and not self.isActiveWindow():
            app.tray.showMessage(f"Text from {device.name}" + (" (copied)" if copied else ""), text[:200],
                                 app_icon(), 4000)

    def _activity_text(self, who: str, text: str, copied: bool = False) -> None:
        one = " ".join(text.split())
        r = Row(one[:300], f"{who} · {time.strftime('%H:%M')}" + (" · copied to clipboard" if copied else ""), "¶")
        r.add_button("Copy", lambda _=False, s=text: QGuiApplication.clipboard().setText(s))
        if one.startswith(("http://", "https://")) and " " not in one:
            r.add_button("Open", lambda _=False, s=one: QDesktopServices.openUrl(QUrl(s)))
        self._insert(r)

    def _clear_activity(self) -> None:
        for tid, r in list(self.rows.items()):
            t = self.hub.transfers.get(tid)
            if t and t.state == "active":
                continue
            self.rows.pop(tid).deleteLater()
            self.speeds.pop(tid, None)
        for i in reversed(range(self.activity.count())):
            w = self.activity.itemAt(i).widget()
            if w and w not in self.rows.values():
                w.deleteLater()
        self.no_activity.setVisible(not self.rows)

    def _tick(self) -> None:
        if self.hub.version != self._last_shared_version:
            self.refresh_shared()
        active = [t for t in list(self.hub.transfers.values()) if t.state == "active"]
        for t in active:
            self.on_transfer(t)  # keeps the speed fresh when bytes stop coming
        self.total.setText(f"{len(active)} moving" if active else "")
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
    devices = Devices()
    bridge = Bridge()
    hub = Hub(settings, devices, bridge, thumbnail)
    hub.extra["/icon-180.png"] = (png_bytes(icon_pixmap(180)), "image/png")
    try:
        hub.start(os.environ.get("SKIFFDROP_HOST", "0.0.0.0"))  # the tests bind 127.0.0.1
    except OSError as e:
        QMessageBox.critical(None, "Skiffdrop", f"Couldn't start the local server:\n{e}")
        return 1

    win = MainWindow(hub, settings, bridge)
    tray = QSystemTrayIcon(app_icon())
    app.tray = tray
    menu = QMenu()
    show = QAction("Open Skiffdrop", menu)
    show.triggered.connect(win.bring_up)
    menu.addAction(show)
    folder = QAction("Open received files", menu)
    folder.triggered.connect(lambda: reveal(settings.folder))
    menu.addAction(folder)
    menu.addSeparator()
    quit_action = QAction("Quit", menu)
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

    def quit_all():
        win.quitting = True
        tray.hide()
        hub.stop()
        app.quit()
    quit_action.triggered.connect(quit_all)
    app.aboutToQuit.connect(lambda: hub.server and hub.stop())

    if files:
        win.share([Path(f) for f in files])
    if not background or files:
        win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
