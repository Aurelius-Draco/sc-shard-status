"""1.3: groups, pirate offers, chat lines, reading quality, error reports, log signals, marks."""
import time

from scstatus import community, errors, groups
from scstatus.logparse import Session, parse_line


def _line(ts, tag, msg):
    return f"<{ts}> [Notice] <{tag}> {msg} [Team_X][Y]"


def test_new_log_signals_keep_no_names():
    s = Session()
    s.add(parse_line("<2026-10-30T22:03:37.538Z> Branch: sc-alpha-4.10.2"))
    s.add(parse_line(_line("2026-10-30T23:19:18.257Z", "Add Inventory Management Move",
                           "New Request[91] Player[Test_Pilot] Type[Move] SourceInventory[1:Container:0] TargetInventory[2:Container:0] "
                           "ItemClass[[klwe_rifle_energy_01_mag] [none_lmg_ballistic_01] ] StoredEntity[NULL] LocallyDetached[No]")))
    s.add(parse_line(_line("2026-10-30T23:45:09.382Z", "FatalCollision",
                           "Fatal Collision occured for vehicle DRAK_Cutlass_Red_909537321105 [Part: Body, Pos: x: 1, Zone: OOC, PlayerPilot: 1] after hitting entity: UNKNOWN")))
    s.add(parse_line(_line("2026-10-30T23:45:09.625Z", "[ActorState] Dead",
                           "[ACTOR STATE][CSCActorControlStateDead::PrePhysicsUpdate] Actor 'Test_Pilot' [770] ejected from zone "
                           "'DRAK_Cutlass_Red_909537321105' [909] to zone 'OOC_Stanton_1_Hurston' [862] due to previous zone being in a destroyed vehicle with detached interior.")))
    assert s.branch == "4.10.2"
    assert s.item_moves[0][1] == ["klwe_rifle_energy_01_mag", "none_lmg_ballistic_01"]
    assert s.deaths == [{"ts": s.deaths[0]["ts"], "ship": "DRAK_Cutlass_Red", "collision": True}]
    assert "Test_Pilot" not in repr(s.item_moves) + repr(s.deaths)
    # A death with no crash just before it could be another player
    s.add(parse_line(_line("2026-10-30T23:55:09.625Z", "[ActorState] Dead",
                           "Actor 'Test_Pilot' [770] ejected from zone 'RSI_Aurora_Mk2_88' [88] to zone 'x' [1] due to previous zone being in a destroyed vehicle")))
    assert s.deaths[-1]["collision"] is False and s.deaths[-1]["ship"] == "RSI_Aurora_Mk2"


def test_quality_counts_thrown_away_values():
    now = time.time()
    snaps = [{"ts": now - 60 + i * 5, "ok": True, "server_name": "game-1" if i != 3 else None, "pop_shard": 400,
              "pop_srv": 30, "restarts": 435 if i == 5 else 0, "hitches": 0, "loss_pct": 0.0} for i in range(12)]
    q = community.quality(snaps, tries=14, failed=2, screen="2560x1440")
    assert q == {"readings": 14, "failed": 2, "no_server": 1, "no_players": 0, "misreads": 1, "screen": "2560x1440"}
    p = community.shard_report({"ts": now, "shard_id": "pub_apse2b_1_090"}, "0123456789abcdef", "1", quality=q)
    assert p["quality"]["misreads"] == 1


def test_error_reports_strip_paths_and_quotes():
    try:
        open("C:\\Users\\Someone\\AppData\\Local\\SC Shard Status\\x.json")
    except OSError as e:
        errors.capture("test", e)
    p = errors.payload("0123456789abcdef", "1.3.0")
    text = repr(p)
    assert p and p["errors"][0]["n"] >= 1
    assert "Someone" not in text and "AppData" not in text
    errors.sent(p["errors"])
    assert errors.payload("0123456789abcdef", "1.3.0") is None


class _Store:
    def __init__(self):
        self.m = {}

    def meta(self, k, d=None):
        return self.m.get(k, d)

    def set_meta(self, k, v):
        self.m[k] = v

    def install_id(self):
        return "0123456789abcdef"


class _Alerts:
    mode = None

    def __init__(self):
        self.recent, self.shown = [], []

    def notify(self, title, body, tag=None, sound=False):
        self.shown.append(body)


class _Places:
    def where(self, code):
        return {"system": "stanton", "area": "hurston", "area_name": "Hurston"} if code else None


class _Comm:
    places = _Places()

    def __init__(self):
        self.sent = []

    def _req(self, path, body=None):
        self.sent.append((path, body))
        if path == "/api/v1/posts" and body is None:
            return 200, {"open": True, "activities": ["Mining"]}
        if path == "/api/v1/posts":
            return 200, {"ok": True, "id": "a1b2c3d4e5f6", "key": "f" * 32, "expires": time.time() + 7200}
        if path == "/api/v1/posts/mine":
            return 200, {"posts": [{"id": "a1b2c3d4e5f6", "activity": "Mining", "interested": [
                {"handle": "Another_Pilot", "note": "keen", "created": time.time(), "seen": 0}]}]}
        return 200, {}


class _App:
    def __init__(self, s=None):
        import collections
        self.store, self.alerts, self.session = _Store(), _Alerts(), s
        self.alerts.recent = collections.deque()

    def latest_snap(self):
        return {"shard_id": "pub_apse2b_9945425_090", "server_name": "pub-x-game-37", "location": "Stanton1_CuttersRig"}


def test_group_posts_say_where_and_replies_pop_up():
    app, comm = _App(), _Comm()
    g = groups.Groups(app, comm)
    msg = g.post("recruit", "Mining", "bring a pick", "3", "")
    path, body = comm.sent[-1]
    assert path == "/api/v1/posts" and body["shard_id"] == "pub_apse2b_9945425_090" and body["server"] == "37"
    assert body["area"] == "hurston" and body["handle"] is None and "location" not in body
    assert "2 hours" in msg
    assert g.mine()[0]["chat"] == "Mining on AU-90 near Hurston looking for 3 more. Press I'm interested on Verse Shards"
    g.tick(now=time.time())
    assert g.interest[0]["handle"] == "Another_Pilot" and "Another_Pilot wants to join your Mining" in app.alerts.shown[0]
    g.poll_at = 0
    g.tick(now=time.time())                   # the same reply doesn't pop up twice
    assert len(app.alerts.shown) == 1


def test_pirate_offer_only_after_a_death_that_wasnt_a_crash():
    s = Session()
    now = time.time()
    s.travel = [{"ts": now - 300, "kind": "location", "code": "Stanton1_CuttersRig"}]
    s.deaths = [{"ts": now - 60, "ship": "DRAK_Cutlass_Red", "collision": True}]
    g = groups.Groups(_App(s), _Comm())
    assert g.pirate_offer(now) is None
    s.deaths.append({"ts": now - 30, "ship": "DRAK_Cutlass_Red", "collision": False})
    offer = g.pirate_offer(now)
    assert offer["area_name"] == "Hurston" and offer["ship"] == "DRAK Cutlass Red"
    g.pirate_done()
    assert g.pirate_offer(now) is None
    assert g.pirate_offer(now + 3600) is None                 # and it doesn't hang around


def test_chat_lines():
    d = {"shard": {"name": "AU-20"}, "where": {"area_name": "Bloom"}, "community": None}
    assert groups.chat_lines(d, {"server_fps": 4.5, "pop_srv": 22})[0] == \
        "AU-20 server fps dropping to critical near Bloom (4.5 fps). I'd avoid high-risk stuff there"
    assert "AU-20 server running Bloom has only 22 players right now" in groups.chat_lines(d, {"server_fps": 4.5, "pop_srv": 22})
    assert groups.chat_lines({"shard": {}}, {}) == []


def test_what_went_wrong_ignores_a_lone_misread_restart_or_loss():
    from scstatus.diagnose import _overlay
    now = time.time()
    snaps = [{"ts": now - 300 + i * 5, "ok": True, "server_name": "game-37", "server_fps": 20, "restarts": 0,
              "loss_pct": 9.0 if i == 12 else 0.0} for i in range(60)]
    snaps[20]["restarts"] = 435
    assert _overlay(snaps, now - 600) == []
    for x in snaps[40:]:
        x["restarts"] = 1                     # a real restart: the count goes up by one and stays there
    assert [f["title"] for f in _overlay(snaps, now - 600)] == ["Your server node restarted"]
