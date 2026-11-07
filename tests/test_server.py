"""The phone protocol end to end against a real server on 127.0.0.1."""

from __future__ import annotations

import hashlib
import io
import os
import threading
import time
import zipfile

import pytest
import requests

from skiffdrop.config import Devices, Settings
from skiffdrop.server import Hub, Listener

H = {"X-Skiffdrop": "1"}


class Recorder(Listener):
    def __init__(self):
        self.pairs, self.texts, self.transfers = [], [], []

    def pair_requested(self, req):
        self.pairs.append(req)

    def text_received(self, device, text):
        self.texts.append((device.name, text))

    def transfer(self, t):
        self.transfers.append((t.id, t.state, t.done))


@pytest.fixture
def env(tmp_path):
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    s = Settings.load(cfg)
    s.save_dir = str(tmp_path / "inbox")
    rec = Recorder()
    hub = Hub(s, Devices(cfg), rec)
    port = hub.start("127.0.0.1", 0)
    base = f"http://127.0.0.1:{port}"
    yield hub, rec, base, tmp_path
    hub.stop()


def paired(hub, rec, base, name="iPhone · Safari"):
    sess = requests.Session()
    r = sess.post(base + "/api/pair", json={"key": hub.key, "name": name, "kind": "ios"}, headers=H)
    assert r.status_code == 200, r.text
    req = r.json()["req"]
    threading.Timer(0.3, lambda: hub.resolve_pair(req, True)).start()
    w = sess.get(base + f"/api/pair/{req}", headers=H)
    assert w.json()["status"] == "approved"
    assert "skiffdrop" in sess.cookies
    return sess


def send(sess, base, name, data: bytes, chunk=16 << 20):
    r = sess.post(base + "/api/upload", json={"name": name, "size": len(data), "modified": 1}, headers=H)
    assert r.status_code == 200, r.text
    uid, off = r.json()["id"], r.json()["received"]
    saved = r.json().get("saved")
    while off < len(data):
        r = sess.put(base + f"/api/upload/{uid}?offset={off}", data=data[off:off + chunk], headers=H)
        assert r.status_code == 200, r.text
        off, saved = r.json()["received"], r.json()["saved"]
    return saved


def test_page_and_guards(env):
    hub, rec, base, _ = env
    r = requests.get(base + "/")
    assert r.status_code == 200 and "Skiffdrop" in r.text
    assert "frame-ancestors 'none'" in r.headers["Content-Security-Policy"]
    assert requests.get(base + "/api/events").status_code == 401
    # DNS rebinding: a name in the Host header is refused
    assert requests.get(base + "/", headers={"Host": "evil.example:80"}).status_code == 403
    # writes need our header, and a foreign Origin is refused
    assert requests.post(base + "/api/pair", json={"key": hub.key}).status_code == 403
    assert requests.post(base + "/api/pair", json={"key": hub.key},
                         headers={**H, "Origin": "http://evil.example"}).status_code == 403
    assert requests.post(base + "/api/pair", json={"key": hub.key},
                         headers={**H, "Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert not rec.pairs


def test_wrong_codes_lock_out(env):
    hub, rec, base, _ = env
    for _ in range(5):
        assert requests.post(base + "/api/pair", json={"code": "000000" if hub.code != "000000" else "111111"},
                             headers=H).status_code == 403
    r = requests.post(base + "/api/pair", json={"key": hub.key}, headers=H)
    assert r.status_code == 429  # even the right key waits now


def test_pin_and_code_and_deny(env):
    hub, rec, base, _ = env
    hub.settings.set_pin("4321")
    assert requests.post(base + "/api/pair", json={"code": hub.code, "pin": "1"}, headers=H).json()["error"] == "pin"
    r = requests.post(base + "/api/pair", json={"code": hub.code, "pin": "4321", "name": "Pixel 8"}, headers=H)
    req = r.json()["req"]
    assert rec.pairs[-1].name == "Pixel 8"
    hub.resolve_pair(req, False)
    assert requests.get(base + f"/api/pair/{req}").json()["status"] == "denied"
    assert requests.get(base + f"/api/pair/{req}").json()["status"] == "expired"  # answered once


def test_upload_names_stay_inside(env):
    hub, rec, base, tmp = env
    sess = paired(hub, rec, base)
    inbox = tmp / "inbox"
    cases = {
        "../../evil.txt": "evil.txt",
        "..\\..\\Windows\\x.bat": "x.bat",
        "CON.txt": "_CON.txt",
        'a<b>:c|d?.txt': "a_b__c_d_.txt",
        "photo‮gpj.exe": "photogpj.exe",
        "صورة العائلة 2026.jpg": "صورة العائلة 2026.jpg",
        "  trailing dots... ": "trailing dots",
        "": "file",
    }
    for raw, expect in cases.items():
        saved = send(sess, base, raw, b"x" * 1024)
        assert saved == expect, (raw, saved)
        assert (inbox / expect).read_bytes() == b"x" * 1024
    assert send(sess, base, "صورة العائلة 2026.jpg", b"y") == "صورة العائلة 2026 (1).jpg"
    assert send(sess, base, "empty.bin", b"") == "empty.bin"
    assert sorted(p.name for p in tmp.iterdir()) == ["cfg", "inbox"]  # nothing escaped
    assert not list((inbox / ".skiffdrop-incoming").iterdir())


def test_resume_after_drop(env):
    hub, rec, base, tmp = env
    sess = paired(hub, rec, base)
    data = os.urandom(3 << 20)
    uid = sess.post(base + "/api/upload", json={"name": "video.mp4", "size": len(data), "modified": 5},
                    headers=H).json()["id"]
    assert sess.put(base + f"/api/upload/{uid}?offset=0", data=data[:1 << 20], headers=H).json()["received"] == 1 << 20
    # a stale offset is refused and tells the phone where to carry on
    r = sess.put(base + f"/api/upload/{uid}?offset=0", data=data[:10], headers=H)
    assert r.status_code == 409 and r.json()["received"] == 1 << 20
    # the page was reloaded: starting the same file again resumes it
    again = sess.post(base + "/api/upload", json={"name": "video.mp4", "size": len(data), "modified": 5},
                      headers=H).json()
    assert again == {"id": uid, "received": 1 << 20}
    r = sess.put(base + f"/api/upload/{uid}?offset={1 << 20}", data=data[1 << 20:], headers=H)
    assert r.json()["saved"] == "video.mp4"
    assert hashlib.sha256((tmp / "inbox" / "video.mp4").read_bytes()).digest() == hashlib.sha256(data).digest()


def test_cancel_removes_part(env):
    hub, rec, base, tmp = env
    sess = paired(hub, rec, base)
    uid = sess.post(base + "/api/upload", json={"name": "big.bin", "size": 10 << 20}, headers=H).json()["id"]
    sess.put(base + f"/api/upload/{uid}?offset=0", data=b"z" * (1 << 20), headers=H)
    assert sess.delete(base + f"/api/upload/{uid}", headers=H).status_code == 200
    assert not list((tmp / "inbox" / ".skiffdrop-incoming").iterdir())
    assert sess.put(base + f"/api/upload/{uid}?offset={1 << 20}", data=b"z", headers=H).status_code == 404


def test_downloads_ranges_zip_and_text(env):
    hub, rec, base, tmp = env
    sess = paired(hub, rec, base, "Galaxy S24 · Chrome")
    src = tmp / "out"
    (src / "album").mkdir(parents=True)
    a = os.urandom(300_000)
    (src / "ملف عربي.pdf").write_bytes(a)
    (src / "album" / "1.jpg").write_bytes(b"jpg1")
    (src / "album" / "2.jpg").write_bytes(b"jpg2")
    v0 = sess.get(base + "/api/events?since=0", headers=H).json()["v"]
    got = {}
    t = threading.Thread(target=lambda: got.update(sess.get(base + f"/api/events?since={v0}", headers=H).json()))
    t.start()
    time.sleep(0.3)
    assert hub.share([src / "ملف عربي.pdf", src / "album"]) == 3
    t.join(5)
    files = {f["rel"]: f for f in got["files"]}  # the long poll woke up with the new list
    assert set(files) == {"ملف عربي.pdf", "album/1.jpg", "album/2.jpg"}
    f = files["ملف عربي.pdf"]
    r = sess.get(base + f"/api/file/{f['id']}/x?dl=1", headers=H)
    assert r.content == a
    assert "filename*=UTF-8''%D9%85%D9%84%D9%81" in r.headers["Content-Disposition"]
    assert "sandbox" in r.headers["Content-Security-Policy"]
    r = sess.get(base + f"/api/file/{f['id']}/x", headers={**H, "Range": "bytes=100-199"})
    assert r.status_code == 206 and r.content == a[100:200]
    assert r.headers["Content-Range"] == f"bytes 100-199/{len(a)}"
    r = sess.get(base + f"/api/file/{f['id']}/x", headers={**H, "Range": "bytes=-10"})
    assert r.content == a[-10:]
    assert sess.get(base + f"/api/file/{f['id']}/x", headers={**H, "Range": "bytes=999999-"}).status_code == 416
    assert sess.head(base + f"/api/file/{f['id']}/x", headers=H).headers["Content-Length"] == str(len(a))
    z = zipfile.ZipFile(io.BytesIO(sess.get(base + "/api/zip/all.zip?dl=1", headers=H).content))
    assert sorted(z.namelist()) == ["album/1.jpg", "album/2.jpg", "ملف عربي.pdf"]
    assert z.read("ملف عربي.pdf") == a and z.testzip() is None
    assert requests.get(base + f"/api/file/{f['id']}/x").status_code == 401  # not without the cookie

    hub.send_text("https://example.com/مرحبا")
    assert sess.get(base + "/api/events?since=0", headers=H).json()["texts"][-1]["text"] == "https://example.com/مرحبا"
    assert sess.post(base + "/api/text", json={"text": "من الهاتف"}, headers=H).status_code == 200
    assert rec.texts[-1] == ("Galaxy S24 · Chrome", "من الهاتف")


def test_revoke_and_bye(env):
    hub, rec, base, _ = env
    sess = paired(hub, rec, base)
    assert sess.get(base + "/api/me").json()["paired"] is True
    dev = hub.devices.all()[0]
    hub.revoke(dev.id)
    assert sess.get(base + "/api/me").json()["paired"] is False
    assert sess.post(base + "/api/upload", json={"name": "a", "size": 1}, headers=H).status_code == 401
    sess2 = paired(hub, rec, base)
    assert sess2.post(base + "/api/bye", headers=H).status_code == 200
    assert hub.devices.all() == []


def test_devices_survive_restart(env, tmp_path):
    hub, rec, base, _ = env
    sess = paired(hub, rec, base)
    hub.stop()
    hub2 = Hub(hub.settings, Devices(tmp_path / "cfg"), Recorder())
    port = hub2.start("127.0.0.1", 0)
    try:
        cookie = sess.cookies.get("skiffdrop")
        r = requests.get(f"http://127.0.0.1:{port}/api/me", cookies={"skiffdrop": cookie})
        assert r.json()["paired"] is True
    finally:
        hub2.stop()


def test_qr_link_carries_key_and_code(env):
    hub, rec, base, _ = env
    url = hub.url("192.168.1.20")
    assert url == f"http://192.168.1.20:{hub.port}/#k={hub.key}&c={hub.code}"
    assert hub.url("192.168.1.20", with_key=False) == f"http://192.168.1.20:{hub.port}/"
    # the page sends both; either one is enough for the server
    r = requests.post(base + "/api/pair", json={"key": hub.key, "code": hub.code, "name": "x"}, headers=H)
    assert r.status_code == 200


def test_history_survives_restart(tmp_path):
    from skiffdrop.history import History
    h = History(tmp_path)
    h.add_message("in", "iPhone · Safari", "مرحبا https://example.com", True)
    h.put_file({"id": "a", "dir": "in", "device": "iPhone", "name": "x.jpg", "path": "C:/x.jpg", "size": 5,
                "t": 1.0, "state": "done"})
    h.put_file({"id": "a", "dir": "in", "device": "iPhone", "name": "x.jpg", "path": "C:/x.jpg", "size": 6,
                "t": 2.0, "state": "done"})
    again = History(tmp_path)
    assert again.messages[0]["text"] == "مرحبا https://example.com" and again.messages[0]["copied"]
    assert len(again.files) == 1 and again.files[0]["size"] == 6
    again.clear_files()
    assert History(tmp_path).files == [] and History(tmp_path).messages
