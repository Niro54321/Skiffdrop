"""The web server the phone talks to: its page, pairing, uploads, downloads and text.

Plain HTTP/1.1 on the local network only:
- requests from addresses that are not private (RFC 1918, link-local, loopback) are refused,
  and the Host header must be an IP address, so no web site can rebind a name to this PC;
- everything except the page itself needs a paired device's cookie (HttpOnly, SameSite=Strict);
- requests that change something also need the X-Skiffdrop header, which other sites cannot send
  without a CORS preflight that this server never answers;
- a phone is only paired with the session key from the QR code (or the 6-digit code), the PIN
  when one is set, and a click on Allow on the PC.
Uploads go to disk in 1 MB blocks as they arrive and downloads are read the same way, so file
size never matters for memory.
"""

from __future__ import annotations

import hmac
import json
import mimetypes
import os
import secrets
import shutil
import socket
import threading
import time
import traceback
import urllib.parse
import zipfile
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable

from . import __version__
from .config import Device, Devices, Settings
from .names import place, safe_name
from .netutil import host_ok, is_lan

WEB = Path(__file__).with_name("web")
STATIC = {"/": ("index.html", "text/html; charset=utf-8"), "/index.html": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/style.css": ("style.css", "text/css; charset=utf-8"),
          "/icon.svg": ("icon.svg", "image/svg+xml"), "/i18n.js": ("i18n.js", "text/javascript; charset=utf-8"),
          "/fonts/Manrope-wght.ttf": ("fonts/Manrope-wght.ttf", "font/ttf"),
          "/fonts/InstrumentSerif-Regular.ttf": ("fonts/InstrumentSerif-Regular.ttf", "font/ttf"),
          "/fonts/JetBrainsMono-wght.ttf": ("fonts/JetBrainsMono-wght.ttf", "font/ttf")}
BLOCK = 1 << 20              # bytes per read/write
MAX_PUT = 64 << 20           # one upload request
MAX_JSON = 2 << 20           # API bodies (text messages included)
MAX_TEXT = 1 << 20
COOKIE = "skiffdrop"
LONGPOLL = 25.0
PAIR_TTL = 120.0
UPLOAD_IDLE = 6 * 3600.0     # an unfinished upload can be resumed for this long
ONLINE = 40.0                # a phone that polled this recently is "connected"
PAGE_CSP = ("default-src 'self'; img-src 'self' blob: data:; media-src 'self' blob:; style-src 'self'; "
            "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
FILE_CSP = "sandbox; default-src 'none'; img-src 'self' data:; media-src 'self'; style-src 'unsafe-inline'"
INLINE_TYPES = ("image/", "video/", "audio/", "text/plain", "application/pdf")


def now() -> float:
    return time.time()


@dataclass
class PairRequest:
    id: str
    ip: str
    name: str
    kind: str
    created: float
    status: str = "pending"      # pending / approved / denied
    token: str = ""
    device: Device | None = None


@dataclass
class Shared:
    id: str
    path: Path
    name: str
    size: int
    rel: str                     # path inside "Download all" zip
    added: float


@dataclass
class Transfer:
    """One file moving in either direction, for the PC's activity list."""
    id: str
    direction: str               # "in" = phone to PC, "out" = PC to phone
    name: str
    device: str
    size: int
    done: int = 0
    started: float = field(default_factory=now)
    finished: float = 0.0
    state: str = "active"        # active / done / failed / cancelled
    path: str = ""


@dataclass
class Upload:
    id: str
    device: Device
    name: str
    size: int
    part: Path
    key: str
    transfer: Transfer
    received: int = 0
    updated: float = field(default_factory=now)
    fh: object = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    final: Path | None = None


class Listener:
    """What the PC app hears about; every call comes from a server thread."""

    def pair_requested(self, req: PairRequest) -> None: ...
    def devices_changed(self) -> None: ...
    def transfer(self, t: Transfer) -> None: ...
    def text_received(self, device: Device, text: str) -> None: ...
    def code_changed(self) -> None: ...


class Hub:
    """Everything the server knows: session key, devices, shared files, uploads."""

    def __init__(self, settings: Settings, devices: Devices, listener: Listener | None = None,
                 thumbnailer: Callable[[Path], bytes | None] | None = None):
        self.settings = settings
        self.devices = devices
        self.listener = listener or Listener()
        self.thumbnailer = thumbnailer
        self.extra: dict[str, tuple[bytes, str]] = {}    # more static files (the PNG icons)
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.version = 1
        self.pc_name = socket.gethostname()
        self.key = self.code = ""
        self.renew_code()
        self.pending: dict[str, PairRequest] = {}
        self.fails: dict[str, list[float]] = {}         # ip -> [count, locked_until]
        self.total_fails = 0
        self.shared: dict[str, Shared] = {}
        self.texts: list[dict] = []
        self.uploads: dict[str, Upload] = {}
        self.transfers: dict[str, Transfer] = {}
        self.thumbs: dict[str, bytes] = {}
        self.server: Server | None = None
        self.port = 0
        self._stop = threading.Event()
        self._clean_parts()

    # ---------------------------------------------------------------- session code
    def renew_code(self) -> None:
        with self.lock:
            self.key = secrets.token_urlsafe(16)
            self.code = f"{secrets.randbelow(10**6):06d}"
            self.total_fails = 0
        self.listener.code_changed()

    def url(self, ip: str, with_key: bool = True) -> str:
        """The QR link. The fragment (never sent over the network) carries the key, and the
        6-digit code so the phone can show it filled in."""
        base = f"http://{ip}:{self.port}/"
        return base + f"#k={self.key}&c={self.code}" if with_key else base

    # ---------------------------------------------------------------- server life
    def start(self, host: str = "0.0.0.0", port: int | None = None) -> int:
        want = self.settings.port if port is None else port
        last: OSError | None = None
        for p in [want, *range(want + 1, want + 20), 0] if want else [0]:
            try:
                self.server = Server((host, p), self)
                break
            except OSError as e:
                last = e
        else:
            raise last or OSError("no free port")
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.5},
                         name="skiffdrop-http", daemon=True).start()
        threading.Thread(target=self._janitor, name="skiffdrop-janitor", daemon=True).start()
        return self.port

    def stop(self) -> None:
        self._stop.set()
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
        with self.lock:
            uploads = list(self.uploads.values())
            self.changed.notify_all()
        for up in uploads:  # outside the hub lock: a writer holds up.lock and then wants the hub lock
            self._drop_upload(up, "cancelled")

    def _janitor(self) -> None:
        while not self._stop.wait(20):
            t = now()
            with self.lock:
                stale = [up for up in self.uploads.values() if t - up.updated > UPLOAD_IDLE]
            for up in stale:
                self._drop_upload(up, "failed")
            with self.lock:
                for rid, req in list(self.pending.items()):
                    if t - req.created > PAIR_TTL:
                        self.pending.pop(rid, None)
                for tid, tr in list(self.transfers.items()):
                    if tr.state != "active" and t - tr.finished > 3600:
                        self.transfers.pop(tid, None)
                    elif tr.direction == "out" and tr.state == "active" and t - tr.started > 7 * 86400:
                        self.transfers.pop(tid, None)

    def _clean_parts(self) -> None:
        """Half-received files from an earlier run can't be resumed any more."""
        parts = self.settings.folder / ".skiffdrop-incoming"
        if parts.is_dir():
            for p in parts.glob("*.part"):
                try:
                    p.unlink()
                except OSError:
                    pass

    def bump(self) -> None:
        with self.lock:
            self.version += 1
            self.changed.notify_all()

    # ---------------------------------------------------------------- pairing
    def _failed(self, ip: str) -> None:
        with self.lock:
            entry = self.fails.setdefault(ip, [0, 0.0])
            entry[0] += 1
            if entry[0] >= 5:
                entry[1] = now() + 60 * 2 ** min(entry[0] - 5, 6)
            self.total_fails += 1
            renew = self.total_fails >= 30
        if renew:  # someone is guessing codes: the old ones stop working
            self.renew_code()

    def locked(self, ip: str) -> bool:
        with self.lock:
            entry = self.fails.get(ip)
            return bool(entry and entry[1] > now())

    def request_pair(self, ip: str, key: str, code: str, pin: str, name: str, kind: str) -> tuple[int, dict]:
        if self.locked(ip):
            return 429, {"error": "locked"}
        good = (key and hmac.compare_digest(key.encode(), self.key.encode())) or \
               (code and hmac.compare_digest(code.strip().encode(), self.code.encode()))
        if not good:
            self._failed(ip)
            return 403, {"error": "code"}
        if not self.settings.check_pin(pin):
            self._failed(ip)
            return 403, {"error": "pin"}
        with self.lock:
            self.fails.pop(ip, None)
            for rid, r in list(self.pending.items()):
                if r.ip == ip and r.status == "pending":
                    self.pending.pop(rid)
            req = PairRequest(secrets.token_urlsafe(18), ip, clean_label(name) or "Phone",
                              kind if kind in ("ios", "android", "desktop") else "other", now())
            self.pending[req.id] = req
        self.listener.pair_requested(req)
        return 200, {"req": req.id}

    def resolve_pair(self, req_id: str, allow: bool) -> None:
        with self.lock:
            req = self.pending.get(req_id)
            if not req or req.status != "pending":
                return
            if allow:
                req.device, req.token = self.devices.add(req.name, req.kind, req.ip, now())
                req.status = "approved"
            else:
                req.status = "denied"
            self.changed.notify_all()
        if allow:
            self.listener.devices_changed()

    def wait_pair(self, req_id: str, ip: str, timeout: float) -> PairRequest | None:
        end = now() + timeout
        with self.lock:
            while True:
                req = self.pending.get(req_id)
                if not req or req.ip != ip:
                    return None
                if req.status != "pending" or now() >= end or self._stop.is_set():
                    if req.status != "pending":
                        self.pending.pop(req_id, None)  # the token is handed out once
                    return req
                self.changed.wait(min(1.0, end - now()))

    def revoke(self, dev_id: str) -> None:
        self.devices.remove(dev_id)
        self.listener.devices_changed()
        self.bump()

    def seen(self, dev: Device, ip: str) -> None:
        t = now()
        fresh = t - dev.last_seen > ONLINE
        dev.last_seen, dev.ip = t, ip
        if fresh:
            self.devices.save()
            self.listener.devices_changed()

    def online(self, dev: Device) -> bool:
        return now() - dev.last_seen < ONLINE

    # ---------------------------------------------------------------- PC -> phone
    def share(self, paths: list[Path]) -> int:
        """Offers files (folders are walked) to every paired phone."""
        added = 0
        with self.lock:
            known = {s.path for s in self.shared.values()}
            for p in paths:
                p = Path(p)
                items = [(p, p.name)] if p.is_file() else \
                    [(f, f.relative_to(p.parent).as_posix()) for f in sorted(p.rglob("*")) if f.is_file()] \
                    if p.is_dir() else []
                for f, rel in items:
                    f = f.resolve()
                    if f in known:
                        continue
                    try:
                        size = f.stat().st_size
                    except OSError:
                        continue
                    sid = secrets.token_hex(6)
                    self.shared[sid] = Shared(sid, f, f.name, size, rel, now())
                    known.add(f)
                    added += 1
        if added:
            self.bump()
        return added

    def unshare(self, sid: str | None = None) -> None:
        with self.lock:
            if sid is None:
                self.shared.clear()
                self.thumbs.clear()
            else:
                self.shared.pop(sid, None)
                self.thumbs.pop(sid, None)
        self.bump()

    def send_text(self, text: str) -> None:
        text = text[:MAX_TEXT]
        if not text.strip():
            return
        with self.lock:
            self.texts.append({"id": secrets.token_hex(4), "text": text, "t": int(now() * 1000)})
            del self.texts[:-30]
        self.bump()

    def clear_texts(self) -> None:
        with self.lock:
            self.texts.clear()
        self.bump()

    def snapshot(self) -> dict:
        with self.lock:
            files = [{"id": s.id, "name": s.name, "size": s.size, "rel": s.rel,
                      "type": mimetypes.guess_type(s.name)[0] or "application/octet-stream"}
                     for s in sorted(self.shared.values(), key=lambda s: s.added)]
            return {"v": self.version, "pc": self.pc_name, "files": files, "texts": list(self.texts)}

    # ---------------------------------------------------------------- phone -> PC
    def start_upload(self, dev: Device, name: str, size: int, modified: int) -> tuple[int, dict]:
        name = safe_name(name)
        key = f"{dev.id}|{name}|{size}|{modified}"
        with self.lock:
            for up in self.uploads.values():
                if up.key == key and up.final is None:  # same file again: carry on where it stopped
                    return 200, {"id": up.id, "received": up.received}
            if sum(1 for u in self.uploads.values() if u.device.id == dev.id) >= 32:
                return 429, {"error": "busy"}
        folder = self.settings.folder
        parts = folder / ".skiffdrop-incoming"
        try:
            parts.mkdir(parents=True, exist_ok=True)
            hide(parts)
            if shutil.disk_usage(folder).free < size + (256 << 20):
                return 507, {"error": "disk_full"}
        except OSError:
            return 500, {"error": "folder"}
        uid = secrets.token_urlsafe(12)
        part = parts / f"{uid}.part"
        try:
            fh = open(part, "wb")
        except OSError:
            return 500, {"error": "folder"}
        tr = Transfer(uid, "in", name, dev.name, size)
        up = Upload(uid, dev, name, size, part, key, tr, fh=fh)
        with self.lock:
            self.uploads[uid] = up
            self.transfers[uid] = tr
        self.listener.transfer(tr)
        if size == 0:
            with up.lock:
                self._finish(up)
        return 200, {"id": uid, "received": 0, "saved": up.final.name if up.final else None}

    def _finish(self, up: Upload) -> None:
        """Called with up.lock held once every byte is on disk."""
        up.fh.close()
        up.fh = None
        up.final = place(up.part, self.settings.folder, up.name)
        tr = up.transfer
        tr.done, tr.state, tr.finished, tr.path = up.size, "done", now(), str(up.final)
        with self.lock:
            self.uploads.pop(up.id, None)
        self.listener.transfer(tr)

    def _drop_upload(self, up: Upload, state: str) -> None:
        with self.lock:
            self.uploads.pop(up.id, None)
        if up.lock.acquire(timeout=5):
            try:
                if up.fh:
                    up.fh.close()
                    up.fh = None
                if up.final is None:
                    try:
                        up.part.unlink()
                    except OSError:
                        pass
            finally:
                up.lock.release()
        tr = up.transfer
        if tr.state == "active":
            tr.state, tr.finished = state, now()
            self.listener.transfer(tr)

    def cancel_upload(self, uid: str) -> None:
        with self.lock:
            up = self.uploads.get(uid)
        if up:
            self._drop_upload(up, "cancelled")

    def text_from(self, dev: Device, text: str) -> None:
        self.listener.text_received(dev, text[:MAX_TEXT])


def clean_label(text: str) -> str:
    text = "".join(c for c in str(text or "") if c.isprintable())
    return " ".join(text.split())[:48]


def hide(path: Path) -> None:
    try:
        import ctypes
        ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x2)  # FILE_ATTRIBUTE_HIDDEN
    except (OSError, AttributeError):
        pass


def content_disposition(name: str, inline: bool) -> str:
    ascii_name = "".join(c if 32 <= ord(c) < 127 and c not in '"\\' else "_" for c in name) or "file"
    kind = "inline" if inline else "attachment"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{urllib.parse.quote(name, safe='')}"


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False      # on Windows that would let another program take the port
    request_queue_size = 64

    def __init__(self, address, hub: Hub):
        self.hub = hub
        super().__init__(address, Handler)

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()

    def handle_error(self, request, client_address) -> None:
        pass  # dropped connections are normal (phone screen locked, page closed)


class _Counter:
    """A write-only stream for zipfile that counts what went out."""

    def __init__(self, write, tick):
        self._write, self._tick, self.n = write, tick, 0

    def write(self, b) -> int:
        self._write(b)
        self.n += len(b)
        self._tick(self.n)
        return len(b)

    def flush(self) -> None:
        pass


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Skiffdrop"
    sys_version = ""
    timeout = 120
    server: Server

    def log_message(self, fmt, *args) -> None:
        pass

    def setup(self) -> None:
        super().setup()
        try:
            self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass

    def do_GET(self):
        self._dispatch("GET")

    def do_HEAD(self):
        self._dispatch("HEAD")

    def do_POST(self):
        self._dispatch("POST")

    def do_PUT(self):
        self._dispatch("PUT")

    def do_DELETE(self):
        self._dispatch("DELETE")

    def do_OPTIONS(self):
        self._dispatch("OPTIONS")

    # ---------------------------------------------------------------- plumbing
    @property
    def hub(self) -> Hub:
        return self.server.hub

    @property
    def ip(self) -> str:
        return self.client_address[0]

    def _headers(self, status: int, ctype: str, length: int | None, extra: dict | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        if length is not None:
            self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", (extra or {}).pop("Cache-Control", "no-store"))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        if self.close_connection:
            self.send_header("Connection", "close")
        self.end_headers()

    def _json(self, status: int, data: dict, extra: dict | None = None) -> None:
        body = json.dumps(data, ensure_ascii=False).encode()
        self._headers(status, "application/json; charset=utf-8", len(body), extra)
        if self.command != "HEAD":
            self.wfile.write(body)

    def _fail(self, status: int, error: str, close: bool = False) -> None:
        if close:
            self.close_connection = True
        self._json(status, {"error": error})

    def _length(self) -> int:
        if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
            return -1
        try:
            return max(0, int(self.headers.get("Content-Length", "0")))
        except ValueError:
            return -1

    def _body_json(self) -> dict | None:
        n = self._length()
        if n < 0 or n > MAX_JSON:
            self.close_connection = True
            return None
        raw = self.rfile.read(n) if n else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else None
        except (UnicodeDecodeError, ValueError):
            return None

    def _device(self) -> Device | None:
        token = ""
        for part in self.headers.get("Cookie", "").split(";"):
            k, _, v = part.strip().partition("=")
            if k == COOKIE:
                token = v.strip().strip('"')
        dev = self.hub.devices.by_token(token)
        if dev:
            self.hub.seen(dev, self.ip)
        return dev

    def _write_ok(self) -> bool:
        """State-changing calls must come from our own page."""
        if self.headers.get("X-Skiffdrop") != "1":
            return False
        origin = self.headers.get("Origin")
        if origin and origin != f"http://{self.headers.get('Host', '')}":
            return False
        return self.headers.get("Sec-Fetch-Site", "same-origin") in ("same-origin", "none")

    # ---------------------------------------------------------------- routing
    def _dispatch(self, method: str) -> None:
        try:
            if not is_lan(self.ip) or not host_ok(self.headers.get("Host", "")):
                return self._fail(403, "forbidden", close=True)
            url = urllib.parse.urlsplit(self.path)
            path = urllib.parse.unquote(url.path)
            query = urllib.parse.parse_qs(url.query)
            parts = [p for p in path.split("/") if p]

            if method in ("GET", "HEAD") and (path in STATIC or path in self.hub.extra):
                return self._static(path)
            if not parts or parts[0] != "api" or method == "OPTIONS":
                if method not in ("GET", "HEAD"):
                    self.close_connection = True
                return self._fail(404, "not_found")
            parts = parts[1:]
            if method != "GET" and method != "HEAD" and not self._write_ok():
                return self._fail(403, "origin", close=True)

            if parts == ["me"] and method == "GET":
                return self._me()
            if parts == ["pair"] and method == "POST":
                return self._pair()
            if len(parts) == 2 and parts[0] == "pair" and method == "GET":
                return self._pair_wait(parts[1])

            dev = self._device()
            if not dev:
                if method in ("PUT", "POST"):
                    self.close_connection = True
                return self._fail(401, "not_paired")
            if parts == ["events"] and method == "GET":
                return self._events(query)
            if parts == ["text"] and method == "POST":
                return self._text(dev)
            if parts == ["bye"] and method == "POST":
                self.hub.revoke(dev.id)
                return self._json(200, {"ok": True}, {"Set-Cookie": f"{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"})
            if parts == ["upload"] and method == "POST":
                return self._upload_start(dev)
            if len(parts) == 2 and parts[0] == "upload":
                if method == "PUT":
                    return self._upload_put(dev, parts[1], query)
                if method == "GET":
                    return self._upload_state(dev, parts[1])
                if method == "DELETE":
                    return self._upload_cancel(dev, parts[1])
            if len(parts) >= 2 and parts[0] == "file" and method in ("GET", "HEAD"):
                return self._file(dev, parts[1], query)
            if len(parts) >= 1 and parts[0] == "zip" and method in ("GET", "HEAD"):
                return self._zip(dev)
            if method in ("PUT", "POST"):
                self.close_connection = True
            return self._fail(404, "not_found")
        except (ConnectionError, TimeoutError, socket.timeout):
            self.close_connection = True
        except Exception:  # never take the server down; tell the phone
            traceback.print_exc()
            self.close_connection = True
            try:
                self._fail(500, "server")
            except OSError:
                pass

    # ---------------------------------------------------------------- page
    def _static(self, path: str) -> None:
        if path in self.hub.extra:
            body, ctype = self.hub.extra[path]
            extra = {}
        else:
            name, ctype = STATIC[path]
            body = (WEB / name).read_bytes()
            extra = {"Content-Security-Policy": PAGE_CSP} if name == "index.html" else {}
            if ctype.startswith("font/"):
                extra["Cache-Control"] = "max-age=604800"  # fonts never change within a version
        self._headers(200, ctype, len(body), extra)
        if self.command != "HEAD":
            self.wfile.write(body)

    def _me(self) -> None:
        dev = self._device()
        self._json(200, {"paired": bool(dev), "name": dev.name if dev else "", "pc": self.hub.pc_name,
                         "pin": self.hub.settings.has_pin, "version": __version__})

    def _pair(self) -> None:
        data = self._body_json()
        if data is None:
            return self._fail(400, "bad_request")
        status, out = self.hub.request_pair(self.ip, str(data.get("key", ""))[:64], str(data.get("code", ""))[:12],
                                            str(data.get("pin", ""))[:32], str(data.get("name", "")),
                                            str(data.get("kind", "")))
        self._json(status, out)

    def _pair_wait(self, req_id: str) -> None:
        req = self.hub.wait_pair(req_id, self.ip, 20.0)
        if not req:
            return self._json(200, {"status": "expired"})
        if req.status == "approved" and req.token:
            cookie = f"{COOKIE}={req.token}; Path=/; Max-Age=34560000; HttpOnly; SameSite=Strict"
            req.token = ""
            return self._json(200, {"status": "approved", "name": req.name}, {"Set-Cookie": cookie})
        self._json(200, {"status": req.status})

    def _events(self, query: dict) -> None:
        try:
            since = int(query.get("since", ["0"])[0])
        except ValueError:
            since = 0
        end = now() + LONGPOLL
        with self.hub.lock:
            while self.hub.version == since and now() < end and not self.hub._stop.is_set():
                self.hub.changed.wait(end - now())
        self._json(200, self.hub.snapshot())

    def _text(self, dev: Device) -> None:
        data = self._body_json()
        text = str((data or {}).get("text", ""))
        if not text.strip():
            return self._fail(400, "empty")
        self.hub.text_from(dev, text)
        self._json(200, {"ok": True})

    # ---------------------------------------------------------------- uploads
    def _upload_start(self, dev: Device) -> None:
        data = self._body_json()
        if data is None:
            return self._fail(400, "bad_request")
        try:
            size = int(data.get("size", -1))
            modified = int(data.get("modified", 0))
        except (TypeError, ValueError):
            return self._fail(400, "bad_request")
        if not 0 <= size < 1 << 44:
            return self._fail(400, "size")
        status, out = self.hub.start_upload(dev, str(data.get("name", "")), size, modified)
        self._json(status, out)

    def _upload_for(self, dev: Device, uid: str) -> Upload | None:
        with self.hub.lock:
            up = self.hub.uploads.get(uid)
        return up if up and up.device.id == dev.id else None

    def _upload_state(self, dev: Device, uid: str) -> None:
        up = self._upload_for(dev, uid)
        if not up:
            return self._fail(404, "gone")
        self._json(200, {"id": up.id, "received": up.received, "size": up.size})

    def _upload_cancel(self, dev: Device, uid: str) -> None:
        up = self._upload_for(dev, uid)
        if up:
            self.hub.cancel_upload(up.id)
        self._json(200, {"ok": True})

    def _upload_put(self, dev: Device, uid: str, query: dict) -> None:
        length = self._length()
        up = self._upload_for(dev, uid)
        if length < 0 or length > MAX_PUT:
            return self._fail(413 if length > MAX_PUT else 411, "length", close=True)
        if not up:
            return self._fail(404, "gone", close=True)
        try:
            offset = int(query.get("offset", ["-1"])[0])
        except ValueError:
            offset = -1
        if not up.lock.acquire(timeout=30):
            return self._fail(409, "busy", close=True)
        try:
            if up.fh is None or up.final is not None:
                return self._fail(404, "gone", close=True)
            if offset != up.received or offset + length > up.size:
                self.close_connection = True
                return self._json(409, {"error": "offset", "received": up.received})
            buf = bytearray(min(BLOCK, max(length, 1)))
            view = memoryview(buf)
            left = length
            tr = up.transfer
            last = 0.0
            while left:
                n = self.rfile.readinto(view[:min(left, BLOCK)])
                if not n:
                    raise ConnectionError("phone went away")
                up.fh.write(view[:n])
                left -= n
                up.received += n
                up.updated = now()
                if up.updated - last > 0.25:
                    last = up.updated
                    tr.done = up.received
                    self.hub.listener.transfer(tr)
            tr.done = up.received
            if up.received == up.size:
                self.hub._finish(up)
            else:
                self.hub.listener.transfer(tr)
            self._json(200, {"received": up.received, "saved": up.final.name if up.final else None})
        except (ConnectionError, TimeoutError, socket.timeout):
            self.close_connection = True
            try:
                up.fh and up.fh.flush()
            except (OSError, ValueError):
                pass
        finally:
            up.lock.release()

    # ---------------------------------------------------------------- downloads
    def _out_transfer(self, dev: Device, key: str, name: str, size: int, path: str = "") -> Transfer:
        """One entry per download; a resumed download (Range) continues the one still running."""
        base = f"out-{dev.id}-{key}"
        with self.hub.lock:
            tr = next((t for t in self.hub.transfers.values()
                       if t.id.startswith(base) and t.state == "active"), None)
            if tr is None:
                tr = Transfer(f"{base}-{int(now() * 1000)}", "out", name, dev.name, size, path=path)
                self.hub.transfers[tr.id] = tr
        return tr

    def _file(self, dev: Device, sid: str, query: dict) -> None:
        with self.hub.lock:
            item = self.hub.shared.get(sid)
        if not item:
            return self._fail(404, "gone")
        if query.get("thumb"):
            return self._thumb(item)
        try:
            f = open(item.path, "rb")
        except OSError:
            return self._fail(404, "gone")
        with f:
            size = os.fstat(f.fileno()).st_size
            ctype = mimetypes.guess_type(item.name)[0] or "application/octet-stream"
            inline = bool(query.get("inline")) and ctype.startswith(INLINE_TYPES)
            start, end = 0, size - 1
            status = 200
            rng = self.headers.get("Range", "")
            if rng.startswith("bytes=") and "," not in rng and size:
                a, _, b = rng[6:].strip().partition("-")
                try:
                    if a:
                        start, end = int(a), min(int(b), size - 1) if b else size - 1
                    elif b:
                        start, end = max(0, size - int(b)), size - 1
                    status = 206
                except ValueError:
                    start, end, status = 0, size - 1, 200
                if status == 206 and (start > end or start >= size):
                    return self._json(416, {"error": "range"}, {"Content-Range": f"bytes */{size}"})
            length = max(0, end - start + 1)
            extra = {"Accept-Ranges": "bytes", "Content-Disposition": content_disposition(item.name, inline),
                     "Content-Security-Policy": FILE_CSP}
            if status == 206:
                extra["Content-Range"] = f"bytes {start}-{end}/{size}"
            self._headers(status, ctype, length, extra)
            if self.command == "HEAD":
                return
            tr = self._out_transfer(dev, sid, item.name, size, str(item.path)) if query.get("dl") else None
            f.seek(start)
            self._send(f, length, tr, start)

    def _send(self, f, length: int, tr: Transfer | None, base: int) -> None:
        buf = bytearray(BLOCK)
        view = memoryview(buf)
        left, sent, last = length, 0, 0.0
        try:
            while left:
                n = f.readinto(view[:min(left, BLOCK)])
                if not n:
                    break
                self.wfile.write(view[:n])
                left -= n
                sent += n
                if tr and now() - last > 0.25:
                    last = now()
                    tr.done = base + sent
                    self.hub.listener.transfer(tr)
        except (ConnectionError, TimeoutError, socket.timeout):
            self.close_connection = True
            if tr:
                tr.done = base + sent
                tr.state, tr.finished = "failed", now()
                self.hub.listener.transfer(tr)
            return
        if left:  # the file shrank under us
            self.close_connection = True
        if tr:
            tr.done = base + sent
            if tr.done >= tr.size:
                tr.state, tr.finished = "done", now()
            self.hub.listener.transfer(tr)

    def _thumb(self, item: Shared) -> None:
        data = self.hub.thumbs.get(item.id)
        if data is None and self.hub.thumbnailer:
            data = self.hub.thumbnailer(item.path) or b""
            with self.hub.lock:
                if len(self.hub.thumbs) > 500:
                    self.hub.thumbs.clear()
                self.hub.thumbs[item.id] = data
        if not data:
            return self._fail(404, "no_thumb")
        self._headers(200, "image/jpeg", len(data), {"Content-Security-Policy": FILE_CSP})
        if self.command != "HEAD":
            self.wfile.write(data)

    def _zip(self, dev: Device) -> None:
        with self.hub.lock:
            items = sorted(self.hub.shared.values(), key=lambda s: s.added)
        if not items:
            return self._fail(404, "empty")
        name = time.strftime("Skiffdrop-%Y%m%d-%H%M.zip")
        self.close_connection = True  # the size isn't known up front: the body ends when the connection does
        self._headers(200, "application/zip", None, {"Content-Disposition": content_disposition(name, False)})
        if self.command == "HEAD":
            return
        total = sum(i.size for i in items)
        tr = self._out_transfer(dev, "zip", name, total)
        state = {"last": 0.0}

        def tick(n: int) -> None:
            if now() - state["last"] > 0.25:
                state["last"] = now()
                tr.done = min(n, total)
                self.hub.listener.transfer(tr)

        out = _Counter(self.wfile.write, tick)
        used: set[str] = set()
        buf = bytearray(BLOCK)
        view = memoryview(buf)
        try:
            with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
                for item in items:
                    try:
                        f = open(item.path, "rb")
                    except OSError:
                        continue
                    with f:
                        st = os.fstat(f.fileno())
                        arc = "/".join(safe_name(p) for p in item.rel.split("/")) or safe_name(item.name)
                        base, n = arc, 1
                        while arc.lower() in used:
                            stem, ext = os.path.splitext(base)
                            arc, n = f"{stem} ({n}){ext}", n + 1
                        used.add(arc.lower())
                        info = zipfile.ZipInfo(arc, time.localtime(max(st.st_mtime, 315532800))[:6])
                        info.file_size = st.st_size
                        info.compress_type = zipfile.ZIP_STORED
                        with zf.open(info, "w", force_zip64=True) as dst:
                            while True:
                                k = f.readinto(view)
                                if not k:
                                    break
                                dst.write(view[:k])
        except (ConnectionError, TimeoutError, socket.timeout):
            tr.state, tr.finished = "failed", now()
            self.hub.listener.transfer(tr)
            return
        tr.done, tr.state, tr.finished = total, "done", now()
        self.hub.listener.transfer(tr)
