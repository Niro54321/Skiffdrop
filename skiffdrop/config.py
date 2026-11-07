"""Settings and paired devices, saved as JSON in %APPDATA%\\Skiffdrop."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from .netutil import downloads_dir

APP = "Skiffdrop"
DEFAULT_PORT = 7340


def config_dir() -> Path:
    d = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP
    d.mkdir(parents=True, exist_ok=True)
    return d


def _write(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


@dataclass
class Settings:
    port: int = DEFAULT_PORT
    save_dir: str = ""          # empty = Downloads\Skiffdrop
    ip: str = ""                # address in the QR code; empty = best guess
    copy_text: bool = True      # put text from the phone on the clipboard
    notify: bool = True
    pin_salt: str = ""
    pin_hash: str = ""
    firewall_asked: bool = False
    path: Path | None = field(default=None, repr=False, compare=False)

    @classmethod
    def load(cls, folder: Path | None = None) -> "Settings":
        path = (folder or config_dir()) / "settings.json"
        s = cls()
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for f in fields(cls):
                if f.name != "path" and f.name in data and isinstance(data[f.name], type(getattr(s, f.name))):
                    setattr(s, f.name, data[f.name])
        except (OSError, ValueError):
            pass
        s.path = path
        if not (1 <= s.port <= 65535):
            s.port = DEFAULT_PORT
        return s

    def save(self) -> None:
        if self.path:
            _write(self.path, {k: v for k, v in asdict(self).items() if k != "path"})

    @property
    def folder(self) -> Path:
        return Path(self.save_dir) if self.save_dir else downloads_dir() / APP

    # PIN: kept as a salted hash, checked in constant time
    @property
    def has_pin(self) -> bool:
        return bool(self.pin_hash)

    def set_pin(self, pin: str) -> None:
        pin = (pin or "").strip()
        if not pin:
            self.pin_salt = self.pin_hash = ""
            return
        self.pin_salt = secrets.token_hex(16)
        self.pin_hash = self._hash(pin)

    def check_pin(self, pin: str) -> bool:
        if not self.pin_hash:
            return True
        return hmac.compare_digest(self._hash((pin or "").strip()), self.pin_hash)

    def _hash(self, pin: str) -> str:
        return hashlib.pbkdf2_hmac("sha256", pin.encode(), bytes.fromhex(self.pin_salt), 120_000).hex()


@dataclass
class Device:
    id: str
    name: str
    kind: str            # ios / android / desktop / other
    token_hash: str      # sha256 of the cookie the phone holds; the token itself is never stored
    added: float
    last_seen: float = 0.0
    ip: str = ""


class Devices:
    """Phones that were allowed once and may come back without asking again."""

    def __init__(self, folder: Path | None = None):
        self.path = (folder or config_dir()) / "devices.json"
        self.lock = threading.RLock()
        self.items: dict[str, Device] = {}
        try:
            for d in json.loads(self.path.read_text(encoding="utf-8")):
                dev = Device(**{f.name: d[f.name] for f in fields(Device) if f.name in d})
                self.items[dev.id] = dev
        except (OSError, ValueError, TypeError, KeyError):
            pass

    def save(self) -> None:
        with self.lock:
            _write(self.path, [asdict(d) for d in self.items.values()])

    def add(self, name: str, kind: str, ip: str, now: float) -> tuple[Device, str]:
        token = secrets.token_urlsafe(32)
        dev = Device(secrets.token_hex(6), name, kind, hashlib.sha256(token.encode()).hexdigest(), now, now, ip)
        with self.lock:
            self.items[dev.id] = dev
            self.save()
        return dev, token

    def by_token(self, token: str) -> Device | None:
        if not token:
            return None
        h = hashlib.sha256(token.encode()).hexdigest()
        with self.lock:
            for d in self.items.values():
                if hmac.compare_digest(d.token_hash, h):
                    return d
        return None

    def remove(self, dev_id: str) -> None:
        with self.lock:
            if self.items.pop(dev_id, None):
                self.save()

    def all(self) -> list[Device]:
        with self.lock:
            return sorted(self.items.values(), key=lambda d: -d.last_seen)
