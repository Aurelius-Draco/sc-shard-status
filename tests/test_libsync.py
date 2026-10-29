import copy
import json
import threading

from scstatus import libsync
from scstatus.config import LIBRARY


def _lib(version, **kw):
    d = json.loads(LIBRARY.read_text(encoding="utf-8"))
    d["version"] = version
    d.update(kw)
    return d


def test_library_checks():
    cur = json.loads(LIBRARY.read_text(encoding="utf-8"))["version"]
    assert libsync.check_library(_lib("2099-01-01.1"), cur) == (True, "ok")
    assert libsync.check_library(_lib(cur), cur)[1] == "already up to date"
    assert libsync.check_library(_lib("2099-01-01", min_app="99.0"), cur)[0] is False
    assert libsync.check_library({"version": "2099-01-01", "rules": []}, cur)[1] == "too few entries"
    broken = _lib("2099-01-01")
    for r in broken["rules"]:
        r["match"] = {"regex": "(unclosed"}
    assert libsync.check_library(broken, cur)[1] == "too many broken entries"
    assert libsync.check_library([], cur)[0] is False


class _Store:
    def __init__(self):
        self.rows, self.answers = {}, {}

    def install_id(self):
        return "0123456789abcdef"

    def set_review_status(self, rid, st):
        self.rows[rid] = st

    def set_review_answer(self, rid, status, answer, rule):
        self.answers[rid] = (status, answer, rule)

    def reviews(self):
        return [{"id": k, "status": v, "answer_status": self.answers.get(k, (None,))[0]} for k, v in self.rows.items()]


class _App:
    def __init__(self):
        from scstatus.issues import Library
        self.cfg = {"library_updates": True}
        self.library = Library()
        self.store = _Store()


def test_newer_library_is_saved_and_used(tmp_path, monkeypatch):
    monkeypatch.setattr(libsync, "DATA", tmp_path)
    from scstatus import issues
    monkeypatch.setattr(issues, "DATA", tmp_path)
    app = _App()
    s = libsync.LibrarySync(app, "http://site.invalid")
    newer = _lib("2099-01-01.3")
    monkeypatch.setattr(s, "_get", lambda path, timeout=20: copy.deepcopy(newer))
    info = s.update_library()
    assert info["version"] == "2099-01-01.3" and "updated" in info["note"] and (tmp_path / "issues.json").exists()
    # The same again: nothing to do
    info = s.update_library()
    assert info["note"] is None and info["error"] is None


def test_review_tickets_pick_up_answers(monkeypatch):
    app = _App()
    s = libsync.LibrarySync(app, "http://site.invalid")
    monkeypatch.setattr(s, "_post", lambda path, body, timeout=15: (200, {"ok": True, "ticket": body["ticket"], "status": "new"}))
    s.send_review("abc1234567", {"ticket": "abc1234567"})
    assert app.store.rows == {"abc1234567": "sent"}
    asked = []
    monkeypatch.setattr(s, "_get", lambda path, timeout=20: asked.append(path) or {"tickets": [
        {"ticket": "abc1234567", "status": "harmless", "answer": "Just noise.", "rule_id": None}]})
    assert s.check_tickets() == 1
    assert app.store.answers["abc1234567"] == ("harmless", "Just noise.", None)
    assert "install=0123456789abcdef" in asked[0] and "t=abc1234567" in asked[0]
    assert s.check_tickets() == 0          # answered tickets aren't asked about again
