"""1.5.2: what you type into a moment is saved with the mark as you type it (8 Nov: five notes were lost), kept a
month when it has a note, and never sent anywhere unless you press Send."""
import json
import time
import types

from scstatus import app as app_mod


class _Store:
    def __init__(self):
        self.m = {}

    def meta(self, k, d=None):
        return self.m.get(k, d)

    def set_meta(self, k, v):
        self.m[k] = v


def _app():
    a = types.SimpleNamespace(store=_Store())
    for n in ("marks", "marks_shown", "mark_note", "_kept_marks", "_save_marks"):
        setattr(a, n, types.MethodType(getattr(app_mod.App, n), a))
    for n in ("MARK_KEEP_S", "MARK_NOTE_KEEP_S", "MARK_NOTE_MAX"):
        setattr(a, n, getattr(app_mod.App, n))
    return a


def test_a_note_is_saved_with_its_mark_and_kept_a_month():
    a = _app()
    now = time.time()
    a.store.set_meta("marks", json.dumps([{"ts": now - 3 * 86400, "source": "button"}, {"ts": now - 60, "source": "button"},
                                          {"ts": now - 5 * 3600, "source": "hotkey"}]))
    a.mark_note(now - 60, "  Idea:   a reputation   tracker  ")
    rows = a.marks(a.MARK_NOTE_KEEP_S)
    assert [r.get("what") for r in rows if r.get("what")] == ["Idea: a reputation tracker"]
    a._save_marks(a._kept_marks())
    kept = a.marks(a.MARK_NOTE_KEEP_S)
    assert len(kept) == 2                          # the 3 day old mark with no note went; the 5 hour old one stayed
    shown = a.marks_shown()
    assert [r["ts"] for r in shown] == [now - 60]  # older than 4 hours and no note: not on the list


def test_an_old_note_still_shows_and_clearing_it_removes_it():
    a = _app()
    old = time.time() - 10 * 86400
    a.store.set_meta("marks", json.dumps([{"ts": old, "source": "button", "what": "Blueprint list idea"}]))
    assert a.marks_shown()[0]["what"] == "Blueprint list idea"
    a.mark_note(old, "")
    assert "what" not in a.marks(a.MARK_NOTE_KEEP_S)[0]


def test_note_for_a_mark_that_is_gone():
    a = _app()
    a.store.set_meta("marks", "[]")
    try:
        a.mark_note(time.time(), "x")
        raise AssertionError("expected an error")
    except ValueError as e:
        assert "isn't there" in str(e)
    assert len(a.mark_note.__doc__) > 10


def test_notes_are_capped():
    a = _app()
    t = time.time()
    a.store.set_meta("marks", json.dumps([{"ts": t}]))
    assert len(a.mark_note(t, "x" * 500)["what"]) == 200
