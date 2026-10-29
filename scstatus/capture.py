"""Reading the game's debug overlay off the screen every few seconds.

Only runs OCR while Star Citizen is the window in front, and only on the corner
of the screen where the overlay sits. The Session line on the overlay is never
read into the readings.
"""

import os
import time

import numpy as np

from .config import say


def game_in_front():
    """True when the Star Citizen window has focus (always True off Windows, for testing)."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        n = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(n + 1)
        user32.GetWindowTextW(hwnd, buf, n + 1)
        return "star citizen" in buf.value.lower()
    except Exception:
        return True


def make_grabber(monitor=1):
    import cv2
    import mss
    sct = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
    mons = sct.monitors
    mon = mons[monitor] if 0 < monitor < len(mons) else mons[1]
    # The overlay lives in the top right; grabbing just that is much cheaper at 4K
    region = {"left": mon["left"] + mon["width"] // 2, "top": mon["top"],
              "width": mon["width"] - mon["width"] // 2, "height": int(mon["height"] * 0.4)}

    def grab():
        img = cv2.cvtColor(np.array(sct.grab(region)), cv2.COLOR_BGRA2BGR)
        return img, (mon["width"], mon["height"])
    return grab


class OverlayWatcher:
    """Grabs and reads the overlay on a timer; hands each reading to on_reading."""

    def __init__(self, every_s=5, monitor=1, on_reading=None):
        self.every = max(1.0, float(every_s))
        self.monitor = monitor
        self.on_reading = on_reading
        self.reader = None
        self.grab = None
        self.status = "starting"
        self.last_ok = None
        self.misses = 0

    def _setup(self):
        from .overlay import OverlayReader
        self.reader = OverlayReader()
        self.grab = make_grabber(self.monitor)

    def place(self, crop, full_size):
        """Put the top-right crop back into a full-size dark frame so positions match a real screen."""
        W, H = full_size
        frame = np.zeros((H, W, 3), dtype=np.uint8)
        h, w = crop.shape[:2]
        frame[0:h, W - w:W] = crop
        return frame

    def tick(self):
        if not game_in_front():
            self.status = "waiting for the game window"
            return None
        crop, size = self.grab()
        snap = self.reader.read(self.place(crop, size))
        snap["ts"] = time.time()
        snap.pop("session", None)
        if snap.get("ok"):
            self.status = "reading"
            self.last_ok = snap["ts"]
            self.misses = 0
        else:
            self.misses += 1
            if self.misses >= 3:
                self.status = "no overlay on screen (type r_displayinfo 3 in the game console)"
        return snap

    def run(self, stop):
        try:
            self._setup()
        except Exception as e:
            self.status = f"screen reading unavailable ({e})"
            say(f"Overlay reading unavailable: {e}")
            return
        while not stop.is_set():
            t0 = time.time()
            try:
                snap = self.tick()
                if snap and snap.get("ok") and self.on_reading:
                    self.on_reading(snap)
            except Exception as e:
                self.status = f"error: {e}"
            stop.wait(max(0.5, self.every - (time.time() - t0)))
