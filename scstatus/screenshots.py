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


SHOT_NAME_RX = re.compile(r"^[\w .()\-]{1,120}\.(jpg|jpeg|png)$", re.I)


def list_shots(folder, lo, hi, limit=12):
    """Screenshots in the game's folder taken between lo and hi (file time), newest first: [{name, ts}]."""
    folder = Path(folder)
    out = []
    try:
        for p in folder.iterdir():
            if p.is_file() and SHOT_NAME_RX.match(p.name):
                t = p.stat().st_mtime
                if lo <= t <= hi:
                    out.append({"name": p.name, "ts": t})
    except OSError:
        return []
    out.sort(key=lambda x: -x["ts"])
    return out[:limit]


def shot_path(folder, name):
    """The screenshot called name, only if it's a picture directly inside folder. None otherwise."""
    if not isinstance(name, str) or not SHOT_NAME_RX.match(name) or name in (".", ".."):
        return None
    folder = Path(folder)
    try:
        p = (folder / name).resolve()
        if p.parent != folder.resolve() or not p.is_file():
            return None
    except OSError:
        return None
    return p


def thumbnail(folder, name, width=480):
    """A small JPEG of one screenshot for the moment picker: (bytes, mime), or None. Falls back to the file itself
    when it can't be shrunk."""
    p = shot_path(folder, name)
    if not p:
        return None
    try:
        import cv2
        import numpy as np
        img = cv2.imdecode(np.fromfile(str(p), dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is not None:
            h, w = img.shape[:2]
            if w > width:
                img = cv2.resize(img, (width, max(1, round(h * width / w))), interpolation=cv2.INTER_AREA)
            ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if ok:
                return buf.tobytes(), "image/jpeg"
    except Exception:
        pass
    try:
        return p.read_bytes(), "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
    except OSError:
        return None
