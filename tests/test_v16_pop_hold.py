"""1.6 (9 Nov, Ray: "we're no longer seeing the players on the shard, and On your server is often showing -"). His
session: the mission tracker sat across the overlay's Server line, so the counts read on 33% of readings. The last
good counts stand in for up to 3 minutes on the same server, with their age; a second look may fill them in only
when they agree with a recent clean read."""
import time

from scstatus import overlay, score


def _snap(t, **kw):
    s = {"ts": t, "ok": True, "shard_id": "pub_apse2a_12881860_110", "server_name": "pub-apse2a-sc-alpha-4102-12974691-game-34",
         "server_fps": 30.0, "ping_ms": 24, "loss_pct": 0.0, "hitches": 0, "restarts": 0, "pop_shard": None, "pop_srv": None}
    s.update(kw)
    return s


def test_the_last_good_counts_stand_in_with_their_age():
    now = time.time()
    snaps = [_snap(now - 100, pop_shard=116, pop_srv=9)] + [_snap(now - 100 + 5 * i) for i in range(1, 21)]
    a = score.assess(snaps, now=now)
    assert a["pop_shard"] == 116 and a["pop_srv"] == 9
    assert 95 <= a["pop_age"] <= 105
    assert "116 players, 9 on your server" in a["summary"]


def test_counts_read_now_have_no_age_and_old_ones_go():
    now = time.time()
    a = score.assess([_snap(now - 10, pop_shard=120, pop_srv=11), _snap(now - 5, pop_shard=118, pop_srv=10)], now=now)
    assert a["pop_shard"] == 118 and a["pop_age"] is None
    old = [_snap(now - 250, pop_shard=116, pop_srv=9)] + [_snap(now - 250 + 10 * i) for i in range(1, 25)]
    b = score.assess(old, now=now)
    assert b["pop_shard"] is None and b["pop_srv"] is None and b["pop_age"] is None


def test_not_across_a_server_hop():
    now = time.time()
    snaps = [_snap(now - 60, pop_shard=116, pop_srv=9),
             _snap(now - 5, server_name="pub-apse2a-sc-alpha-4102-12974691-game-25")]
    a = score.assess(snaps, now=now)
    assert a["pop_srv"] is None


def test_the_server_number_is_held_too():
    now = time.time()
    a = score.assess([_snap(now - 30, pop_shard=116, pop_srv=9), _snap(now - 5, server_name=None)], now=now)
    assert "Your game server (34)" in a["summary"]


def test_a_second_look_count_only_when_it_agrees_with_a_recent_clean_one():
    t = time.monotonic()
    good = {"pop_shard": (427, t - 30), "pop_srv": (34, t - 30)}
    assert overlay._pop_agrees("pop_shard", 431, good, t)
    assert not overlay._pop_agrees("pop_shard", 3, good, t)           # a glyph over "shard 427"
    assert overlay._pop_agrees("pop_srv", 37, good, t)
    assert not overlay._pop_agrees("pop_srv", 74, good, t)
    assert not overlay._pop_agrees("pop_shard", 427, good, t + overlay.POP_AGREE_S + 1)   # too long ago
    assert not overlay._pop_agrees("pop_shard", 427, {}, t)                                 # nothing clean yet
