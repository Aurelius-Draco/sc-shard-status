"""1.4 (v3 design): post details and length, keen statuses, extend and decide, the groups feed on Now, the fed count,
crash state, ships retrieved and the pilot profile. Made-up handles only; nothing talks to the live site."""
import base64
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from scstatus import community, groups, profile
from scstatus.logparse import Session, parse_line, records
from test_v13 import _App, _Comm

KEY = "f" * 32


class _Comm3(_Comm):
    """A v3 site: hours on posting, statuses and the crew count on /posts/mine, extend and decide."""

    def __init__(self, old=False):
        super().__init__()
        self.old = old
        self.posts = None

    def _req(self, path, body=None):
        self.sent.append((path, body))
        if self.old and (path.endswith("/extend") or path.endswith("/decide") or path.startswith("/api/v1/fed")):
            return 404, {"ok": False, "error": "not found"}
        if path == "/api/v1/posts" and body is not None:
            out = {"ok": True, "id": "a1b2c3d4e5f6", "key": KEY, "expires": time.time() + 3600}
            if not self.old:
                out["hours"] = body.get("hours")
            return 200, out
        if path == "/api/v1/posts/mine":
            p = {"id": "a1b2c3d4e5f6", "activity": "Mining", "interested": [
                {"handle": "Another_Pilot", "note": "keen", "created": time.time(), "seen": 0, "status": "sent"},
                {"handle": "Second_Pilot", "note": None, "created": time.time(), "seen": 1, "status": "in"},
                {"handle": "Third_Pilot", "note": None, "created": time.time(), "seen": 1, "status": "out"}]}
            if not self.old:
                p.update(filled=1, full=False)
            return 200, {"posts": [p]}
        if path.endswith("/extend"):
            return 200, {"ok": True, "expires": time.time() + 7200, "hours": 3}
        if path.endswith("/decide"):
            return 200, {"ok": True, "filled": 2, "full": False}
        if path.startswith("/api/v1/fed"):
            return 200, {"install": "0123456789abcdef", "week": 38, "since": time.time() - 86400}
        return super()._req(path, body)


def test_details_are_cleaned_and_hours_kept_to_one_to_three():
    d = groups.clean_details({"voice": "voice", "exp": "veteran", "style": "loud", "ship": "  Cutlass   Black ",
                              "lang": "English", "org": "Night Owls", "extra": "dropped"})
    assert d == {"voice": "voice", "exp": "veteran", "ship": "Cutlass Black", "lang": "English", "org": "Night Owls"}
    assert groups.clean_details({"seat": True, "ship": "Prospector"}) == {"seat": True}     # a seat wins over a ship
    assert groups.clean_details({"voice": "shout"}) is None and groups.clean_details("x") is None
    assert [groups.clean_hours(h) for h in (0, 1, "2", 3, 9, None, "x")] == [1, 1, 2, 3, 3, 2, 2]


def test_post_sends_details_and_hours_and_says_the_real_length():
    app, comm = _App(), _Comm3()
    g = groups.Groups(app, comm)
    msg = g.post("recruit", "Mining", "bring a pick", "3", "", details={"voice": "text", "exp": "new"}, hours=1)
    path, body = comm.sent[-1]
    assert body["hours"] == 1 and body["details"] == {"voice": "text", "exp": "new"}
    assert "for an hour" in msg
    row = g.mine()[0]
    assert row["hours"] == 1 and row["details"] == {"voice": "text", "exp": "new"} and row["can_extend"] is True


def test_an_older_site_still_takes_a_post_for_two_hours():
    app, comm = _App(), _Comm3(old=True)
    g = groups.Groups(app, comm)
    assert "for 2 hours" in g.post("recruit", "Mining", None, "3", "", hours=3)
    assert g.mine()[0]["hours"] == 2


def test_keen_statuses_filled_and_withdrawn_players():
    app, comm = _App(), _Comm3()
    g = groups.Groups(app, comm)
    g.post("recruit", "Mining", None, "3", "")
    g.tick(now=time.time())
    st = {i["handle"]: i["status"] for i in g.interest_rows()}
    assert st == {"Another_Pilot": "seen", "Second_Pilot": "in", "Third_Pilot": "out"}   # picked up here = seen
    row = g.mine()[0]
    assert row["filled"] == 1 and row["full"] is False and row["keen"] == 2              # "out" isn't counted as keen
    assert row["chat"].startswith("Mining on AU-90") and "looking for 2 more" in row["chat"]
    # Third_Pilot withdraws on the site: gone from the list here too
    orig = comm._req

    def gone(path, body=None):
        code, d = orig(path, body)
        if path == "/api/v1/posts/mine":
            d["posts"][0]["interested"] = d["posts"][0]["interested"][:2]
        return code, d
    comm._req = gone
    g.poll_at = 0
    g.tick(now=time.time())
    assert {i["handle"] for i in g.interest_rows()} == {"Another_Pilot", "Second_Pilot"}


def test_a_full_crew_closes_itself_ten_minutes_later():
    app, comm = _App(), _Comm3()
    g = groups.Groups(app, comm)
    g.post("recruit", "Mining", None, "2", "")
    pid = g.mine()[0]["id"]
    g.filled[pid], g.full_at[pid] = 2, time.time()
    row = g.mine()[0]
    assert row["full"] and row["can_extend"] is False and "chat" not in row
    g.full_at[pid] = time.time() - 601
    assert g.mine() == []


def test_extend_and_decide_call_the_site_with_the_post_key():
    app, comm = _App(), _Comm3()
    g = groups.Groups(app, comm)
    g.post("recruit", "Mining", None, "3", "")
    g.tick(now=time.time())
    r = g.extend("a1b2c3d4e5f6")
    assert comm.sent[-1] == ("/api/v1/posts/a1b2c3d4e5f6/extend", {"key": KEY}) and "Extended" in r["message"]
    assert g.mine()[0]["hours"] == 3
    r = g.decide("", "Another_Pilot", "in")           # no post id: your recruiting post
    assert comm.sent[-1][1] == {"key": KEY, "handle": "Another_Pilot", "verdict": "in"}
    assert r["filled"] == 2 and {i["handle"]: i["status"] for i in g.interest_rows()}["Another_Pilot"] == "in"
    g.decide("a1b2c3d4e5f6", "Another_Pilot", None)
    assert comm.sent[-1][1]["verdict"] is None
    with pytest.raises(ValueError, match="isn't on your post"):
        g.decide("a1b2c3d4e5f6", "Nobody_Here", "in")


def test_an_older_site_without_extend_or_decide_changes_nothing():
    app, comm = _App(), _Comm3(old=True)
    g = groups.Groups(app, comm)
    g.post("recruit", "Mining", None, "3", "")
    g.tick(now=time.time())
    before = g.mine()[0]["expires"]
    with pytest.raises(ValueError, match="hasn't been updated"):
        g.extend("a1b2c3d4e5f6")
    with pytest.raises(ValueError, match="hasn't been updated"):
        g.decide("a1b2c3d4e5f6", "Another_Pilot", "in")
    assert g.mine()[0]["expires"] == before


def test_extend_passes_the_sites_reason_on():
    app, comm = _App(), _Comm3()
    g = groups.Groups(app, comm)
    g.post("recruit", "Mining", None, "3", "")
    comm._req = lambda path, body=None: (409, {"ok": False, "error": "Posts run for 3 hours at most."})
    with pytest.raises(ValueError, match="3 hours at most"):
        g.extend("a1b2c3d4e5f6")


def test_pirates_here_and_groups_on_shard_from_the_public_feed():
    app, comm = _App(), _Comm3()
    g = groups.Groups(app, comm)
    shard = "pub_apse2b_9945425_090"
    comm.posts = {"open": True, "posts": [
        {"id": "111111111111", "kind": "recruit", "shard_id": shard},
        {"id": "222222222222", "kind": "recruit", "shard_id": shard, "full": True},
        {"id": "333333333333", "kind": "lfg", "shard_id": shard},
        {"id": "444444444444", "kind": "recruit", "shard_id": "pub_apse2b_9945425_110"}],
        "pirates": [{"shard_id": shard, "area": "hurston", "area_name": "Hurston", "system": "stanton", "reporters": 1,
                     "created": 10, "expires": 20, "latest": 15},
                    {"shard_id": shard, "area": "crusader", "area_name": "Crusader", "system": "stanton", "reporters": 3,
                     "created": 11, "expires": 21, "latest": 16}]}
    # _App sits at Cutter's Rig, which the test places call Hurston
    p = g.pirates_here()
    assert p["here"]["area"] == "hurston" and p["here"]["last"] == 15 and p["elsewhere"]["area"] == "crusader"
    assert p["area_name"] == "Hurston"
    assert g.groups_on_shard() == 1
    comm.posts = {"open": False}
    assert g.pirates_here()["here"] is None and g.groups_on_shard() == 0


def test_fed_count_is_unknown_on_an_older_site_or_an_error():
    store = SimpleNamespace(install_id=lambda: "0123456789abcdef")
    c = community.Community(SimpleNamespace(cfg={}, store=store), "http://127.0.0.1:9", "1.4.0")
    c._req = lambda path, body=None: (200, {"week": 38})
    assert c.fetch_fed() == 38
    c._req = lambda path, body=None: (404, {"error": "not found"})
    assert c.fetch_fed() is None

    def boom(path, body=None):
        raise OSError("offline")
    c._req = boom
    assert c.fetch_fed() is None


RETRIEVE = """<2026-10-29T22:15:00.000Z> [Notice] <CEntityComponentShipListProvider::SetVehicleSpawningInformations> SetVehicleSpawningInformations - VehicleEntityId: [123], LandingArea: Test_Pilot's
<2026-10-29T22:15:02.000Z> [Notice] <ATC_Reset_VehiclesBeingStoredCleared> ATC 'ORIG_m80_ShipATCDataManager_9001' [9001] clearing 0 entries from vehicles-being-stored list on Reset [Team_MissionFeatures][ATC]
<2026-10-29T23:15:00.000Z> [Notice] <CEntityComponentShipListProvider::SetVehicleSpawningInformations> SetVehicleSpawningInformations - VehicleEntityId: [124], LandingArea: Test_Pilot's
<2026-10-29T23:15:03.000Z> [Notice] <ATC_Reset_VehiclesBeingStoredCleared> ATC 'ORIG_m80_ShipATCDataManager_9003' [9003] clearing 0 entries from vehicles-being-stored list on Reset [Team_MissionFeatures][ATC]
<2026-10-29T23:40:00.000Z> [Notice] <CEntityComponentShipListProvider::SetVehicleSpawningInformations> SetVehicleSpawningInformations - VehicleEntityId: [125], LandingArea: Test_Pilot's
<2026-10-29T23:40:04.000Z> [Notice] <ATC_Reset_VehiclesBeingStoredCleared> ATC 'RSI_Constellation_Mk5_Centaurus_ShipATCDataManager_9004' [9004] clearing 0 entries from vehicles-being-stored list on Reset [Team_MissionFeatures][ATC]
<2026-10-29T23:50:00.000Z> [Notice] <CEntityComponentShipListProvider::SetVehicleSpawningInformations> SetVehicleSpawningInformations - VehicleEntityId: [126], LandingArea: Test_Pilot's
"""
CRASH = """<2026-10-29T23:58:00.000Z> [Notice] <Join PU> address[1.2.3.4] port[64300] shard[pub_apse2a_12881860_020] locationId[0]
Cloud Imperium Games public crash handler taking over
Exception EXCEPTION_ACCESS_VIOLATION(0xC0000005) addr=0x7ff6 digest=00ab12cd
Is GPU crash: Yes
"""


def _parse(text):
    s = Session("Game.log")
    for raw in records(text.splitlines(True)):
        s.add(parse_line(raw))
    return s


def test_ships_retrieved_counts_named_ships_and_keeps_no_handle():
    s = _parse(RETRIEVE)
    assert s.ships_retrieved() == {"ORIG_m80": 2, "RSI_Constellation_Mk5_Centaurus": 1}   # the unnamed one isn't counted
    summary = s.summary()
    assert summary["ships_retrieved"] == {"ORIG_m80": 2, "RSI_Constellation_Mk5_Centaurus": 1}
    assert "Test_Pilot" not in repr(summary["ships_retrieved"])


def test_ships_retrieved_adds_past_sessions_on_this_build(tmp_path):
    from scstatus.app import App
    from scstatus.store import Store
    store = Store(tmp_path / "s.db")
    for i, (build, ships) in enumerate((("12913470", {"ORIG_m80": 3}), ("12801932", {"ORIG_m80": 9}))):
        store.save_session({"name": f"s{i}.log", "start": i, "end": i + 1, "build": build, "version": "4.10", "shard_id": None,
                            "region": None, "minutes": 1, "load_s": None, "joins": 0, "bad_disconnects": 0, "errors": 0,
                            "clean_exit": True, "ships_retrieved": ships}, 1)
    fake = SimpleNamespace(store=store, build="12913470", session=_parse(RETRIEVE))
    out = App.ships_retrieved(fake)
    assert out == [{"ship": "ORIG M80", "times": 5}, {"ship": "RSI Constellation Mk5 Centaurus", "times": 1}]


def test_crash_state_names_the_library_entry_just_before(tmp_path):
    from scstatus.app import App
    from scstatus.issues import Library
    (tmp_path / "Game.log").write_text(CRASH)
    s = _parse(CRASH)
    assert s.crash and not s.clean_exit
    fake = SimpleNamespace(session=s, game_dir=tmp_path, library=Library())
    c = App.crash_state(fake)
    assert c["ts"] == s.end and c["after_code"] in ("crash-exception", "crash-gpu")
    assert App.crash_state(SimpleNamespace(session=_parse(RETRIEVE))) is None


PNG = "data:image/png;base64," + base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 64).decode()


def test_profile_is_kept_on_this_pc_with_limits(tmp_path):
    p = profile.Profiles(tmp_path)
    assert p.get() is None
    saved = p.save({"handle": "  Demo_Pilot ", "bio": "x" * 500, "exp": "legend", "voice": "text",
                    "ships": ["Origin M80", "C2 Hercules", "Origin M80", 5], "main": "C2 Hercules", "pic": PNG, "extra": 1})
    assert saved["handle"] == "Demo_Pilot" and len(saved["bio"]) == 200 and saved["exp"] == "" and saved["voice"] == "text"
    assert saved["ships"] == ["Origin M80", "C2 Hercules"] and saved["main"] == "C2 Hercules" and "extra" not in saved
    assert (tmp_path / "profile.png").is_file() and saved["pic"].startswith("data:image/png;base64,")
    # Saving without a picture removes it; "keep" leaves the saved one alone
    p.save({"handle": "Demo_Pilot", "pic": PNG})
    assert p.save({"handle": "Demo_Pilot", "pic": "keep"})["pic"]
    assert p.save({"handle": "Demo_Pilot"})["pic"] == "" and not (tmp_path / "profile.png").exists()
    with pytest.raises(ValueError, match="handle"):
        p.save({"handle": ""})
    with pytest.raises(ValueError, match="isn't a PNG"):
        p.save({"handle": "Demo_Pilot", "pic": "data:text/html;base64,PGI+"})
    big = "data:image/jpeg;base64," + base64.b64encode(b"0" * (profile.PIC_MAX + 1)).decode()
    with pytest.raises(ValueError, match="too big"):
        p.save({"handle": "Demo_Pilot", "pic": big})


def test_dashboard_serves_webp_profile_and_refuses_huge_posts(tmp_path):
    import json
    import urllib.request
    from scstatus import dashboard
    app = SimpleNamespace(cfg={"dashboard_port": 8897}, profiles=profile.Profiles(tmp_path))
    server, url = dashboard.start_server(app)
    try:
        html = urllib.request.urlopen(url).read().decode()
        token = html.split('const TOKEN = "')[1].split('"')[0]
        assert 'content="SC Shard Status v' in html                     # an older copy still finds a running one
        r = urllib.request.urlopen(url + "img/centaurus.webp")
        assert r.headers["Content-Type"] == "image/webp"
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(url + "img/not-there-yet.webp")
        assert e.value.code == 404

        def call(path, body=None):
            req = urllib.request.Request(url + path, data=None if body is None else json.dumps(body).encode(),
                                         headers={"X-Token": token, "Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read())
        assert call("api/profile") == {"profile": None}
        assert call("api/profile", {"profile": {"handle": "Demo_Pilot"}})["profile"]["handle"] == "Demo_Pilot"
        assert call("api/profile")["profile"]["handle"] == "Demo_Pilot"
        with pytest.raises(urllib.error.HTTPError) as e:
            call("api/profile", {"profile": {"handle": "Demo_Pilot", "bio": "x" * 1_600_000}})
        assert e.value.code == 413
    finally:
        server.shutdown()
