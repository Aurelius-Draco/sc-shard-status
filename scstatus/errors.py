"""Opt-in error reports: when something in the app itself goes wrong, where and what, so it can be fixed.

Off unless you say yes on the Set up tab. What's sent: the app version, a random install id, where in the app it
went wrong (module and line), the error message and the stack trace with every file path cut down to the file
name and anything in quotes taken out. Never Game.log lines, your handle, your files or screenshots.
"""

import hashlib
import re
import sys
import threading
import time
import traceback

SEND_EVERY_S = 1800
_lock = threading.Lock()
_pending = {}            # sig -> {sig, place, message, trace, n}
_installed = False


def _scrub(text, n):
    t = str(text or "")
    t = re.sub(r"[A-Za-z]:\\[^\s\"'<>]*\\([^\\\s\"'<>]+)", r"\1", t)          # C:\Users\x\...\file.py -> file.py
    t = re.sub(r"/(?:home|Users|root|tmp|mnt)/[^\s\"'<>]*/([^/\s\"'<>]+)", r"\1", t)
    t = re.sub(r"'[^'\n]{0,200}'|\"[^\"\n]{0,200}\"", "'…'", t)              # quoted values: names, paths, text
    t = re.sub(r"\b\d{6,}\b", "<n>", t)                                        # ids
    return t[:n]


def capture(place, exc=None):
    """Note an error (call from an except block, or pass the exception). Kept in memory until sent."""
    exc = exc or sys.exc_info()[1]
    if exc is None:
        return
    tb = traceback.extract_tb(exc.__traceback__) if exc.__traceback__ else []
    top = tb[-1] if tb else None
    where = f"{place}:{top.name}:{top.lineno}" if top else place
    sig = hashlib.sha1(f"{where}|{type(exc).__name__}".encode()).hexdigest()[:12]
    trace = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)[-12:])
    with _lock:
        e = _pending.setdefault(sig, {"sig": sig, "place": _scrub(where, 80), "n": 0})
        e["n"] += 1
        e["message"] = _scrub(f"{type(exc).__name__}: {exc}", 300)
        e["trace"] = _scrub(trace, 2000)


def install():
    """Catch errors nobody else caught (in any thread) too."""
    global _installed
    if _installed:
        return
    _installed = True
    old = threading.excepthook

    def hook(args):
        capture(f"thread {getattr(args.thread, 'name', '?')}", args.exc_value)
        old(args)
    threading.excepthook = hook


def payload(install_id, version):
    with _lock:
        rows = list(_pending.values())[:10]
    if not rows:
        return None
    return {"v": 1, "kind": "errors", "install": install_id, "version": version, "errors": rows}


def sent(rows):
    with _lock:
        for r in rows:
            _pending.pop(r["sig"], None)


class ErrorReports:
    def __init__(self, app, community):
        self.app, self.community = app, community
        self.sent_at = 0
        self.sent_n = 0
        self.last_payload = None

    def tick(self, now=None):
        now = now or time.time()
        if not self.app.cfg.get("send_errors") or now - self.sent_at < SEND_EVERY_S:
            return
        self.sent_at = now
        from .config import VERSION
        p = payload(self.app.store.install_id(), VERSION)
        if not p:
            return
        try:
            code, _ = self.community._req("/api/v1/errors", p)
        except Exception:
            return
        if code == 200:
            self.last_payload = p
            self.sent_n += len(p["errors"])
            sent(p["errors"])
