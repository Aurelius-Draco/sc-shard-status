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
    finally:
        app.stop.set()
        server.shutdown()
