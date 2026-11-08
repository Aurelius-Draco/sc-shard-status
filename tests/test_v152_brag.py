"""1.5.2 brag cards: the bundled files are served from a fixed list only, and /api/brag gives the best session score
and nothing else."""
import http.client
import json
import shutil
import time
import urllib.error
import urllib.request

from conftest import FIX

from scstatus import dashboard


def _server(tmp_path, monkeypatch, port):
    game = tmp_path / "LIVE"
    shutil.copytree(FIX / "game", game)
    shutil.copy2(FIX / "wikelo_sample.log", game / "Game.log")
    (game / "logbackups").mkdir()
    from scstatus import app as appmod, config, issues, report
    for m in (report, config, appmod, issues):
        monkeypatch.setattr(m, "DATA", tmp_path / "data")
    monkeypatch.setattr(issues, "LIBRARY", FIX / "mini_issues.json")
    cfg = dict(config.DEFAULT_CONFIG, game_dir=str(game), dashboard_port=port, open_browser=False)
    app = appmod.App(cfg)
    app.start(overlay=False)
    server, url = dashboard.start_server(app)
    return app, server, url


def _raw(port, path):
    """Send the path as written (urllib would tidy up ../ before it left)."""
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("GET", path, headers={"Host": f"127.0.0.1:{port}"})
    r = c.getresponse()
    return r.status, r.getheader("Content-Type"), r.read()


def test_every_bundled_file_is_listed_and_there():
    folder = dashboard.STATIC / "brag"
    on_disk = sorted(str(p.relative_to(folder)).replace("\\", "/") for p in folder.rglob("*") if p.is_file())
    assert on_disk == sorted(dashboard.BRAG_FILES)            # nothing stray, nothing missing
    assert len([n for n in on_disk if n.endswith(".woff2")]) == 8 and len([n for n in on_disk if n.endswith(".jpg")]) == 9
    head = (folder / "html-to-image.js").read_text(encoding="utf-8")[:1500]
    assert "html-to-image 1.11.11" in head and "MIT License" in head and "Permission is hereby granted" in head
    css = (folder / "fonts.css").read_text(encoding="utf-8")
    assert css.count('url("fonts/') == 8 and "../" not in css


def test_brag_files_served_from_the_list_only(tmp_path, monkeypatch):
    port = 8893
    app, server, url = _server(tmp_path, monkeypatch, port)
    try:
        want = {"brag-card.css": "text/css", "fonts.css": "text/css", "html-to-image.js": "text/javascript",
                "img/SC_14.jpg": "image/jpeg", "img/mbtc-white.png": "image/png",
                "fonts/barlow-semi-condensed-latin-800-normal.woff2": "font/woff2"}
        for name, ctype in want.items():
            st, ct, body = _raw(port, "/brag/" + name)
            assert st == 200 and ct.split(";")[0] == ctype, name
            assert body == (dashboard.STATIC / "brag" / name).read_bytes()
        for bad in ("/brag/", "/brag/../dashboard.py", "/brag/..%2fdashboard.py", "/brag/img/../../dashboard.py",
                    "/brag/%2e%2e/index.html", "/brag/img/SC_99.jpg", "/brag/BRAG-CARD.CSS", "/brag/img",
                    "/brag/fonts", "/brag//etc/passwd", "/brag/img\\SC_14.jpg", "/brag/brag-card.css/",
                    "/brag/./brag-card.css", "/brag/index.html"):
            st, ct, body = _raw(port, bad)
            assert st == 404 and body == b"", bad
        # Still local only, like every other page
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
        c.request("GET", "/brag/brag-card.css", headers={"Host": "evil.example"})
        assert c.getresponse().status == 403
    finally:
        server.shutdown()
        app.stop.set()


def test_api_brag_needs_the_token_and_says_little(tmp_path, monkeypatch):
    port = 8894
    app, server, url = _server(tmp_path, monkeypatch, port)
    try:
        html = urllib.request.urlopen(url).read().decode()
        token = html.split('const TOKEN = "')[1].split('"')[0]
        try:
            urllib.request.urlopen(urllib.request.Request(url + "api/brag", headers={"X-Token": "nope"}), timeout=10)
            raise AssertionError("bad token accepted")
        except urllib.error.HTTPError as e:
            assert e.code == 403
        d = json.loads(urllib.request.urlopen(urllib.request.Request(url + "api/brag", headers={"X-Token": token}), timeout=10).read())
        assert set(d) == {"best"}
    finally:
        server.shutdown()
        app.stop.set()


def test_brag_best_and_week(monkeypatch):
    from scstatus import app as appmod
    now = time.time()
    cards = [
        {"id": "a", "start": now - 20 * 86400, "score": 99, "health": "good", "word": "Healthy", "day": "Mon 19 Oct", "shards": [{"shard": "AU-110", "servers": ["x"]}]},
        {"id": "b", "start": now - 3 * 86400, "score": 61, "health": "poor", "word": "Struggling", "day": "Thu 5 Nov"},
        {"id": "c", "start": now - 1 * 86400, "score": 94, "health": "good", "word": "Healthy", "day": "Sat 7 Nov"},
        {"id": "d", "start": now - 2 * 86400, "score": None, "health": "none", "word": "", "day": "Fri 6 Nov"},
        {"id": "e", "start": now - 5 * 86400, "score": 80, "health": "ok", "word": "OK", "day": "Tue 3 Nov"},
    ]
    a = appmod.App.__new__(appmod.App)
    monkeypatch.setattr(appmod.App, "sessions_cards", lambda self, page=0, per=9: {"sessions": cards})
    d = a.brag()
    assert d["best"] == {"score": 99, "health": "good", "word": "Healthy", "day": "Mon 19 Oct"}   # best of all time
    assert set(d) == {"best"} and "AU-110" not in json.dumps(d) and '"a"' not in json.dumps(d)
    monkeypatch.setattr(appmod.App, "sessions_cards", lambda self, page=0, per=9: {"sessions": []})
    assert a.brag() == {"best": None}


def test_the_build_carries_the_brag_folder():
    spec = (dashboard.STATIC.parent.parent / "installer" / "sc-shard-status.spec").read_text(encoding="utf-8")
    assert '"static"' in spec            # the whole static folder, brag/ included, goes into the PyInstaller build
