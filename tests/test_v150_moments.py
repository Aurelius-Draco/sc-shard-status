"""1.5.0: a moment sent for review carries enough to diagnose it without the player's files.

The cases are the three moments sent on 3 Nov 2026 from a struggling server at Crusader: a burst of failed inventory
moves at 6:14 pm, "Items went missing" marked at 6:41 pm (27 minutes later, so nothing was found near it), and
"ATC won't respond" at 6:50 pm, right as the player changed game server, with no library rule to match.
"""
import json
from types import SimpleNamespace

from scstatus import app as appmod, community

T = 1793695312          # 6:41:52 pm, the "Items went missing" mark


def _finding(rule_id, first, last, near=False, kind="problem"):
    return {"rule_id": rule_id, "title": rule_id, "severity": "medium", "kind": kind,
            "first_ts": first, "last_ts": last, "near_mark": near}


def test_a_problem_from_half_an_hour_before_goes_with_a_late_moment():
    found = [
        _finding("inventory-request-failed", T - 1660, T - 1620),       # 6:14, 27 minutes before
        _finding("actor-action-queue-full", T - 1680, T - 1680),
        _finding("server-struggling", T - 120, T + 30, near=True),
        _finding("ancient-thing", T - 4000, T - 3900),                     # over half an hour: left out
        _finding("contract-failed", T - 900, T - 900, kind="info"),         # info, never a problem
        _finding(None, T - 600, T - 700),                                  # no rule id (overlay), not "earlier"
    ]
    near, earlier = appmod.moment_findings(found, T)
    assert [f["rule_id"] for f in near] == ["server-struggling"]
    assert [f["rule_id"] for f in earlier] == ["inventory-request-failed", "actor-action-queue-full"]
    assert earlier[0]["min_before"] == 27


def test_the_detail_is_cut_to_the_allowed_shape():
    d = community.moment_detail_clean({
        "earlier": [{"id": "inventory-request-failed", "min": 27}, {"id": "../admin", "min": 1}, "junk"] + [{"id": f"x-{i}", "min": 1} for i in range(9)],
        "unknown": [{"sig": "ATC|  Landing request  <hex> timed out", "n": 3, "level": "error", "line": "raw line with Some_Pilot"},
                    {"sig": "   "}] + [{"sig": f"s{i}", "n": 1} for i in range(9)],
        "events": [{"k": "server_change", "s": 15}, {"k": "Bad Kind!", "s": 2}, {"k": "qt_arrived", "s": 99999}],
        "area": {"system": "stanton", "area_name": "Crusader", "place": "Orison"},
        "server": "169", "fps": "24.33", "place": "Seraphim Station", "handle": "Some_Pilot",
    })
    assert set(d) == {"earlier", "unknown", "events", "area", "server", "fps"}
    assert d["earlier"][0] == {"id": "inventory-request-failed", "min": 27} and len(d["earlier"]) == 6
    assert all(e["id"] != "../admin" for e in d["earlier"])
    assert d["unknown"][0] == {"sig": "ATC| Landing request <hex> timed out", "n": 3, "level": "error"} and len(d["unknown"]) == 5
    assert d["events"] == [{"k": "server_change", "s": 15}]          # bad kind dropped, out-of-range seconds dropped
    assert d["area"] == {"system": "stanton", "area_name": "Crusader"} and d["server"] == "169" and d["fps"] == 24.3
    text = json.dumps(d)
    assert "Some_Pilot" not in text and "Orison" not in text and "Seraphim" not in text
    assert community.moment_detail_clean({}) is None and community.moment_detail_clean("x") is None
    assert community.moment_detail_clean({"server": "game-07 "}) is None


def test_send_moment_adds_the_detail_and_version_only_when_there_is_some():
    sent = []
    store = SimpleNamespace(install_id=lambda: "9" * 16)
    c = community.Community(SimpleNamespace(cfg={}, store=store), "http://127.0.0.1:9", "1.5.0")
    c._req = lambda path, body=None: (sent.append(body) or (200, {"ok": True, "matched": []}))
    c.send_moment(T, "12913470", "pub_use1b_12881860_360", "Items went missing", [])
    assert set(sent[-1]) == {"install", "ts", "build", "shard_id", "what", "issues"}
    c.send_moment(T, "12913470", "pub_use1b_12881860_360", "Items went missing", [],
                  {"earlier": [{"id": "inventory-request-failed", "min": 27}], "nonsense": 1})
    assert sent[-1]["detail"] == {"earlier": [{"id": "inventory-request-failed", "min": 27}]} and sent[-1]["version"] == "1.5.0"


class _Places:
    def where(self, code):
        return {"system": "stanton", "area": "crusader", "area_name": "Crusader"} if code else None

    def place(self, code):
        return "Seraphim Station"


def test_the_detail_for_the_atc_moment(tmp_path, monkeypatch):
    """6:50 pm: the player changed game server (178 to 169) a few seconds before marking. An error the library doesn't
    know goes as its stripped code; one still holding a handle from the log is dropped instead of sent."""
    t = 1793695825
    snaps = [{"ts": t - 200, "shard_id": "s1", "server_name": "pub-use1b-game-178", "ok": True},
             {"ts": t - 20, "shard_id": "s1", "server_name": "pub-use1b-game-169", "ok": True}]
    fake = SimpleNamespace(
        game_dir=tmp_path, session=None, places=_Places(),
        community=SimpleNamespace(places=_Places()),
        store=SimpleNamespace(snapshots=lambda since=0, limit=400: [s for s in snaps if s["ts"] >= since]),
        EVENT_KINDS=appmod.App.EVENT_KINDS)
    monkeypatch.setattr(community, "make_redactor", lambda path: __import__("scstatus.redact", fromlist=["Redactor"]).Redactor(["Some_Pilot"]))
    res = {"unknown": [
        {"title": "Unrecognised error: ATC", "count": 2, "first_ts": t - 40, "last_ts": t - 5,
         "fields": {"sig": "CSCATC::OnRequest| Landing request for '<name>'[N] got no response"}},
        {"title": "Unrecognised warning: Chat", "count": 1, "first_ts": t - 30, "last_ts": t - 30,
         "fields": {"sig": "Chat| Some_Pilot said hello"}},
        {"title": "Unrecognised error: Old", "count": 1, "first_ts": t - 3000, "last_ts": t - 2900,
         "fields": {"sig": "Old| long ago"}}]}
    snap = {"location": "Stanton2_SeraphimStation", "server_name": "pub-use1b-game-169", "server_fps": 24.3}
    d = appmod.App._moment_detail(fake, t, res, snap, [], [])
    assert d["unknown"] == [{"sig": "CSCATC::OnRequest| Landing request for '<name>'[N] got no response", "n": 2, "level": "error"}]
    assert d["events"] == [{"k": "server_change", "s": 20}]
    assert d["area"] == {"system": "stanton", "area_name": "Crusader"} and d["server"] == "169" and d["fps"] == 24.3
    assert "Seraphim" not in json.dumps(d) and "Some_Pilot" not in json.dumps(d)
    lines = appmod.App._moment_send_lines(SimpleNamespace(EVENT_WORDS=appmod.App.EVENT_WORDS), d)
    assert "The area: Crusader (never the exact place)" in lines
    assert any("changed game server" in x for x in lines) and any("1 error code the app doesn't know yet" in x for x in lines)


def test_codes_never_carry_names():
    # Audit, 4 Nov: a handle inside an error code went out marked clean, and quoted names weren't touched
    from scstatus.redact import Redactor, scrub_code, leaks
    red = Redactor(["Some_Pilot", "Other_Guy"])
    f = {"fields": {"sig": "ATC| Landing request <hex> for Some_Pilot timed out after Ns"}, "title": "x", "area": "ATC",
         "count": 2, "examples": ["<2026-11-03T08:50:00.000Z> [Error] <ATC> Landing request 0x1F for Some_Pilot timed out after 30s"]}
    rid, p = community.review_request(f, {"build": "12913470"}, red, "a" * 16, contracts=["Help Other_Guy out"])
    assert "Some_Pilot" not in json.dumps(p) and "Other_Guy" not in json.dumps(p)
    assert p["sig"] == "ATC| Landing request <hex> for <YOU> timed out after Ns" and p["checked_clean"] is True
    assert scrub_code("Chat| Joined channel 'Night Owls Ops' as member") == "Chat| Joined channel '<TEXT>' as member"
    assert scrub_code('Org| "Ashen Tide" invite failed', red) == "Org| '<TEXT>' invite failed"
    assert not leaks(scrub_code("x for Some_Pilot", red), red.handles)


def test_a_moment_opened_late_still_looks_back_half_an_hour():
    # Audit, 4 Nov: opened 25 minutes after marking, the check only reached 10 minutes before the mark
    import time as _t
    got = {}
    a = SimpleNamespace(cfg={"lookback_minutes": 30}, lock=__import__("threading").Lock(), snaps=[], library=SimpleNamespace(cig_fixes=[]),
                        names=None, game_dir=__import__("pathlib").Path("."), session=None, build=None, EARLIER_S=appmod.App.EARLIER_S)
    mark = _t.time() - 25 * 60
    a.marks = lambda within: [{"ts": mark}]
    orig = appmod.diagnose
    appmod.diagnose = lambda *x, lookback_min, **k: got.setdefault("min", lookback_min) and {"findings": [], "unknown": []}
    try:
        appmod.App.run_diagnosis(a, None, mark)
    finally:
        appmod.diagnose = orig
    assert got["min"] >= 25 + 30               # the mark was 25 min ago; the "earlier" window is 30 min before it
