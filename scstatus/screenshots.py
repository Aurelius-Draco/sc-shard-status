"""Readings from screenshots you take in game (Print Screen).

The app watches StarCitizen\\LIVE\\screenshots. Any new screenshot with the debug
overlay on it becomes a reading, the same as the live screen reading. If the
session QR code is on (r_DisplaySessionInfo 1), its shard and time are used too.
Nothing about the session id is kept.
"""

import re
import time
from pathlib import Path

from .config import say

QR_TEXT = re.compile(r"^\S+\s+(?P<shard>[a-z]+_[a-z0-9]+_\d+_\d+)\s+(?P<ts>\d{9,11})\s+(?P<env>\S+)$")


def read_qr(img):
    """The session QR code -> {shard_id, ts, env}. Only looks in the top-right corner."""
    import cv2
    h, w = img.shape[:2]
    corner = img[0:int(h * 0.25), int(w * 0.75):w]
    try:
        text, _, _ = cv2.QRCodeDetector().detectAndDecode(corner)
    except Exception:
        return None
    m = QR_TEXT.match((text or "").strip())
    if not m:
        return None
    return {"shard_id": m.group("shard"), "ts": int(m.group("ts")), "env": m.group("env")}


class ScreenshotWatcher:
    def __init__(self, folder, reader_factory, on_reading=None, every_s=3):
        self.folder = Path(folder)
        self.reader_factory = reader_factory
        self.reader = None
        self.on_reading = on_reading
        self.every = every_s
        self.seen = set()
        self.started = time.time()
        self.count = 0

    def read_file(self, path):
        import cv2
        import numpy as np
        data = np.fromfile(str(path), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is None:
            return None
        if self.reader is None:
            self.reader = self.reader_factory()
        snap = self.reader.read(img)
        snap.pop("session", None)
        qr = read_qr(img)
        snap["ts"] = path.stat().st_mtime
        if qr:
            snap["shard_id"] = snap.get("shard_id") or qr["shard_id"]
            if abs(qr["ts"] - snap["ts"]) < 3600:
                snap["ts"] = qr["ts"]
        snap["source"] = "screenshot"
        return snap

    def poll(self):
        if not self.folder.exists():
            return 0
        n = 0
        for p in self.folder.iterdir():
            if p.suffix.lower() not in (".jpg", ".jpeg", ".png") or p.name in self.seen:
                continue
            self.seen.add(p.name)
            try:
                if p.stat().st_mtime < self.started:
                    continue
                time.sleep(0.3)         # let the game finish writing it
                snap = self.read_file(p)
            except Exception as e:
                say(f"Couldn't read screenshot {p.name} ({e}).")
                continue
            if snap and snap.get("ok"):
                self.count += 1
                n += 1
                if self.on_reading:
                    self.on_reading(snap)
        return n

    def run(self, stop):
        while not stop.is_set():
            try:
                self.poll()
            except Exception:
                pass
            stop.wait(self.every)
