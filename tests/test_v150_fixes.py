"""1.5.0: CIG's claimed fixes from the library (cig_fixes): a fix on the way, a listed fix that hasn't held, the
new-build notice naming fixes for problems this player hit, and the Issue Council draft saying so."""
import json
import os
import time
import types

from scstatus import app as app_mod
from scstatus import issues, report

FIXES = issues.clean_fixes([
    {"id": "t-spawn", "patch": "4.10.3", "ptu": "13107423", "said": "Ground vehicles being destroyed on the hangar pad when retrieved",
     "starc": "STARC-219816", "rules": ["vehicle-bad-spawn"], "how": "related"},
    {"id": "t-crash", "patch": "4.10.3", "ptu": "13107423", "said": "Two client crashes", "rules": ["crash-exception"], "measure": "crashes"},
    {"id": "t-hangar", "patch": "4.10.3", "ptu": "13093654", "said": "Personal hangars visually overlapping", "rules": [], "ask": True},
    {"id": "bad", "patch": "soon", "said": "x"},
])


def test_library_ships_cig_fixes_and_bad_entries_are_dropped():
    lib = issues.Library()
    assert lib.cig_fixes and all(issues.patch_tuple(f["patch"]) for f in lib.cig_fixes)
    ids = {r.id for r in lib.rules}
    assert all(r in ids for f in lib.cig_fixes for r in f["rules"])
    assert [f["id"] for f in FIXES] == ["t-spawn", "t-crash", "t-hangar"]


def test_coming_on_an_older_build_listed_from_the_ptu_build_on():
    # By build number: the 4.10.3 PTU's Branch line says sc-alpha-4.10.0, so the patch label can't be trusted
    assert issues.fix_for(FIXES, "vehicle-bad-spawn", "4.10.2", "12913470")["state"] == "coming"
    assert issues.fix_for(FIXES, "vehicle-bad-spawn", "4.10.0", "13107423")["state"] == "listed"
    assert issues.fix_for(FIXES, "vehicle-bad-spawn", "4.10.3", "13250001")["state"] == "listed"
    # No build: by patch
    assert issues.fix_for(FIXES, "vehicle-bad-spawn", "4.10.2")["state"] == "coming"
    assert issues.fix_for(FIXES, "vehicle-bad-spawn", "4.10.3")["state"] == "listed"
    assert issues.fix_for(FIXES, "vehicle-bad-spawn", "5.0.0")["state"] == "listed"
    assert issues.fix_for(FIXES, "vehicle-bad-spawn", None)["state"] == "coming"
    assert issues.fix_for(FIXES, "hangar-queue", "4.10.3") is None


def test_draft_says_the_listed_fix_did_not_hold():
    f = {"rule_id": "vehicle-bad-spawn", "title": "Something spawned inside the scenery", "explain": "It overlapped.",
         "area": "Vehicles", "first_ts": 1793786400, "last_ts": 1793786400, "count": 1, "fields": {},
         "cig_fix": issues.fix_for(FIXES, "vehicle-bad-spawn", "4.10.3")}
    d = report.draft(f, {"session": {"branch": "4.10.3", "build": "13200000"}})
    happened = next(s for s in d["sections"] if s["key"] == "happened")["text"]
    assert "still happens on 4.10.3, whose patch notes listed a potential fix (STARC-219816)" in happened
    f["cig_fix"] = issues.fix_for(FIXES, "vehicle-bad-spawn", "4.10.2")
    d = report.draft(f, {"session": {"branch": "4.10.2", "build": "12913470"}})
    assert "patch notes listed" not in next(s for s in d["sections"] if s["key"] == "happened")["text"]


class _Store:
    def __init__(self, sessions):
        self.m, self._s = {}, sessions

    def meta(self, k, d=None):
        return self.m.get(k, d)

    def set_meta(self, k, v):
        self.m[k] = v

    def sessions(self, limit=200):
        return self._s


def test_patch_notice_names_fixes_for_problems_this_player_hit(tmp_path):
    patch_at = time.time() - 3600
    bk = tmp_path / "logbackups"
    bk.mkdir()
    old = bk / "Game Build(12913470) 01 Nov 26.log"
    old.write_text("<2026-11-01T10:00:00.000Z> [Notice] <Bad Spawn Position> Spawn of x is in deep penetration for entity URSA_Rover_123[456] [Team_X]\n", encoding="utf-8")
    os.utime(old, (patch_at - 3 * 86400, patch_at - 3 * 86400))
    stale = bk / "Game Build(12660092) 01 Sep 26.log"           # older than the fortnight: not counted
    stale.write_text(old.read_text(encoding="utf-8"), encoding="utf-8")
    os.utime(stale, (patch_at - 40 * 86400, patch_at - 40 * 86400))
    store = _Store([{"start": patch_at - 86400, "crashed": True}])
    store.m["prev_build"] = "12913470"
    a = types.SimpleNamespace(game_dir=tmp_path, store=store,
                              library=types.SimpleNamespace(cig_fixes=FIXES, rules=issues.Library().rules,
                                                            match=issues.Library().match),
                              session=types.SimpleNamespace(branch="4.10.3"), FIX_LOOKBACK_S=14 * 86400)
    a._scan_fix_hits = types.MethodType(app_mod.App._scan_fix_hits, a)
    first = app_mod.App.patch_fixes(a, "13200000", patch_at)
    assert all(f["you"] is None for f in first)                  # still reading, in the background
    a._fix_scan.join(10)
    got = {f["id"]: f for f in app_mod.App.patch_fixes(a, "13200000", patch_at)}
    assert got["t-spawn"]["you"] is True and got["t-spawn"]["titles"] == ["Something spawned inside the scenery"]
    assert got["t-crash"]["you"] is True                         # a session crashed in the fortnight before
    assert got["t-hangar"]["you"] is False and got["t-hangar"]["ask"] is True
    assert json.loads(a.store.m["patch_fix_hits:13200000"]) == ["t-crash", "t-spawn"]
    # The build after (a hotfix, 4.10.3 already before it) brings nothing new; nor does an older build
    a.store.m["prev_build"] = "13200000"
    assert app_mod.App.patch_fixes(a, "13210000", patch_at) == []
    a.store.m["prev_build"] = "12660092"
    assert app_mod.App.patch_fixes(a, "12913470", patch_at) == []


def test_moment_quick_pick_and_hangar_draft():
    lib = issues.Library()
    assert issues.asks_for(lib.cig_fixes, "4.10.2", "12913470") == []        # before the fix: nothing to report yet
    asks = issues.asks_for(lib.cig_fixes, "4.10.0", "13107423")             # the PTU (its Branch says 4.10.0)
    assert [a["chip"] for a in asks] == ["Saw into someone else's hangar"]
    assert issues.asks_for(lib.cig_fixes, "5.0.0", "14000000") == []        # a later patch: no longer asked
    assert issues.ask_matching(lib.cig_fixes, "4.10.3", "The hangar elevator didn't come", "13200000") is None
    a = issues.ask_matching(lib.cig_fixes, "4.10.3", "Saw into someone else's hangar", "13200000")
    f = {"title": a["ic_title"], "ic_title": a["ic_title"], "area": "Hangar", "explain": a["explain"], "first_ts": 1793786400,
         "last_ts": 1793786400, "count": 1, "fields": {}, "rule_id": None, "moment": True,
         "ic_summary": "Saw into someone else's hangar. " + a["explain"],
         "cig_fix": {"patch": "4.10.3", "said": a["said"], "starc": None, "how": "same", "state": "listed"}}
    d = report.draft(f, {"session": {"branch": "4.10.3", "build": "13200000"}})
    assert d["title"] == "Personal hangar overlaps other players' hangars"
    assert "still happens on 4.10.3, whose patch notes listed a potential fix." in next(s for s in d["sections"] if s["key"] == "happened")["text"]


def test_a_vanduul_contract_suggests_the_activity():
    lib = issues.Library()
    cs = [{"name": "Intercept Vanduul Fleet", "result": "active", "accepted": 5},
          {"name": "Deliver medical supplies", "result": "active", "accepted": 9}]
    assert issues.activity_for(lib.activity_hints, cs) == "Vanduul Incursion"
    assert issues.activity_for(lib.activity_hints, [{"name": "Intercept Vanduul Fleet", "result": "complete"}]) is None
    assert issues.activity_for(lib.activity_hints, []) is None
