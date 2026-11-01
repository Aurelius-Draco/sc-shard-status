"""1.4.1: the Unplayable alarm (server under 5 fps), as the design's card edge sets out, with the log check run straight away."""
from pathlib import Path

from scstatus import alerts, score
from test_alerts import _make, _snap

PAGE = (Path(__file__).resolve().parent.parent / "scstatus" / "static" / "index.html").read_text(encoding="utf-8")


def test_unplayable_needs_a_minute_under_5_fps_not_one_misread():
    now = 10_000.0
    ok = [_snap(now - 300 + i * 5, 20) for i in range(56)] + [_snap(now - 5, 3)]
    assert score.assess(ok, now=now)["unplayable"] is False          # one low reading is a misread
    low = [_snap(now - 300 + i * 5, 20) for i in range(48)] + [_snap(now - 50 + i * 5, 4.1) for i in range(10)]
    a = score.assess(low, now=now)
    assert a["unplayable"] is True and a["server_fps_now"] == 4.1
    assert score.assess([_snap(now - 50 + i * 5, 5.2) for i in range(10)], now=now)["unplayable"] is False


def test_the_log_check_runs_straight_away_even_with_popups_off(monkeypatch):
    app, a, shown, t = _make(mode=None)
    app.game_found = True
    app.game_dir = Path("/nowhere")
    app.library = app.names = None
    calls = []

    def fake(*args, **kw):
        calls.append(kw["now"])
        return {"findings": [{"title": "Server running very slowly", "kind": "problem"},
                             {"title": "Inventory failed to load", "kind": "problem", "severity": "high"},
                             {"title": "Some info", "kind": "info"}]}
    import scstatus.diagnose
    monkeypatch.setattr(scstatus.diagnose, "diagnose", fake)
    app.snaps = [_snap(t[0] - 50 + i * 5, 4) for i in range(10)]
    u = a.watch_unplayable(now=t[0])
    assert u["checked"] == t[0] and [f["title"] for f in u["findings"]] == ["Inventory failed to load"]
    a.watch_unplayable(now=t[0] + 30)
    assert len(calls) == 1                                    # not again until 3 minutes have passed
    app.snaps += [_snap(t[0] + alerts.PROBLEM_EVERY_S - 50 + i * 5, 4) for i in range(10)]
    a.watch_unplayable(now=t[0] + alerts.PROBLEM_EVERY_S)
    assert len(calls) == 2 and not shown                      # no pop-up of its own
    app.snaps = [_snap(t[0] + 200 + i * 5, 20) for i in range(10)]
    assert a.watch_unplayable(now=t[0] + 250) is None and a.unplayable is None    # cleared once it recovers


def test_now_tab_uses_the_crash_alarm_for_unplayable():
    js = PAGE.split("async function renderNow()")[1].split("\n}\n")[0]
    assert 'crash || unp ? "alarm"' in js and 'crash || unp ? `<div class="hazard"' in js
    assert '"Unplayable"' in js and "fps, under 5" in js
    assert "found nothing on your side, so it's the server." in js


def test_reduced_motion_stops_the_invite_pip_and_the_slides():
    assert ".hreg *, .sgshare * { animation: none !important; } .dial circle, .hbar i { transition: none !important; }" in PAGE
