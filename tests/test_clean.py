"""Overlay misreads: a value only counts once it repeats, and each server stint is judged on its own."""
from scstatus import clean
from scstatus.community import summarise


def test_single_misreads_vanish_and_real_changes_stay():
    assert clean.settle([0, 0, 10, 0, 0]) == [None, 0, 0, 0, 0]
    assert clean.settle([0, 0, 0, 1, 1, 1], k=3) == [None, None, 0, 0, 0, 1]
    assert clean.settle([0.0, 0.0, 9.0, 0.0, None, 0.0]) == [None, 0.0, 0.0, 0.0, 0.0, 0.0]


def test_restarts_need_to_hold_and_rise_by_one_or_two():
    # Real readings from a player's PC: lone 9, 10, 435 and 438 between zeros
    assert clean.restart_rises([0, 0, 9, 0, 0, 0, 10, 0, 0, 435, 0, 438, 0, 0]) == 0
    assert clean.restart_rises([4] * 5 + [5] * 6) == 1
    # Held for a while, then back to the old count: a misread, not a restart (real readings)
    assert clean.restart_rises([0] * 6 + [9, 9, 9, 19, 10, 10, 10, 10, 10] + [0] * 6) == 0
    assert clean.restart_rises([4] * 5 + [300] * 6) == 0        # a jump that size is a different counter


def test_a_server_hop_starts_a_fresh_run():
    a = [{"ts": i * 5, "ok": True, "shard_id": "s1", "server_name": "game-01", "server_fps": 20} for i in range(10)]
    b = [{"ts": 50 + i * 5, "ok": True, "shard_id": "s1", "server_name": "game-07", "server_fps": 6} for i in range(6)]
    blank = [{"ts": 80, "ok": True, "shard_id": "s1", "server_name": None, "server_fps": 6}]
    run = clean.current_run(a + b + blank)
    assert len(run) == 7 and {s["server_name"] for s in run} == {"game-07", None}
    # A long gap is a new stint too
    assert len(clean.current_run(a + [dict(a[-1], ts=2000)])) == 1


def test_summary_ignores_misreads():
    snaps = [{"ts": 1000 + i * 5, "ok": True, "shard_id": "pub_apse2a_1_090", "server_name": "g-37",
              "server_fps": 20.0 + (i % 3) * 0.2, "server_fps_min": 19.0, "server_fps_max": 21.0,
              "hitches": 519 if i == 10 else 0, "restarts": 435 if i == 20 else 0,
              "loss_pct": 9.0 if i == 30 else 0.0} for i in range(59)]
    snaps[40]["server_fps_min"], snaps[41]["server_fps_max"] = 1.2, 294
    snaps[50]["server_name"] = None                                  # a line the overlay didn't give us
    snaps[58]["server_name"] = None
    s = summarise(snaps, now=1000 + 58 * 5)
    assert s["restarts"] == 0 and s["hitches"] == 0 and s["loss_pct"] == 0.0
    assert s["server_name"] == "g-37" and 19.9 <= s["server_fps_min"] <= 20.4 and s["server_fps_max"] <= 30
