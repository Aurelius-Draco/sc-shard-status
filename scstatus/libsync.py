"""Keeping the known-issues library current, and the review queue.

Library: when library_updates is on, a minute and a half after start and every 6 hours after that the app fetches
the library from the community site (verseshards.com/library/issues.json). A newer, valid copy is saved as
issues.json in the data folder and used straight away. Nothing is sent about you; it's a plain download.

Review queue: an unrecognised error the player chooses to send ("Send for review") goes to the site with names and
numbers already replaced by placeholders. The app asks after its own tickets at the same times and shows the answer.
"""

import json
import re
import threading
import time
import urllib.request

from .config import DATA, VERSION, say

FIRST_S = 90
EVERY_S = 6 * 3600
VER_RX = re.compile(r"(\d{4}-\d\d-\d\d)(?:\.(\d+))?$")


def lib_version(v):
    m = VER_RX.fullmatch(v or "")
    return (m.group(1), int(m.group(2) or 0)) if m else None


def _app_version(v):
    return tuple(int(x) for x in re.findall(r"\d+", v or "")[:3]) or (0,)


def check_library(data, current_version, app_version=VERSION):
    """Is this downloaded library safe to use, and newer than ours? Returns (ok, reason)."""
    if not isinstance(data, dict) or not isinstance(data.get("rules"), list):
        return False, "not a library file"
    new, cur = lib_version(data.get("version")), lib_version(current_version)
    if not new:
        return False, "no version on it"
    if cur and new <= cur:
        return False, "already up to date"
    if _app_version(data.get("min_app")) > _app_version(app_version):
        return False, f"needs app version {data.get('min_app')} or newer"
    rules = [r for r in data["rules"] if isinstance(r, dict) and r.get("id")]
    if len(rules) < 20:
        return False, "too few entries"
    bad = 0
    for r in rules:
        m = r.get("match") or {}
        try:
            if isinstance(m, dict) and m.get("regex"):
                re.compile(m["regex"])
        except re.error:
            bad += 1
    if bad > len(rules) // 10:
        return False, "too many broken entries"
    return True, "ok"


class LibrarySync:
    def __init__(self, app, url, version=VERSION):
        self.app, self.url, self.version = app, (url or "").rstrip("/"), version
        self.checked_at = None
        self.updated_at = None
        self.error = None
        self.note = None
        self.lock = threading.Lock()

    def _get(self, path, timeout=20):
        req = urllib.request.Request(self.url + path, headers={"user-agent": f"SCShardStatus/{self.version}",
                                                               "cache-control": "no-cache"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))

    def _post(self, path, body, timeout=15):
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode(), headers={
            "content-type": "application/json", "user-agent": f"SCShardStatus/{self.version}"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode() or "{}")
            except Exception:
                return e.code, {}

    def run(self, stop):
        if stop.wait(FIRST_S):
            return
        while not stop.is_set():
            self.tick()
            if stop.wait(EVERY_S):
                return

    def tick(self):
        if self.app.cfg.get("library_updates") and self.url:
            self.update_library()
        if self.url:
            self.check_tickets()

    # -- library
    def update_library(self):
        from .issues import Library
        with self.lock:
            self.checked_at = time.time()
            try:
                data = self._get("/library/issues.json")
            except Exception as e:
                self.error = f"Couldn't reach the community site ({e.__class__.__name__})"
                return self.info()
            ok, why = check_library(data, self.app.library.version)
            self.error = None
            if not ok:
                self.note = None if why == "already up to date" else f"Skipped a library download: {why}."
                return self.info()
            path = DATA / "issues.json"
            tmp = DATA / "issues.json.new"
            try:
                DATA.mkdir(parents=True, exist_ok=True)
                tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
                lib = Library(path=tmp)
                if len(lib.rules) < 20:
                    raise ValueError("it didn't load properly")
                tmp.replace(path)
            except Exception as e:
                self.error = f"Couldn't save the new library ({e})"
                return self.info()
            old = self.app.library.version
            self.app.library = Library()
            self.updated_at = time.time()
            self.note = f"Known-issues library updated from {old} to {self.app.library.version}."
            say(self.note)
        return self.info()

    def info(self):
        return {"enabled": bool(self.app.cfg.get("library_updates")), "version": self.app.library.version,
                "checked_at": self.checked_at, "updated_at": self.updated_at, "error": self.error, "note": self.note}

    # -- review queue
    def send_review(self, rid, payload):
        code, d = self._post("/api/v1/review", payload)
        if code != 200 or not d.get("ok"):
            raise ValueError(d.get("error") or f"the site answered {code}")
        self.app.store.set_review_status(rid, "sent")
        if d.get("status") and d["status"] != "new":
            self.app.store.set_review_answer(rid, d["status"], d.get("answer"), None)
        return d

    def check_tickets(self):
        open_ = [r["id"] for r in self.app.store.reviews() if r["status"] == "sent" and not r.get("answer_status")]
        if not open_:
            return 0
        install = self.app.store.install_id()
        try:
            d = self._get(f"/api/v1/review?install={install}&t={','.join(open_[:50])}")
        except Exception:
            return 0
        n = 0
        for t in d.get("tickets", []):
            if t.get("status") and t["status"] != "new":
                self.app.store.set_review_answer(t["ticket"], t["status"], t.get("answer"), t.get("rule_id"))
                n += 1
        if n:
            say(f"{n} of your reviews {'has' if n == 1 else 'have'} an answer. See What's gone wrong?")
        return n
