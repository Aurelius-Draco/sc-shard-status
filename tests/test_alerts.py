import threading

from scstatus import alerts


class _Sess:
    def __init__(self):
        self.disconnects = []


class _App:
    def __init__(self, mode="sound"):
        self.cfg = {"alerts": mode}
        self.lock = threading.RLock()
        self.snaps = []
        self.session = _Sess()
        self.game_found = False


def _snap(ts, fps, loss=0.0, restarts=0, name="pub-x-game-07"):
    return {"ts": ts, "ok": True, "server_fps": fps, "loss_pct": loss, "restarts": restarts, "server_name": name}


def _make(mode="sound"):
    shown = []
    t = [10_000.0]
    app = _App(mode)
    a = alerts.Alerts(app, notify=lambda title, body, tag, sound: shown.append((title, sound)), clock=lambda: t[0])
    a.problem_at = 1e12            # leave the log check out of these
    return app, a, shown, t


def test_fps_cliff_alerts_once_per_10_minutes():
    app, a, shown, t = _make()
    app.snaps = [_snap(t[0] - 300 + i * 5, 20) for i in range(48)] + [_snap(t[0] - 50 + i * 5, 4) for i in range(10)]
    a.tick()
    assert shown and shown[0][0].startswith("Server fps down to 4 (was 20)") and shown[0][1] is True
    a.tick()
    assert len(shown) == 1                           # not again straight away
    t[0] += 601
    app.snaps = [_snap(t[0] - 300 + i * 5, 20) for i in range(48)] + [_snap(t[0] - 50 + i * 5, 4) for i in range(10)]
    a.tick()
    assert len(shown) == 2


def test_a_steady_slow_server_isnt_news_but_loss_and_restarts_are():
    app, a, shown, t = _make("quiet")
    app.snaps = [_snap(t[0] - 300 + i * 5, 5) for i in range(60)]
    a.tick()
    assert shown == []                               # slow all along: the score says so, no pop-up
    app.snaps = [_snap(t[0] - 58 + i * 5, 20, loss=6) for i in range(12)]
    a.tick()
    assert shown[-1] == ("Packet loss at 6%", False)
    # A single misread restart count (or a lone 9.0% loss) is ignored; a count that holds is a real restart
    n = len(shown)
    app.snaps.append(_snap(t[0] - 1, 20, restarts=10))
    app.snaps.append(_snap(t[0] - 0.5, 20, restarts=0))
    a.tick()
    assert len(shown) == n
    app.snaps += [_snap(t[0] + i, 20, restarts=1) for i in range(5)]
    a.tick()
    assert shown[-1][0] == "The server you're on just restarted"


def test_an_already_slow_server_dropping_to_almost_nothing_alerts():
    app, a, shown, t = _make("quiet")
    app.snaps = [_snap(t[0] - 300 + i * 5, 9) for i in range(48)] + [_snap(t[0] - 55 + i * 5, 3.5) for i in range(12)]
    a.tick()
    assert shown and shown[-1][0].startswith("Server fps down to 4") and "(was 9)" in shown[-1][0]


def test_bad_disconnect_alerts_normal_one_doesnt():
    app, a, shown, t = _make()
    a.tick()                                         # first look just counts what's there
    app.session.disconnects.append({"cause": 30010, "reason": "Quit"})
    a.tick()
    assert shown == []
    app.session.disconnects.append({"cause": 30007, "reason": "Server crashed"})
    a.tick()
    assert shown[-1][0] == "Disconnected (error 30007)"


def test_off_means_off():
    app, a, shown, t = _make(None)
    assert a.mode is None


def test_an_old_crash_isnt_alerted_when_the_app_starts(monkeypatch):
    app, a, shown, t = _make()
    app.game_found = True
    app.game_dir = __import__("pathlib").Path("/nonexistent")
    app.library = app.names = None
    old = {"title": "The game crashed", "area": "Game", "kind": "problem", "severity": "high", "rule_id": "crash-x",
           "first_ts": t[0] - 7200, "last_ts": t[0] - 7200, "explain": ""}
    new = dict(old, rule_id="crash-y", title="Contract stuck", first_ts=t[0] - 60, last_ts=t[0] - 60)
    import scstatus.diagnose as d
    monkeypatch.setattr(d, "diagnose", lambda *a, **k: {"findings": [old, new]})
    a._problems(t[0])
    assert [s[0] for s in shown] == ["Contract stuck"]
