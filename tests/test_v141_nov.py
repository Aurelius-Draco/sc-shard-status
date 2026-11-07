"""1.4.1, the November round: patrolling reports, reporting pirates somewhere else, the Issue Council link with how it
relates, Mark this moment start to finish, Bad's constant breath, and 30028 counting as a normal disconnect."""
import json
import os
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from conftest import FIX
from scstatus import alerts, community, config, groups, locations, screenshots
from scstatus.logparse import NORMAL_CAUSES, Session, parse_line
from test_v13 import _App, _Comm

PAGE = (Path(__file__).resolve().parent.parent / "scstatus" / "static" / "index.html").read_text(encoding="utf-8")
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


# ---------------------------------------------------------------- places and pirate reports
def test_places_only_from_systems_on_your_shard():
    sp = {"stanton", "pyro"}
    assert [p["name"] for p in locations.suggest_places("yel", sp)][0] == "Yela"
    assert locations.suggest_places("cr", sp)[0]["name"] == "Crusader"            # the planet before its L-points
    assert len(locations.suggest_places("", sp)) == 7
    names = [p["name"] for p in locations.suggest_places("jump", sp, limit=20)]
    assert "Stanton - Pyro jump point" in names and not any("Nyx" in n for n in names)
    assert locations.find_place("checkmate", sp) == {"name": "Checkmate", "type": "contested zone, Pyro", "area": "pyro2", "system": "pyro"}
    assert locations.find_place("Checkmate", {"stanton"}) is None                   # Pyro isn't on that shard
    assert locations.find_place("Somewhere made up", sp) is None
    assert locations.find_place("CRU-L4", sp)["area"] == "crusader"
    assert all(set(p) == {"name", "type", "area", "system"} for p in locations.report_places())


def test_patrolling_and_somewhere_else_reports():
    app, comm = _App(), _Comm()
    g = groups.Groups(app, comm)
    msg = g.post("pirate", report_kind="patrol", place="Yela")
    path, body = comm.sent[-1]
    assert path == "/api/v1/posts" and body["report_kind"] == "patrol" and body["elsewhere"] is True
    assert body["area"] == "crusader" and body["area_name"] == "Crusader" and body["system"] == "stanton" and body["server"] is None
    assert body["shard_id"] == "pub_apse2b_9945425_090" and "handle" not in body and "note" not in body
    assert "Yela" not in json.dumps(body)                   # area only: the place picked never goes
    assert msg.startswith("Patrolling noted near Crusader.") and g.last_area_name == "Crusader"
    # Reported here, as a sighting: your area and server, as before
    g.post("pirate")
    body = comm.sent[-1][1]
    assert body["report_kind"] == "seen" and body["area"] == "hurston" and body["server"] == "37" and "elsewhere" not in body
    # The same area again replaces your earlier report
    g.post("pirate", report_kind="seen", place="Yela")
    rows = [r for r in g._keys() if r["kind"] == "pirate"]
    assert [(r["area_name"], r["report_kind"]) for r in rows] == [("Hurston", "seen"), ("Crusader", "seen")]
    with pytest.raises(ValueError, match="Pick a place from the list"):
        g.post("pirate", place="Nowhere Station")
    with pytest.raises(ValueError, match="Pick a place"):
        g.post("pirate", place="Nyx I")                      # Nyx isn't on this shard


def test_pirates_here_says_patrolling_and_shows_your_reports_elsewhere():
    app, comm = _App(), _Comm()
    g = groups.Groups(app, comm)
    g.post("pirate", report_kind="patrol", place="Daymar")
    comm.posts = {"open": True, "pirates": [{"shard_id": "pub_apse2b_9945425_090", "area": "hurston", "area_name": "Hurston",
                                             "kind": "patrol", "reporters": 2, "expires": time.time() + 900}]}
    p = g.pirates_here()
    assert p["here"]["kind"] == "patrol" and p["here"]["reporters"] == 2
    assert [(y["area_name"], y["kind"]) for y in p["yours"]] == [("Crusader", "patrol")]
    comm.posts["pirates"][0].pop("kind")                    # an older site doesn't say: a sighting
    assert g.pirates_here()["here"]["kind"] == "seen"
    assert [x["name"] for x in g.places("day")][0] == "Daymar"


def test_somewhere_else_sends_the_area_never_the_place():
    """Every place in the list, in every system: the body sent names the area, never the place picked."""
    app, comm = _App(), _Comm()
    g = groups.Groups(app, comm)
    g.shard_systems = lambda: {"stanton", "pyro", "nyx"}
    for name in {p["name"] for p in locations.report_places()}:
        p = locations.find_place(name, {"stanton", "pyro", "nyx"})   # a name used twice goes to the first match
        area_name = locations.AREAS[p["area"]][1]
        g.post("pirate", place=name)
        body = comm.sent[-1][1]
        assert body["area"] == p["area"] and body["area_name"] == area_name, name
        if name not in area_name:                           # a planet's own name is the area's name
            assert name not in json.dumps(body), name


# ---------------------------------------------------------------- Issue Council link
def test_issue_council_link_says_how_it_relates():
    sent = []
    c = community.Community(type("A", (), {"cfg": {}, "store": _App().store})(), "http://127.0.0.1:9", "1.4.1")
    c._req = lambda path, body=None: (sent.append((path, body)) or (200, {"ok": True, "message": "Added. Thanks!"}))
    url = "https://issue-council.robertsspaceindustries.com/projects/STAR-CITIZEN/issues/STARC-151999"
    r = c.add_ic_link("freight-entity-not-present", url, "dup", "STARC-148213")
    assert sent[-1] == ("/api/v1/issue/freight-entity-not-present/link",
                        {"voter": "0123456789abcdef", "url": url, "relation": "dup", "to": "STARC-148213"})
    assert r["message"] == "STARC-151999 is on the issue page as a duplicate of STARC-148213."
    r = c.add_ic_link("freight-entity-not-present", url, "linked", url.replace("151999", "100"))
    assert sent[-1][1]["to"] == "STARC-100" and r["message"].endswith("linked to STARC-100.")
    assert c.add_ic_link("freight-entity-not-present", url)["message"].endswith("as a new report.")
    for bad in ("https://evil.example/projects/STAR-CITIZEN/issues/STARC-1", "http://issue-council.robertsspaceindustries.com/projects/STAR-CITIZEN/issues/STARC-1",
                "https://robertsspaceindustries.com/spectrum/x"):
        with pytest.raises(ValueError, match="Only Issue Council links"):
            c.add_ic_link("freight-entity-not-present", bad)
    with pytest.raises(ValueError, match="Pick the report"):
        c.add_ic_link("freight-entity-not-present", url, "same", "")
    with pytest.raises(ValueError, match="isn't on the community board"):
        c.add_ic_link("../admin", url)


def test_moment_review_sends_only_the_description_and_issue_ids():
    sent = []
    c = community.Community(type("A", (), {"cfg": {}, "store": _App().store})(), "http://127.0.0.1:9", "1.4.1")
    c._req = lambda path, body=None: (sent.append((path, body)) or (200, {"ok": True, "matched": [{"id": "x", "title": "X"}]}))
    out = c.send_moment(1793500000.4, "12913470", "pub_apse2b_9945425_090", "  Elevator   ate my\ncargo " + "x" * 300, ["freight-x", "../bad", 5])
    path, body = sent[-1]
    assert path == "/api/v1/moment" and set(body) == {"install", "ts", "build", "shard_id", "what", "issues"}
    assert body["what"].startswith("Elevator ate my cargo x") and len(body["what"]) == 200 and body["issues"] == ["freight-x"]
    assert out["matched"][0]["title"] == "X"


# ---------------------------------------------------------------- screenshots
def test_screenshot_paths_stay_inside_the_folder(tmp_path):
    shots = tmp_path / "screenshots"
    shots.mkdir()
    (shots / "ScreenShot-2026-11-01_09-56-40-1A2.jpg").write_bytes(PNG)
    (tmp_path / "secret.png").write_bytes(PNG)
    assert screenshots.shot_path(shots, "ScreenShot-2026-11-01_09-56-40-1A2.jpg")
    for bad in ("../secret.png", "..\\secret.png", "/etc/passwd", "secret.png", "", None, "notes.txt", "a/b.jpg"):
        assert screenshots.shot_path(shots, bad) is None, bad
    got = screenshots.thumbnail(shots, "ScreenShot-2026-11-01_09-56-40-1A2.jpg")
    assert got and got[0]                                       # not a real picture: the file itself comes back
    now = time.time()
    os.utime(shots / "ScreenShot-2026-11-01_09-56-40-1A2.jpg", (now - 3000, now - 3000))
    (shots / "new.png").write_bytes(PNG)
    assert [x["name"] for x in screenshots.list_shots(shots, now - 600, now + 60)] == ["new.png"]


# ---------------------------------------------------------------- 30028
def test_kicked_for_being_idle_is_a_normal_disconnect():
    assert 30028 in NORMAL_CAUSES
    s = Session()
    s.add(parse_line('<2026-10-29T01:20:00.000Z> [Notice] <Channel Disconnected> cause=30028 reason="Remote Disconnect - player inactive" '
                     'frame=1 isRemote=1 viewState=eCVS_InGame map="megamap" [Team_Network][Network]'))
    assert s.disconnects and s.summary()["bad_disconnects"] == 0
    lib = json.loads((Path(config.__file__).parent / "library" / "issues.json").read_text(encoding="utf-8"))
    r = next(x for x in lib["rules"] if x["id"] == "disconnect-30028")
    assert r["kind"] == "info" and r["title"] == "Kicked for being idle"
    # No pop-up for it either
    app = type("A", (), {"cfg": {"alerts": "quiet"}, "session": s})()
    shown = []
    a = alerts.Alerts(app, notify=lambda *x, **k: shown.append(x))
    a.disc_seen = 0
    a._disconnects()
    assert not shown


def test_version_is_1_5_0():
    assert config.VERSION == "1.5.0"


# ---------------------------------------------------------------- the page
def test_page_has_the_november_designs():
    assert ".hud.beacon { animation: hudBad 2s ease-in-out infinite; }" in PAGE
    assert ".sevl.high .tlights i:nth-child(1) { animation: critGlow 2.4s ease-in-out infinite; }" in PAGE
    for k in ("patrolSweep", "patrolIn", "markPing", "pipPop", "nvRise", "barGrow", "toastIn"):
        assert f"@keyframes {k}" in PAGE, k
    assert "Somewhere else, or patrolling" in PAGE and "Report patrolling" in PAGE
    assert "Take screenshots now if you can." in PAGE and "I took screenshots" in PAGE and "I didn't" in PAGE
    assert "After you post" in PAGE and "Add to Verse Shards" in PAGE
    assert '$("markBtn").onclick = () => openMoment();' in PAGE
    assert "SIM SHIM" not in PAGE and "fakeShots" not in PAGE and "localStorage.getItem(\"nvReports\")" not in PAGE
    # Unplayable keeps the crash alarm
    assert 'crash || unp ? "alarm"' in PAGE
    # Everything new stops for reduced motion
    assert ".nv-shot i, .hud.beacon, .sevl.high .tlights i { animation: none !important; }" in PAGE


# ---------------------------------------------------------------- the local API, end to end
def _call(url, token, path, body=None):
    req = urllib.request.Request(url + path.lstrip("/"), data=None if body is None else json.dumps(body).encode(),
                                 headers={"X-Token": token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read()
        return json.loads(raw) if r.headers.get_content_type() == "application/json" else raw


def test_moment_screenshots_review_draft_link_and_places(tmp_path, monkeypatch):
    game = tmp_path / "LIVE"
    shutil.copytree(FIX / "game", game)
    shutil.copy2(FIX / "wikelo_sample.log", game / "Game.log")
    (game / "logbackups").mkdir()
    from scstatus import app as appmod, dashboard, issues, report
    for mod in (report, config, appmod, issues):
        monkeypatch.setattr(mod, "DATA", tmp_path / "data")
    monkeypatch.setattr(issues, "LIBRARY", FIX / "mini_issues.json")
    cfg = dict(config.DEFAULT_CONFIG, game_dir=str(game), dashboard_port=8893, open_browser=False, community_board=False)
    app = appmod.App(cfg)
    app.start(overlay=False)
    sent = []

    def req(path, body=None):
        sent.append((path, body))
        if path == "/api/v1/moment":
            return 200, {"ok": True, "matched": []}
        if path.endswith("/link"):
            return 200, {"ok": True}
        if path == "/api/v1/posts" and body:
            return 200, {"ok": True, "id": "a1b2c3d4e5f6", "key": "f" * 32, "expires": time.time() + 2700}
        return 200, {}
    app.community._req = req
    now = time.time()
    with app.lock:
        app.snaps.append({"ts": now - 2, "ok": True, "shard_id": "pub_apse2b_9945425_090", "server_name": "pub-x-game-37",
                          "location": "Stanton2_Orison", "server_fps": 4.6, "pop_srv": 53, "ping_ms": 41})
    server, url = dashboard.start_server(app)
    try:
        token = urllib.request.urlopen(url).read().decode().split('const TOKEN = "')[1].split('"')[0]
        ts = _call(url, token, "/api/mark", {})["mark"]["ts"]
        shots = game / "screenshots"
        shots.mkdir(exist_ok=True)
        for name, age in (("ScreenShot-a.jpg", 30), ("ScreenShot-b.jpg", 200), ("ScreenShot-old.jpg", 4000)):
            (shots / name).write_bytes(PNG)
            os.utime(shots / name, (now - age, now - age))
        assert [s["name"] for s in _call(url, token, f"/api/moment?part=shots&ts={ts}")["shots"]] == ["ScreenShot-a.jpg", "ScreenShot-b.jpg"]
        # The picture comes with the token in the address (an <img> can't send headers), and only from that folder
        assert urllib.request.urlopen(f"{url}api/shot?name=ScreenShot-a.jpg&t={token}").read()
        for q in ("name=ScreenShot-a.jpg&t=nope", "name=..%2F..%2FGame.log&t=" + token, "name=Game.log&t=" + token):
            with pytest.raises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(f"{url}api/shot?{q}")
            assert e.value.code in (403, 404)
        m = _call(url, token, f"/api/moment?ts={ts}")
        assert m["shard_name"] == "AU-90" and m["server"] == "37" and m["readings"]["server_fps"] == 4.6
        assert m["log"][-1]["kind"] == "mark" or any(x["kind"] == "mark" for x in m["log"])
        assert m["board"] is False
        # Send for review: pressing the button is the yes, so it goes with Show other shards and sharing both off.
        # Only the time, build, shard, what was typed and issue ids. Never screenshots or log lines
        assert not app.cfg.get("community_board") and not app.cfg.get("share_readings")
        r = _call(url, token, "/api/moment/review", {"ts": ts, "what": "Elevator didn't come", "issues": ["not-in-library"]})
        assert r["message"] == "Thanks, sent."
        body = sent[-1][1]
        assert sent[-1][0] == "/api/v1/moment" and body["issues"] == [] and body["what"] == "Elevator didn't come"
        assert set(body) <= {"install", "ts", "build", "shard_id", "what", "issues", "detail", "version"}
        assert "ScreenShot" not in json.dumps(body)
        # 1.5: the detail the player was shown. The area, never the place; the server's number and fps
        assert body["detail"]["server"] == "37" and body["detail"]["fps"] == 4.6 and body["version"]
        assert "Orison" not in json.dumps(body["detail"]) and "Game.log" not in json.dumps(body)
        assert m["send"]["lines"] and any("fps" in x for x in m["send"]["lines"])
        assert "Send for review" in PAGE and "Never your screenshots or log lines" in PAGE
        # The draft: your description, and only the screenshots you picked
        d = _call(url, token, "/api/moment/draft", {"ts": ts, "what": "Elevator didn't come", "shots": ["ScreenShot-b.jpg", "../Game.log"]})
        files = sorted(p.name for p in Path(d["folder"]).iterdir())
        assert "ScreenShot-b.jpg" in files and "ScreenShot-a.jpg" not in files and "Game.log" in files
        assert d["shot_names"] == ["ScreenShot-b.jpg"]
        assert "Elevator didn't come" in (Path(d["folder"]) / "issue-council-report.txt").read_text(encoding="utf-8")
        rep = _call(url, token, "/api/report", {"group": d["group"], "i": d["i"]})
        assert "Elevator didn't come" in json.dumps(rep["sections"])
        # Old marks: a moment that wasn't marked is refused
        with pytest.raises(urllib.error.HTTPError) as e:
            _call(url, token, "/api/moment?ts=12345")
        assert e.value.code == 400
        # Issue Council link
        u = "https://issue-council.robertsspaceindustries.com/projects/STAR-CITIZEN/issues/STARC-151999"
        r = _call(url, token, "/api/issue/link", {"issue": "freight-entity-not-present", "url": u, "relation": "same", "to": "STARC-1"})
        assert r["id"] == "STARC-151999" and sent[-1][1]["relation"] == "same"
        # Places and a report for somewhere else
        assert [p["name"] for p in _call(url, token, "/api/places?q=orb")["places"]][0] == "Orbituary"
        r = _call(url, token, "/api/groups/post", {"kind": "pirate", "report_kind": "patrol", "place": "Orbituary"})
        body = sent[-1][1]
        assert body["area"] == "pyro3" and body["area_name"] == "Bloom" and body["server"] is None and body["report_kind"] == "patrol"
        assert "Orbituary" not in json.dumps(body) and r["area_name"] == "Bloom"
        # Opening a folder outside the report folders is refused
        with pytest.raises(urllib.error.HTTPError):
            _call(url, token, "/api/moment/open", {"folder": str(tmp_path)})
    finally:
        server.shutdown()
        app.stop.set()
