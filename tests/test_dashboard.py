import json
import shutil
import urllib.request

from conftest import FIX


def _call(url, token, path, body=None):
    req = urllib.request.Request(url + path.lstrip("/"), data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-Token": token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def test_dashboard_end_to_end(tmp_path, monkeypatch):
    game = tmp_path / "LIVE"
    shutil.copytree(FIX / "game", game)
    shutil.copy2(FIX / "wikelo_sample.log", game / "Game.log")
    (game / "logbackups").mkdir()
    from scstatus import app as appmod, config, dashboard, issues, report
    monkeypatch.setattr(report, "DATA", tmp_path / "data")
    monkeypatch.setattr(config, "DATA", tmp_path / "data")
    monkeypatch.setattr(appmod, "DATA", tmp_path / "data")
    monkeypatch.setattr(issues, "DATA", tmp_path / "data")
    monkeypatch.setattr(issues, "LIBRARY", FIX / "mini_issues.json")
    cfg = dict(config.DEFAULT_CONFIG, game_dir=str(game), dashboard_port=8899, open_browser=False)
    app = appmod.App(cfg)
    app.start(overlay=False)
    server, url = dashboard.start_server(app)
    try:
        html = urllib.request.urlopen(url).read().decode()
        token = html.split('const TOKEN = "')[1].split('"')[0]
        # Wrong token is refused
        try:
            _call(url, "nope", "/api/now")
            raise AssertionError("bad token accepted")
        except urllib.error.HTTPError as e:
            assert e.code == 403
        now = _call(url, token, "/api/now")
        assert now["session"]["build"] == "12913470" and [c["name"] for c in now["contracts"]] == ["Very Hungry", "Wikelo Arrive to System [10 Rep]"]
        assert now["health"]["score"] is None and now["user_cfg"]["has_displayinfo"] is False
        res = _call(url, token, "/api/diagnose", {"minutes": 100000})
        assert res["findings"][0]["title"] == '"Very Hungry": deliveries never counted'
        d = _call(url, token, "/api/report", {"group": "findings", "i": 0})
        assert d["url"].startswith("https://issue-council.robertsspaceindustries.com")
        rv = _call(url, token, "/api/review", {"i": 0, "save": True})
        assert rv["saved"] and _call(url, token, "/api/reviews")[0]["id"] == rv["ticket"]
        b = _call(url, token, "/api/bundle", {"group": "findings", "i": 0})
        assert (tmp_path / "data" / "reports").exists() and "Game.log" in [p.name for p in
                                                                          __import__("pathlib").Path(b["folder"]).iterdir()]
        msg = _call(url, token, "/api/usercfg", {"name": "r_displayinfo"})
        assert "r_displayinfo = 3" in (game / "USER.cfg").read_text() and msg["user_cfg"]["has_displayinfo"]
        msg = _call(url, token, "/api/usercfg", {"name": "r_DisplaySessionInfo"})
        assert msg["user_cfg"]["has_sessioninfo"] and "r_displayinfo = 3" in (game / "USER.cfg").read_text()
        msg = _call(url, token, "/api/usercfg", {"name": "r_DisplaySessionInfo", "on": False})
        assert msg["user_cfg"]["has_sessioninfo"] is False
        try:
            _call(url, token, "/api/usercfg", {"name": "sys_maxfps"})
            raise AssertionError("arbitrary setting accepted")
        except urllib.error.HTTPError as e:
            assert e.code == 400
        for p in ("/api/history", "/api/pc", "/api/issues", "/api/about"):
            assert _call(url, token, p) is not None
        # First-run questions: asked until every one is answered, then applied in one go
        assert now["setup_needed"] is True
        try:
            _call(url, token, "/api/setup", {"choices": {"game": "ok", "live": True}})
            raise AssertionError("half-answered set-up accepted")
        except urllib.error.HTTPError as e:
            assert e.code == 400
        r = _call(url, token, "/api/setup", {"choices": {"game": "ok", "displayinfo": True, "sessioninfo": False,
                                                          "live": False, "screenshots": False, "board": False,
                                                          "share": False, "updates": False, "library": False,
                                                          "alerts": False}})
        st = r["settings"]
        assert st["live"] is False and st["screenshots"] is False and st["share"] is False and st["board"] is False
        cfgtxt = (game / "USER.cfg").read_text()
        assert "r_displayinfo = 3" in cfgtxt and "r_DisplaySessionInfo = 0" in cfgtxt
        now = _call(url, token, "/api/now")
        assert now["setup_needed"] is False and now["setup_ask"] == []
        assert r["settings"]["updates"] is False and now["update"]["current"] == config.VERSION
        # Someone who answered the first set of questions is asked only the ones added since
        app.cfg["setup_version"] = 1
        assert _call(url, token, "/api/now")["setup_ask"] == ["updates", "library", "alerts"]
        r = _call(url, token, "/api/setup", {"choices": {"updates": False, "library": False, "alerts": "quiet"}})
        assert r["settings"]["alerts"]["mode"] == "quiet"
        assert _call(url, token, "/api/now")["setup_needed"] is False
        # What's shared changed in 1.2, so people already sharing are asked again; others aren't
        app.cfg.update(setup_version=2, share_readings=True, share_text_seen=None)
        assert _call(url, token, "/api/now")["setup_ask"] == ["share"]
        assert _call(url, token, "/api/now")["setup_needed"] is True
        app.cfg.update(share_readings=False)
        assert _call(url, token, "/api/now")["setup_ask"] == [] and not _call(url, token, "/api/now")["setup_needed"]
    finally:
        app.stop.set()
        server.shutdown()


def test_set_game_dir_accepts_close_enough_paths(tmp_path, monkeypatch):
    from scstatus import app as appmod, config
    monkeypatch.setattr(config, "DATA", tmp_path / "data")
    (tmp_path / "data").mkdir()
    live = tmp_path / "RSI" / "StarCitizen" / "LIVE"
    (live / "Bin64").mkdir(parents=True)
    (live / "Game.log").write_text("x")
    app = appmod.App.__new__(appmod.App)
    app.cfg, app.game_dir, app.shots, app._names = {"game_dir": ""}, tmp_path, None, None
    app.tail = type("T", (), {"path": None, "ident": None})()
    app.import_backups = lambda: None
    for given in (live, live / "Bin64", live / "Game.log", tmp_path / "RSI", tmp_path / "RSI" / "StarCitizen"):
        app.set_game_dir(str(given))
        assert app.cfg["game_dir"] == str(live)
    try:
        app.set_game_dir(str(tmp_path / "nowhere"))
        raise AssertionError("bad folder accepted")
    except ValueError:
        pass
    assert '"game_dir"' in (tmp_path / "data" / "config.json").read_text()
