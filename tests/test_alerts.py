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
    app.snaps = [_snap(t[0] - 50 + i * 5, 20, loss=6) for i in range(10)]
    a.tick()
    assert shown[-1] == ("Packet loss at 6%", False)
    app.snaps.append(_snap(t[0], 20, restarts=1))
    a.tick()
    assert shown[-1][0] == "The server you're on just restarted"


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
