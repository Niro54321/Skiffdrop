"""What was sent and received, kept in %APPDATA%\\Skiffdrop\\history.json so it is still
there after a restart. Clearing a list only forgets the entries: files stay where they are."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

KEEP = 400  # entries per list


class History:
    def __init__(self, folder: Path):
        self.path = Path(folder) / "history.json"
        self.messages: list[dict] = []
        self.files: list[dict] = []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.messages = [m for m in data.get("messages", []) if isinstance(m, dict) and "text" in m]
            self.files = [f for f in data.get("files", []) if isinstance(f, dict) and "name" in f]
        except (OSError, ValueError, AttributeError):
            pass

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        try:
            tmp.write_text(json.dumps({"messages": self.messages[-KEEP:], "files": self.files[-KEEP:]},
                                      ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass

    def add_message(self, direction: str, device: str, text: str, copied: bool = False) -> dict:
        m = {"dir": direction, "device": device, "text": text[:20000], "t": time.time(), "copied": copied}
        self.messages.append(m)
        del self.messages[:-KEEP]
        self.save()
        return m

    def put_file(self, entry: dict) -> None:
        """Adds or updates a finished transfer (keyed by its id)."""
        for i, f in enumerate(self.files):
            if f.get("id") == entry["id"]:
                self.files[i] = entry
                break
        else:
            self.files.append(entry)
        del self.files[:-KEEP]
        self.save()

    def clear_messages(self) -> None:
        self.messages.clear()
        self.save()

    def clear_files(self) -> None:
        self.files.clear()
        self.save()
