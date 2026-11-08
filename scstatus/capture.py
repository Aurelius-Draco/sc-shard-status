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
    """True when the Star Citizen game window has focus (always True off Windows, for testing).
    Checks the process behind the window, so a browser tab called "Star Citizen" doesn't count."""
    if os.name != "nt":
        return True
    try:
        import ctypes
        from ctypes import wintypes
        user32, kernel32 = ctypes.windll.user32, ctypes.windll.kernel32
        hwnd = user32.GetForegroundWindow()
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        h = kernel32.OpenProcess(0x1000, False, pid.value)       # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return False
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if not kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                return False
            return os.path.basename(buf.value).lower() == "starcitizen.exe"
        finally:
            kernel32.CloseHandle(h)
    except Exception:
        return True


def game_rect():
    """Where the game draws on the desktop: the Star Citizen window's inside (no title bar), as
    (left, top, width, height) in screen pixels. Called right after game_in_front(), so the window in front is the
    game. Follows the game to whichever monitor it's on, at whatever size it draws (9 Nov: players with the game on
    their second screen got "overlay off" because only monitor 1 was read). None when it can't be told."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd or user32.IsIconic(hwnd):
            return None
        rc = wintypes.RECT()
        if not user32.GetClientRect(hwnd, ctypes.byref(rc)):
            return None
        pt = wintypes.POINT(0, 0)
        if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
            return None
        return pt.x, pt.y, rc.right - rc.left, rc.bottom - rc.top
    except Exception:
        return None


def _region(left, top, w, h):
    # The overlay lives in the top right; grabbing just that is much cheaper at 4K
    return {"left": left + w // 2, "top": top, "width": w - w // 2, "height": int(h * 0.4)}


def pick_area(mons, monitor, rect):
    """The part of the desktop to read and the screen size the overlay's text is drawn for.

    With the game's window known (at least 640x360, its middle on a monitor): the top right of that window. The
    game draws the overlay's text at the same pixel size in a small window as full screen on that monitor (9 Nov,
    a 1920x1080 window on a 4K screen had 4K-sized text), so the size handed on is the monitor's, and the slice is
    at least as wide and tall as the overlay is on that monitor (about 42% by 40% of it), within the window.
    Otherwise the monitor in config (1 = main), as before."""
    if rect:
        x, y, w, h = rect
        cx, cy = x + w // 2, y + h // 2
        on = next((m for m in mons[1:] if m["left"] <= cx < m["left"] + m["width"]
                   and m["top"] <= cy < m["top"] + m["height"]), None)
        if on and w >= 640 and h >= 360:
            # clip to the screen it's on (a maximised window hangs a few pixels over the edges)
            l, t = max(x, on["left"]), max(y, on["top"])
            r, b = min(x + w, on["left"] + on["width"]), min(y + h, on["top"] + on["height"])
            if r - l >= 640 and b - t >= 360:
                W, H = on["width"], on["height"]
                cw = min(r - l, max((r - l) - (r - l) // 2, int(W * 0.42)))
                ch = min(b - t, max(int((b - t) * 0.4), int(H * 0.4)))
                return {"left": r - cw, "top": t, "width": cw, "height": ch}, (max(W, r - l), max(H, b - t)), "window"
    mon = mons[monitor] if 0 < monitor < len(mons) else mons[1]
    return _region(mon["left"], mon["top"], mon["width"], mon["height"]), (mon["width"], mon["height"]), "monitor"


def make_grabber(monitor=1, sct=None):
    import cv2
    if sct is None:
        import mss
        sct = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
    state = {"sct": sct}

    def grab(rect=None):
        s = state["sct"]
        mons = s.monitors
        region, size, how = pick_area(mons, monitor, rect)
        if rect and how == "monitor" and not getattr(grab, "relisted", False):
            # the game's window isn't on any screen we know: the screens changed since they were listed (a monitor
            # added, or exclusive fullscreen changed the resolution), so list them again, once
            try:
                import mss
                state["sct"] = s = mss.MSS() if hasattr(mss, "MSS") else mss.mss()
                region, size, how = pick_area(s.monitors, monitor, rect)
            except Exception:
                pass
            grab.relisted = True
        elif how == "window":
            grab.relisted = False
        img = cv2.cvtColor(np.array(s.grab(region)), cv2.COLOR_BGRA2BGR)
        grab.how, grab.region, grab.rect = how, region, rect
        return img, size
    grab.how = grab.region = grab.rect = None
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
        self.tries = 0              # readings attempted with the game in front (for the reading-quality counts)
        self.failed = 0             # of those, ones that couldn't be read at all
        self.screen = None          # e.g. "2560x1440"

    def _setup(self):
        from .overlay import OverlayReader
        self.reader = OverlayReader(threads=2)     # leave the CPU to the game
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
        crop, size = self.grab(game_rect())
        self.screen = f"{size[0]}x{size[1]}"
        self._note_area(size)
        self.tries += 1
        snap = self.reader.read(self.place(crop, size))
        snap["ts"] = time.time()
        snap.pop("session", None)
        if snap.get("ok"):
            self.status = "reading"
            self.last_ok = snap["ts"]
            self.misses = 0
        else:
            self.misses += 1
            self.failed += 1
            if self.misses == 3:
                self._save_miss(crop)
            if self.misses >= 3:
                self.status = ("overlay off, readings paused (type r_displayinfo 3 to start again; bright scenery "
                               "behind the text also stops it, see Set up for tips)")
        return snap

    def _note_area(self, size):
        """One line in the log whenever what's read changes: the game's window or the monitor, where, what size."""
        g = self.grab
        r, how = getattr(g, "region", None), getattr(g, "how", None)
        key = (how, tuple(sorted(r.items())) if r else None, size)
        if key != getattr(self, "_area", None):
            self._area = key
            win = getattr(g, "rect", None)
            say(f"Overlay: reading the {'game window' if how == 'window' else 'monitor'} "
                f"({size[0]}x{size[1]}), top right from {r['left']},{r['top']} size {r['width']}x{r['height']}"
                + (f"; game window {win}" if win else "; game window not found") if r else "Overlay: reading")

    def _save_miss(self, crop):
        """When the overlay can't be read, keep the last picture of what was looked at, in the app's data folder
        (overlay-miss.png). Stays on this PC: it's for the player, or for help when they choose to send it."""
        try:
            import cv2
            from .config import DATA
            cv2.imwrite(str(DATA / "overlay-miss.png"), crop)
        except Exception:
            pass

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
                from . import errors
                errors.capture("overlay", e)
            stop.wait(max(0.5, self.every - (time.time() - t0)))
