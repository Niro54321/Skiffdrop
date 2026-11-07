"""Checks a packaged build before it ships; not part of the installer.

    skiffdrop-selftest.exe

Runs the real server on 127.0.0.1 with a throwaway config, plays a phone over
HTTP (page, pairing, upload, download, thumbnail, zip) and draws the QR code and
the icon, so a missing data file or Qt plugin shows up here and not on a user's PC.
"""

import io
import json
import os
import sys
import tempfile
import time
import urllib.request
import zipfile
from pathlib import Path


def main() -> int:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QApplication

    from skiffdrop import netutil
    from skiffdrop.app import thumbnail
    from skiffdrop.config import Devices, Settings
    from skiffdrop.server import Hub
    from skiffdrop.ui import QrCode, icon_pixmap, png_bytes

    main.qt = QApplication([])  # loads the image plugins; kept alive here
    tmp = Path(tempfile.mkdtemp(prefix="skiffdrop-selftest-"))
    s = Settings.load(tmp)
    s.save_dir = str(tmp / "inbox")
    hub = Hub(s, Devices(tmp), thumbnailer=thumbnail)
    hub.extra["/icon-180.png"] = (png_bytes(icon_pixmap(180)), "image/png")
    base = f"http://127.0.0.1:{hub.start('127.0.0.1', 0)}"
    cookie = ""

    def call(method, path, body=None, data=None, headers=None):
        h = {"X-Skiffdrop": "1", **(headers or {})}
        if cookie:
            h["Cookie"] = cookie
        if body is not None:
            data, h["Content-Type"] = json.dumps(body).encode(), "application/json"
        req = urllib.request.Request(base + path, data=data, method=method, headers=h)
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.headers, r.read()

    ok = True

    def check(name, cond):
        nonlocal ok
        print(("ok   " if cond else "FAIL ") + name)
        ok &= bool(cond)

    for page in ("/", "/app.js", "/style.css", "/icon.svg", "/icon-180.png"):
        check(f"page {page}", call("GET", page)[0] == 200)
    _, _, raw = call("POST", "/api/pair", {"key": hub.key, "name": "Selftest", "kind": "ios"})
    req = json.loads(raw)["req"]
    hub.resolve_pair(req, True)
    _, headers, raw = call("GET", f"/api/pair/{req}")
    cookie = headers["Set-Cookie"].split(";")[0]
    check("pairing", json.loads(raw)["status"] == "approved")
    data = os.urandom(3 << 20)
    _, _, raw = call("POST", "/api/upload", {"name": "صورة.jpg", "size": len(data)})
    uid = json.loads(raw)["id"]
    _, _, raw = call("PUT", f"/api/upload/{uid}?offset=0", data=data)
    check("upload", json.loads(raw)["saved"] == "صورة.jpg" and (tmp / "inbox" / "صورة.jpg").read_bytes() == data)
    img = QImage(640, 480, QImage.Format.Format_RGB32)
    img.fill(0xFF7A59)
    img.save(str(tmp / "photo.jpg"), "JPEG")
    hub.share([tmp / "inbox" / "صورة.jpg", tmp / "photo.jpg"])
    files = {f["name"]: f["id"] for f in json.loads(call("GET", "/api/events?since=0")[2])["files"]}
    check("download", call("GET", f"/api/file/{files['صورة.jpg']}/x?dl=1")[2] == data)
    status, headers, thumb = call("GET", f"/api/file/{files['photo.jpg']}/x?thumb=1")
    check("thumbnail (Qt JPEG plugin)", status == 200 and thumb[:2] == b"\xff\xd8")
    z = zipfile.ZipFile(io.BytesIO(call("GET", "/api/zip/all.zip")[2]))
    check("zip", sorted(z.namelist()) == ["photo.jpg", "صورة.jpg"] and z.testzip() is None)
    qr = QrCode()
    qr.set_text(hub.url("192.168.1.2"))
    check("qr code", len(qr.matrix) > 20)
    check("icon (Qt SVG)", not icon_pixmap(64).toImage().isNull() and icon_pixmap(64).toImage().pixelColor(32, 2).alpha() > 0)
    t = time.time()
    print("addresses:", [a.label() for a in netutil.addresses()], f"({time.time() - t:.2f} s)")
    hub.stop()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
