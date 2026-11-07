"""Local-network helpers: which address the phone should use, who may connect,
and the Windows bits (Downloads folder, network category, firewall rule)."""

from __future__ import annotations

import ctypes
import ipaddress
import os
import socket
import subprocess
import sys
import uuid
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

_PRIVATE4 = [ipaddress.ip_network(n) for n in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")]
_ULA = ipaddress.ip_network("fc00::/7")
_VIRTUAL = ("virtual", "hyper-v", "vethernet", "vmware", "virtualbox", "vbox", "wsl", "tap", "tun",
            "wireguard", "nordlynx", "openvpn", "vpn", "zerotier", "tailscale", "loopback", "bluetooth",
            "docker", "npcap", "wi-fi direct", "teredo", "isatap")
NO_WINDOW = 0x08000000


def is_lan(ip: str) -> bool:
    """True for loopback, link-local and private (RFC 1918 / ULA) addresses: never the internet."""
    try:
        a = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    if a.is_loopback or a.is_link_local:
        return True
    if a.version == 4:
        return any(a in n for n in _PRIVATE4)
    return a in _ULA


def host_ok(host: str) -> bool:
    """The Host header must be an IP address (or localhost): a page on some
    other site can't rebind its own name to this PC and read our answers."""
    h = (host or "").strip()
    if not h:
        return False
    if h.startswith("["):
        h = h[1:h.find("]")] if "]" in h else ""
    elif h.count(":") == 1:
        h = h.split(":", 1)[0]
    if h.lower() == "localhost":
        return True
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return False


@dataclass
class Address:
    ip: str
    adapter: str
    kind: str        # "Wi-Fi", "Ethernet" or "Other"
    gateway: bool
    virtual: bool
    if_index: int

    @property
    def score(self) -> int:
        s = 4 if self.gateway else 0
        s += 2 if self.kind in ("Wi-Fi", "Ethernet") else 0
        s += 1 if self.ip.startswith("192.168.") else 0
        return s - (8 if self.virtual else 0)

    def label(self) -> str:
        return f"{self.ip}  ({self.adapter})"


class _SOCKET_ADDRESS(ctypes.Structure):
    _fields_ = [("lpSockaddr", ctypes.c_void_p), ("iSockaddrLength", ctypes.c_int)]


class _UNICAST(ctypes.Structure):
    pass


_UNICAST._fields_ = [("Length", wintypes.ULONG), ("Flags", wintypes.DWORD),
                     ("Next", ctypes.POINTER(_UNICAST)), ("Address", _SOCKET_ADDRESS)]


class _GATEWAY(ctypes.Structure):
    pass


_GATEWAY._fields_ = [("Length", wintypes.ULONG), ("Reserved", wintypes.DWORD),
                     ("Next", ctypes.POINTER(_GATEWAY)), ("Address", _SOCKET_ADDRESS)]


class _ADAPTER(ctypes.Structure):
    pass


_ADAPTER._fields_ = [
    ("Length", wintypes.ULONG), ("IfIndex", wintypes.DWORD), ("Next", ctypes.POINTER(_ADAPTER)),
    ("AdapterName", ctypes.c_char_p), ("FirstUnicastAddress", ctypes.POINTER(_UNICAST)),
    ("FirstAnycastAddress", ctypes.c_void_p), ("FirstMulticastAddress", ctypes.c_void_p),
    ("FirstDnsServerAddress", ctypes.c_void_p), ("DnsSuffix", ctypes.c_wchar_p),
    ("Description", ctypes.c_wchar_p), ("FriendlyName", ctypes.c_wchar_p),
    ("PhysicalAddress", ctypes.c_ubyte * 8), ("PhysicalAddressLength", wintypes.ULONG),
    ("Flags", wintypes.ULONG), ("Mtu", wintypes.ULONG), ("IfType", wintypes.ULONG),
    ("OperStatus", ctypes.c_int), ("Ipv6IfIndex", wintypes.DWORD), ("ZoneIndices", wintypes.DWORD * 16),
    ("FirstPrefix", ctypes.c_void_p), ("TransmitLinkSpeed", ctypes.c_uint64),
    ("ReceiveLinkSpeed", ctypes.c_uint64), ("FirstWinsServerAddress", ctypes.c_void_p),
    ("FirstGatewayAddress", ctypes.POINTER(_GATEWAY)),
]


def _ipv4(sa: _SOCKET_ADDRESS) -> str | None:
    if not sa.lpSockaddr:
        return None
    family = ctypes.c_ushort.from_address(sa.lpSockaddr).value
    if family != socket.AF_INET:
        return None
    raw = (ctypes.c_ubyte * 4).from_address(sa.lpSockaddr + 4)
    return ".".join(str(b) for b in raw)


def addresses() -> list[Address]:
    """Private IPv4 addresses of the adapters that are up, best first."""
    found: list[Address] = []
    try:
        iphlp = ctypes.windll.iphlpapi
        size = wintypes.ULONG(64 * 1024)
        for _ in range(3):
            buf = ctypes.create_string_buffer(size.value)
            # AF_INET, GAA_FLAG_SKIP_ANYCAST|SKIP_MULTICAST|SKIP_DNS_SERVER|INCLUDE_GATEWAYS
            rc = iphlp.GetAdaptersAddresses(socket.AF_INET, 0x2 | 0x4 | 0x8 | 0x80, None, buf, ctypes.byref(size))
            if rc != 111:  # ERROR_BUFFER_OVERFLOW
                break
        if rc == 0:
            node = ctypes.cast(buf, ctypes.POINTER(_ADAPTER))
            while node:
                a = node.contents
                if a.OperStatus == 1 and a.IfType != 24:  # up, not loopback
                    text = f"{a.FriendlyName or ''} {a.Description or ''}".lower()
                    kind = {71: "Wi-Fi", 6: "Ethernet"}.get(a.IfType, "Other")
                    virtual = any(v in text for v in _VIRTUAL) or a.IfType in (53, 131)
                    gw = bool(a.FirstGatewayAddress) and _ipv4(a.FirstGatewayAddress.contents.Address) not in (None, "0.0.0.0")
                    u = a.FirstUnicastAddress
                    while u:
                        ip = _ipv4(u.contents.Address)
                        if ip and is_lan(ip) and not ip.startswith(("127.", "169.254.")):
                            found.append(Address(ip, a.FriendlyName or a.Description or "adapter", kind, gw,
                                                 virtual, a.IfIndex))
                        u = u.contents.Next
                node = a.Next
    except (OSError, AttributeError):
        pass
    if not found:  # not Windows, or the call failed: whatever the host name resolves to
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = info[4][0]
                if is_lan(ip) and not ip.startswith("127.") and ip not in [f.ip for f in found]:
                    found.append(Address(ip, "network", "Other", False, False, 0))
        except OSError:
            pass
    found.sort(key=lambda a: -a.score)
    return found


def downloads_dir() -> Path:
    """The user's Downloads folder, wherever they moved it."""
    try:
        guid = (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID("374DE290-123F-4565-9164-39C4925E467B").bytes_le)
        out = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(out)) == 0:
            path = Path(out.value)
            ctypes.windll.ole32.CoTaskMemFree(out)
            return path
    except (OSError, AttributeError):
        pass
    return Path.home() / "Downloads"


def network_category(if_index: int) -> str:
    """"Private", "Public", "DomainAuthenticated" or "" (unknown) for an adapter."""
    if not if_index or sys.platform != "win32":
        return ""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                              f"(Get-NetConnectionProfile -InterfaceIndex {int(if_index)}).NetworkCategory"],
                             capture_output=True, text=True, timeout=15, creationflags=NO_WINDOW)
        return out.stdout.strip().splitlines()[0] if out.stdout.strip() else ""
    except (OSError, subprocess.SubprocessError):
        return ""


RULE = "Skiffdrop"


def firewall_rule_exists() -> bool:
    """True when an inbound allow rule named Skiffdrop exists (reading rules needs no admin)."""
    try:
        out = subprocess.run(["netsh", "advfirewall", "firewall", "show", "rule", f"name={RULE}", "dir=in"],
                             capture_output=True, text=True, timeout=15, creationflags=NO_WINDOW)
        return out.returncode == 0 and "Allow" in out.stdout
    except (OSError, subprocess.SubprocessError):
        return True  # can't tell: don't nag


def add_firewall_rule(program: str, port: int) -> bool:
    """One admin prompt: replaces this program's inbound rules (Windows' own "blocked"
    rules included) with one that allows TCP on our port, on private networks only."""
    q = f'"{program}"'
    script = (f'netsh advfirewall firewall delete rule name=all dir=in program={q} & '
              f'netsh advfirewall firewall delete rule name="{RULE}" & '
              f'netsh advfirewall firewall add rule name="{RULE}" dir=in action=allow program={q} '
              f'protocol=TCP localport={int(port)} profile=private enable=yes '
              f'description="Lets phones on your home Wi-Fi reach Skiffdrop."')
    try:
        SEE_MASK_NOCLOSEPROCESS = 0x40

        class SHELLEXECUTEINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
                        ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR),
                        ("lpParameters", wintypes.LPCWSTR), ("lpDirectory", wintypes.LPCWSTR),
                        ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE), ("lpIDList", ctypes.c_void_p),
                        ("lpClass", wintypes.LPCWSTR), ("hkeyClass", wintypes.HKEY), ("dwHotKey", wintypes.DWORD),
                        ("hIcon", wintypes.HANDLE), ("hProcess", wintypes.HANDLE)]
        info = SHELLEXECUTEINFO(cbSize=ctypes.sizeof(SHELLEXECUTEINFO), fMask=SEE_MASK_NOCLOSEPROCESS,
                                lpVerb="runas", lpFile=os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                                                                    "System32", "cmd.exe"),
                                lpParameters=f"/c {script}", nShow=0)
        if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
            return False  # the user said no to the admin prompt
        ctypes.windll.kernel32.WaitForSingleObject(info.hProcess, 30000)
        ctypes.windll.kernel32.CloseHandle(info.hProcess)
        return firewall_rule_exists()
    except (OSError, AttributeError):
        return False
