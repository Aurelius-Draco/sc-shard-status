"""Opt-in community sharing added after 1.5.2: the login queue and which kinds of contract give which blueprints.
Both ride on Share my readings and send nothing when it's off. Made-up names only."""
import time
import types

from scstatus import community
from scstatus.community import contract_kind, drops_report, queue_report


def test_contract_kind_keeps_only_the_kind_and_tier():
    assert contract_kind("Verified Bounty: Made Upname | VLRT (Solo Craft, Minimal Support) [500/1000 Rep] [BP]*") == "Verified Bounty (VLRT)"
    assert contract_kind("Bounty Assignment: Made Upname (HRT) [4000/8000 Rep] [BP]*") == "Bounty Assignment (HRT)"
    assert contract_kind("Reclusive Bounty: Made Upname | High Risk [200 Rep]") == "Reclusive Bounty (High Risk)"
    assert contract_kind("Data Transfer [100 Rep] [BP]*") == "Data Transfer"
    assert contract_kind("Mercenary: Retake Outpost") == "Mercenary"
    # Anything that isn't plain words (a handle with an underscore or digits) is refused
    assert contract_kind("Haul for Test_Pilot99 [BP]") is None


def _sess(start, contracts, blueprints, branch="4.10.2", build="12913470"):
    return {"start": start, "branch": branch, "build": build, "contracts": contracts, "blueprints": blueprints}


def test_drops_pair_each_bp_contract_with_the_blueprint_that_followed():
    now = time.time()
    t = now - 3 * 86400
    s = _sess(t, [
        {"name": "Data Transfer [100 Rep] [BP]*", "result": "complete", "ended": t + 100},
        {"name": "Verified Bounty: Made Upname | HRT (Large Craft) [BP]*", "result": "complete", "ended": t + 500},
        {"name": "Verified Bounty: Other Name | HRT (Large Craft) [BP]*", "result": "failed", "ended": t + 900},
        {"name": "Simple Hit [75 Rep]", "result": "complete", "ended": t + 1000},           # no [BP]: not a reward contract
    ], [{"ts": t + 102, "name": "Aves Arms"}, {"ts": t + 1001, "name": "Oracle Helmet"}])
    p = drops_report("0123456789abcdef", [s], 0, ["Test_Pilot"], now)
    assert p["kind"] == "drops" and p["build"] == "12913470" and p["branch"] == "4.10.2"
    assert [(d["kind"], d["bp"]) for d in p["drops"]] == [("Data Transfer", "Aves Arms"), ("Verified Bounty (HRT)", None)]
    assert all(set(d) == {"ended", "kind", "bp"} for d in p["drops"]) and all(d["ended"] % 60 == 0 for d in p["drops"])
    assert "Made Upname" not in repr(p)
    # Sent ones aren't sent again; PTU copies and anything over 30 days old never are
    assert drops_report("0123456789abcdef", [s], t + 600, [], now) is None
    assert drops_report("0123456789abcdef", [dict(s, branch="ptu")], 0, [], now) is None
    old = _sess(now - 40 * 86400, [{"name": "Data Transfer [BP]*", "result": "complete", "ended": now - 40 * 86400}], [])
    assert drops_report("0123456789abcdef", [old], 0, [], now) is None


def test_queue_report_is_place_and_estimate_only():
    q = {"ts": 1794100000.4, "position": 214, "eta_s": 420, "queue": "global"}
    p = queue_report("0123456789abcdef", q, "12913470", "4.10.2")
    assert p == {"v": 1, "kind": "queue", "install": "0123456789abcdef", "channel": "LIVE", "build": "12913470",
                 "branch": "4.10.2", "ts": 1794099960, "queue": "global", "position": 214, "eta_s": 420}
    assert queue_report("x", None, "1", "2") is None


class _Store:
    def __init__(self):
        self.m = {}

    def install_id(self):
        return "0123456789abcdef"

    def meta(self, k, d=None):
        return self.m.get(k, d)

    def set_meta(self, k, v):
        self.m[k] = v

    def session_data(self, limit=200):
        return []

    def sessions(self, limit=60):
        return []


def _community(share, queue):
    now = time.time()
    app = types.SimpleNamespace(cfg={"share_readings": share, "community_board": False}, store=_Store(), channel="LIVE",
                                session=types.SimpleNamespace(branch="4.10.2", start=None, handles=[]), build="12913470",
                                queue_state=lambda: queue, snaps=[], lock=__import__("threading").Lock(), last_result=None)
    c = community.Community(app, "https://example.test", "1.5.2")
    sent = []
    c._req = lambda path, body=None: (sent.append((path, body)), (200, {}))[1]
    return c, sent, now


def test_queue_is_only_sent_with_sharing_on_and_while_in_the_queue():
    q = {"ts": time.time(), "position": 50, "eta_s": 120, "queue": "global"}
    c, sent, now = _community(False, q)
    c.tick(now)
    assert not [p for p, b in sent if p == "/api/v1/queue"]
    c, sent, now = _community(True, q)
    c.tick(now)
    assert [b["position"] for p, b in sent if p == "/api/v1/queue"] == [50]
    c.tick(now + 30)                                    # at most once a minute
    assert len([p for p, b in sent if p == "/api/v1/queue"]) == 1
    c, sent, now = _community(True, None)               # not in a queue: nothing
    c.tick(now)
    assert not [p for p, b in sent if p == "/api/v1/queue"]
