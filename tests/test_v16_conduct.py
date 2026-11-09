"""1.6 (9 Nov, Ray, from RSI's "Reporting Player Misconduct"): the app fills in the details for a player conduct
report the player sends CIG themselves: when, where, shard, server and version, at a marked moment or now. Never
anyone else's handle and nothing sent."""
import time
from types import SimpleNamespace

from scstatus import app as appmod
from scstatus.locations import Places


def _app(snap, marks, handle="Demo_Pilot"):
    a = SimpleNamespace(
        session=SimpleNamespace(shard_id="pub_use1b_11218823_110", version="4.10.2", build="12913470", handles=[handle]),
        community=SimpleNamespace(places=Places()), build="12913470",
        groups=SimpleNamespace(handle=lambda: handle))
    a.latest_snap = lambda: snap
    a.marks_shown = lambda: marks
    return a


def test_now_from_the_latest_reading():
    snap = {"ts": time.time() - 5, "shard_id": "pub_use1b_11218823_110", "server_name": "use1b-ec2-3", "location": "RR_MIC_L3"}
    d = appmod.App.conduct_draft(_app(snap, []))
    assert d["source"] == "now" and abs(d["ts"] - time.time()) < 5
    assert d["place"] == "MIC-L3 Endless Odyssey Station"
    assert d["shard_id"] == "pub_use1b_11218823_110" and d["shard"]
    assert d["version"] == "4.10.2" and d["build"] == "12913470"
    assert d["handle"] == "Demo_Pilot"             # the player's own, from their log; theirs to send or not
    assert d["marks"] == []


def test_a_marked_moment_gives_its_own_time_and_place():
    t = time.time() - 600
    marks = [{"ts": t, "shard_id": "pub_euw1b_1_10", "server": "euw1b-ec2-7", "location": "RR_CRU_L4", "what": "abuse in chat"}]
    d = appmod.App.conduct_draft(_app({}, marks), str(t))
    assert d["source"] == "mark" and d["ts"] == t
    assert d["place"] == "CRU-L4 Shallow Fields Station" and d["shard_id"] == "pub_euw1b_1_10"
    assert d["marks"] == [{"ts": t, "what": "abuse in chat"}]
    # a time that isn't a mark falls back to now
    assert appmod.App.conduct_draft(_app({}, marks), "12345")["source"] == "now"


def test_never_anyone_elses_handle_and_the_drawer_sends_nothing():
    d = appmod.App.conduct_draft(_app({}, []))
    assert set(d) == {"ts", "source", "shard_id", "shard", "server", "place", "system", "version", "build", "handle", "marks"}
    html = open("scstatus/static/index.html", encoding="utf-8").read()
    i = html.index("async function openConduct"); body = html[i:html.index("function closeDrawer", i)]
    assert "api(\"/api/conduct" not in body.replace("api(`/api/conduct", "")      # one GET, no POST
    assert "/api/conduct?ts=" in body and "Verse Shards sends nothing" in body
    assert "killed by" not in body.lower()
