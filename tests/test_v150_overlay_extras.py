"""1.5.0: what else the overlay shows (r_displayinfo 3 on 4.10.3): the zone you're in, the planet, the tracked
mission and the render split. Read now and then, best effort, never shared. Lines are from the 4.10.3 PTU (7 Nov)."""
from types import SimpleNamespace

from scstatus import app as appmod, community, issues, score
from scstatus.overlay import parse_lines

LINES = ["CamDir: 0 19 -92 FOV: 60 Focal: 0.30 FStop: 0.5",
         "Zone: RSI_Constellation Mk5 Centaurus 874827156047 Pos: -1.29m 41.71m -0.00m",
         "Zone: SolarSystem_874762419603 Pos: 25149401.1724km -25118159.8587km 26.9457km",
         "Zone: Root Pos: 25149401.1724km -25118159.8587km 26.9457km",
         "FPS 65.5 [53..80], - 15.9ms [12.6ms]",
         "Server FPS 23.3 [22.2..24.4] - 43.0ms [41.0..45.1], Hitches: 0",
         "Server: ptu-use1b-sc-alpha-4100-13132336-game-09, restarts 0, pop. [shard 130, srv 36]",
         "Net: ping 223.9ms, loss 0.0% BwIn 95.506kbps, BwOut 114.571kbps",
         "Render: MT: 12.7ms RT: 3.9ms GPU: 15.4ms",
         "Tracked mission. : InterSec_Bounty_Nyx_Intro.[650f564d-d7ac-4cd8-b73c-1db0c1218526]",
         "NoCurrent Planet"]


def test_the_new_lines_parse_without_ids_or_positions():
    s = parse_lines(LINES)
    assert s["zone"] == "RSI_Constellation_Mk5_Centaurus"
    assert s["mission"] == "InterSec_Bounty_Nyx_Intro"
    assert s["planet"] == ""                                         # read, and not on a planet
    assert (s["render_mt_ms"], s["render_rt_ms"], s["render_gpu_ms"]) == (12.7, 3.9, 15.4)
    assert s["server_fps"] == 23.3 and s["pop_shard"] == 130        # the core lines are untouched
    text = repr(s)
    assert "874827156047" not in text and "650f564d" not in text and "25149401" not in text
    assert parse_lines(["Zone: rs_int_layout_keeger 03 Pos: -16.35m"])["zone"] == "rs_int_layout_keeger_03"
    assert parse_lines(["Planet:Hurston OC (x)"])["planet"] == "Hurston"


def test_ship_mission_and_pc():
    assert appmod.ship_of_zone("RSI_Constellation_Mk5_Centaurus") == "RSI Constellation Mk5 Centaurus"
    assert appmod.ship_of_zone("rs_int_layout_keeger_03") is None
    assert appmod.mission_words("InterSec_Bounty_Nyx_Intro") == "InterSec Bounty Nyx Intro"
    assert appmod.pc_bound(12.7, 3.9, 15.4)["bound"] == "gpu"
    assert appmod.pc_bound(20.0, 4.0, 11.0)["bound"] == "cpu"
    assert appmod.pc_bound(12.0, 3.0, 12.5)["bound"] == "even"
    assert appmod.pc_bound(None, None, 12.0) is None
    hints = issues.Library().activity_hints
    assert issues.activity_for_mission(hints, "InterSec_Bounty_Nyx_Intro") == "Bounty hunting"
    assert issues.activity_for_mission(hints, "Intersec_ShipWaveAttack_H_Van") == "Vanduul Incursion"


def test_you_state_and_low_fps_advice():
    import threading, time
    now = time.time()
    snap = dict(parse_lines(LINES), ts=now - 10, ok=True)
    a = SimpleNamespace(lock=threading.Lock(), snaps=[snap], places=SimpleNamespace(place=lambda c: None),
                        library=issues.Library())
    y = appmod.App.you_state(a, now)
    assert y["ship"] == "RSI Constellation Mk5 Centaurus" and y["mission"] == "InterSec Bounty Nyx Intro"
    assert y["activity"] == "Bounty hunting" and y["pc"]["bound"] == "gpu" and y["planet"] is None
    assert appmod.App.you_state(SimpleNamespace(lock=threading.Lock(), snaps=[dict(snap, ts=now - 999)]), now) is None
    tips = score.tips(23.0, 22.0, 60, 0, 0, 0, dict(snap, client_fps=24.0))
    assert any("graphics card is the limit" in t for t in tips)


def test_none_of_it_is_shared():
    snap = dict(parse_lines(LINES), ts=1794031494, ok=True, shard_id="pub_use1b_12881860_090")
    r = community.shard_report(snap, "a1b2c3d4e5f60718", "13132336")
    for k in ("zone", "mission", "planet", "render_mt_ms", "render_gpu_ms"):
        assert k not in r
    assert "InterSec" not in repr(r) and "Centaurus" not in repr(r)


def test_the_session_qr_gives_the_shard_and_nothing_else():
    import cv2
    import numpy as np
    from scstatus.overlay import qr_shard
    q = cv2.QRCodeEncoder.create().encode("fec85a90-d305-3644-a4aa-94e394b2ac47 ptu_use1b_13132336_010 1794031494 ptu-sc-alpha-4100-13132336")
    q = cv2.resize(q, None, fx=6, fy=6, interpolation=cv2.INTER_NEAREST)
    frame = np.zeros((2160, 3840, 3), np.uint8)
    frame[40:40 + q.shape[0], 3840 - 60 - q.shape[1]:3840 - 60] = cv2.cvtColor(q, cv2.COLOR_GRAY2BGR)
    assert qr_shard(frame) == "ptu_use1b_13132336_010"
    assert qr_shard(np.zeros((2160, 3840, 3), np.uint8)) is None
