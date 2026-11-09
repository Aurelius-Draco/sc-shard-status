"""1.6 (9 Nov, Ray): his M80 came up on the hangar pad but wouldn't take off. The pad started raising and never
reported it was up; he heard the pad doors running late, got in and out of the seat, stored it and retrieved it
again, and then it flew. What's gone wrong? now says so. Lines below are shaped like his, with made-up ids."""
from scstatus import diagnose
from scstatus.logparse import Session, parse_line

MGR = "LoadingPlatformManager_ShipElevator_HangarSmallFront"


def _pad(t, state):
    return (f"<2026-11-09T05:{t}Z> [Notice] <CSCLoadingPlatformManager::OnLoadingPlatformStateChanged> [Loading Platform] "
            f"Loading Platform Manager [{MGR}] Platform state changed to {state} [Team_CoreGameplayFeatures][Cargo]")


def _seat(t):
    return (f"<2026-11-09T05:{t}Z> [Notice] <Vehicle Control Flow> CVehicleMovementBase::ClearDriver: Local client node "
            f"[100000000001] releasing control token for 'ORIG_m80_900000000001' [900000000001] [Team_CGP4][Vehicle]")


def _session(lines):
    s = Session()
    for l in lines:
        ev = parse_line(l)
        if ev:
            s.add(ev)
    return s


def test_lines_parse():
    assert parse_line(_pad("54:46.040", "RaisingPlatform"))["kind"] == "pad_state"
    ev = parse_line(_seat("56:00.435"))
    assert ev == {"ts": ev["ts"], "kind": "seat_left", "ship": "ORIG_m80"}


def test_the_stuck_pad_is_found_and_explained():
    s = _session([_pad("54:46.040", "RaisingPlatform"), _seat("56:00.435"), _seat("57:38.048"),
                  _pad("59:00.812", "LoweringPlatform")])
    assert len(s.pad_stuck) == 1
    x = s.pad_stuck[0]
    assert x["ship"] == "ORIG_m80" and x["then"] == "LoweringPlatform"
    f = diagnose._pad_stuck(s, x["ts"] - 60)
    assert f and f[0]["title"] == "Your ship's pad never finished coming up"
    assert "store the ship" in f[0]["fixes"][0] and "M80" in f[0]["explain"]


def test_a_normal_raise_and_late_seat_changes_are_not():
    ok = _session([_pad("59:51.424", "RaisingPlatform"), _pad("59:59.000", "OpenIdle"), _seat("59:59.500")])
    assert ok.pad_stuck == []
    quick = _session([_pad("54:46.040", "RaisingPlatform"), _seat("55:10.000")])     # 24 s: still coming up
    assert quick.pad_stuck == []
    late = _session([_pad("44:46.040", "RaisingPlatform"), _seat("54:46.040")])      # 10 min: you'd flown off
    assert late.pad_stuck == []
