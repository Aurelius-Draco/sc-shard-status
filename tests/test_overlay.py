"""Tests for scstatus.overlay: the text parser and the OCR overlay reader.

The fixtures are crops of the top right of real 4K screenshots (r_displayinfo 3,
game build 4.10.2) with the Session line blacked out and the session QR code
replaced by random squares. Full frames are rebuilt by pasting a crop into a
dark frame at the top right.
"""

import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scstatus.overlay import FIELDS, OverlayReader, classify, norm_shard_id, parse_lines  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
GUID = "b360e83b-5c9c-c24f-b80f-4977ca855a2c"

# --------------------------------------------------------------------------
# Ground truth for the fixtures (read by eye from the original screenshots)
# --------------------------------------------------------------------------

COMMON = dict(shard_id="pub_apse2a_12881860_090",
              server_name="pub-apse2a-sc-alpha-4102-12974691-game-07",
              restarts=0, hitches=0, loss_pct=0.0, client_fps_min=72, client_fps_max=144,
              vram_total_mb=15423, location="RR_CRU_L4")

EXPECTED = {
    "overlay_4k_1.jpg": dict(
        COMMON, server_fps=21.8, server_fps_min=21.2, server_fps_max=22.3,
        server_ms=45.9, server_ms_min=44.8, server_ms_max=47.3,
        pop_shard=435, pop_srv=34, ping_ms=24.4, bw_in_kbps=222.221, bw_out_kbps=50.556,
        rl_entities=17295, rl_tick_ms=0.26, rl_mtsync_ms=0.97,
        client_fps=106.3, client_ms=10.3, vram_used_mb=9250,
        server_time="Thu Oct 29 01:41:36 2026"),
    "overlay_4k_2.jpg": dict(
        COMMON, server_fps=20.3, server_fps_min=19.1, server_fps_max=21.9,
        server_ms=49.3, server_ms_min=45.6, server_ms_max=52.3,
        pop_shard=432, pop_srv=36, ping_ms=30.9, bw_in_kbps=179.834, bw_out_kbps=47.573,
        rl_entities=17295, rl_tick_ms=0.25, rl_mtsync_ms=0.55,
        client_fps=105.1, client_ms=10.4, vram_used_mb=9242,
        server_time="Thu Oct 29 01:42:11 2026"),
    "overlay_4k_3.jpg": dict(
        COMMON, server_fps=21.6, server_fps_min=18.5, server_fps_max=22.6,
        server_ms=46.4, server_ms_min=44.3, server_ms_max=54.2,
        pop_shard=424, pop_srv=37, ping_ms=27.6, bw_in_kbps=174.112, bw_out_kbps=52.521,
        rl_entities=17252, rl_tick_ms=0.24, rl_mtsync_ms=0.41,
        client_fps=101.8, client_ms=10.7, vram_used_mb=9242,
        server_time="Thu Oct 29 01:44:23 2026"),
    # session QR code on, so the block sits further left
    "overlay_4k_4_qr.jpg": dict(
        COMMON, server_fps=21.7, server_fps_min=20.7, server_fps_max=22.3,
        server_ms=46.1, server_ms_min=44.8, server_ms_max=48.4,
        pop_shard=425, pop_srv=38, ping_ms=29.2, bw_in_kbps=168.923, bw_out_kbps=51.317,
        rl_entities=17252, rl_tick_ms=0.17, rl_mtsync_ms=1.05,
        client_fps=109.0, client_ms=10.0, vram_used_mb=9242,
        server_time="Thu Oct 29 01:45:13 2026"),
}

# Fields that must be right even on the heavily downscaled 1080p frames
CORE = ("server_fps", "server_ms", "pop_shard", "pop_srv", "ping_ms", "server_name",
        "client_fps", "rl_entities", "location", "server_time")

CLEAN_LINES = [
    "FPS 106.3 [72..144], - 10.3ms [7.1ms]",
    f"Session: {GUID}",
    "ShardId: pub apse2a 12881860 090",
    "[100.0|100.0|100.0|100.0|100.0|100.0|100.0]",
    "Phys: 0.0ms Stall: 0.0ms Event: 0.0ms",
    "Server FPS 21.8 [21.2..22.3] - 45.9ms [44.8..47.3], Hitches: 0",
    "Server: pub-apse2a-sc-alpha-4102-12974691-game-07, restarts 0, pop. [shard 435, srv 34]",
    "Net: ping 24.4ms, loss 0.0% BwIn 222.221kbps, BwOut 50.556kbps",
    "RL: entities: 17295, tick: 0.26ms, MTSync: 0.97ms",
    "ServerTime: Thu Oct 29 01:41:36 2026",
    "UniverseTime: Wed Dec 15 10:09:41 2990",
    "Working Set (OS): 13.14 GiB Committed (OS): 24.89 GiB",
    "VRAM(MB): 9250 / 15423",
    "VRAM Demoted: 0, OSBudget: 15419 MB",
    "Current player location : RR_CRU_L4  (LZ : RR_CRU_L4)",
    "Entities: 20536, PS: 0, QdBatches: 0, LB: 0",
]


def _assert_matches(snap, exp, fields=None):
    bad = {k: (snap.get(k), v) for k, v in exp.items()
           if (fields is None or k in fields) and snap.get(k) != v}
    assert not bad, f"wrong fields (got, expected): {bad}"


# --------------------------------------------------------------------------
# parse_lines
# --------------------------------------------------------------------------

def test_parse_clean_block():
    s = parse_lines(CLEAN_LINES)
    assert s["ok"] is True
    assert "ts" not in s
    assert set(s) == set(FIELDS) | {"ok"}
    _assert_matches(s, EXPECTED["overlay_4k_1.jpg"])


def test_parse_never_returns_session_guid():
    s = parse_lines(CLEAN_LINES + [f"Sessi0n: {GUID}", f"Sesion {GUID}", GUID])
    flat = " ".join(str(v) for v in s.values()).lower()
    assert "b360e83b" not in flat and "4977ca855a2c" not in flat
    assert "session" not in s


def test_parse_ocr_mangled_block():
    lines = [
        "FPS 1O6.3 [72.144], - 1O.3ms [7.1ms]",               # O for 0, '..' read as '.'
        f"Session: {GUID}",
        "Shardld: pub_apse2a_1288186O_O9O",                    # l for I, O for 0
        "Server FPS 2l.8 l21.2..22.31 - 45,9ms [44.8.47.3], Hltches: O",   # brackets read as l/1
        "Server:pub-apse2a-sc-alpha-41O2-12974691-game-O7,restarts O,pop.[shard 435,srv 34]",
        "Net:ping 24.4ms,loss O.O% Bwln 222.221kbps,Bw0ut 5O.556kbps",
        "RL: entities: 17295, tick: O.26ms, MTSync: 0.97ms",
        "ServerTime: Thu 0ct 29 O1:41:36 2026",
        "VRAM (MB) : 925O / 15423",
        "Current player location:RR_CRU_L4 (LZ:RR_CRU_L4)",
    ]
    s = parse_lines(lines)
    assert s["ok"] is True
    _assert_matches(s, EXPECTED["overlay_4k_1.jpg"])


def test_parse_missing_spaces_and_odd_punctuation():
    lines = [
        "ServerFPS21.8(21.2..22.3)-45.9ms{44.8..47.3},Hitches:0",
        "Server: pub-apse2a-sc-alpha-4102-12974691-game-07,restarts 0,pop.[shard435,srv34]",
        "Net: ping 24.4ms, loss 0.0% BwIn 222.221kbps, BwOut 50.556kbps",
        "FPS 106.3 【72‥144】, - 10.3ms [7.1ms]",               # full-width brackets, one-char ellipsis
    ]
    s = parse_lines(lines)
    assert s["ok"] is True
    _assert_matches(s, dict(server_fps=21.8, server_fps_min=21.2, server_fps_max=22.3,
                            server_ms=45.9, server_ms_min=44.8, server_ms_max=47.3, hitches=0,
                            pop_shard=435, pop_srv=34, client_fps=106.3, client_fps_min=72,
                            client_fps_max=144, client_ms=10.3))


def test_parse_comma_decimals_and_lost_dots():
    s = parse_lines([
        "Server FPS 21,8 [21,2..22,3] - 45,9ms [44,8..47,3], Hitches: 2",
        "Net: ping 244ms, loss 0.0% BwIn 222.221kbps, BwOut 50.556kbps",     # dot lost in ping
        "Server: pub-apse2a-sc-alpha-4102-12974691-game-07, restarts 1, pop. [shard 435, srv 34]",
    ])
    assert (s["server_fps"], s["server_fps_min"], s["server_ms_max"]) == (21.8, 21.2, 47.3)
    assert s["ping_ms"] == 24.4 and s["hitches"] == 2 and s["restarts"] == 1


def test_parse_keywords_used_when_numbers_dont_line_up():
    s = parse_lines([
        "Server FPS 21.8 [21.2..22.3] - 45.9ms [44.8..47.3], Hitches: 0",
        "Net: ping 24.4ms, loss 0.0% x7 BwIn 222.221kbps, BwOut 50.556kbps",   # stray "7"
        "RL: entities: 17295, tick: 0.26ms, MTSync: 0.97ms 3",
    ])
    assert (s["ping_ms"], s["loss_pct"], s["bw_in_kbps"], s["bw_out_kbps"]) == (24.4, 0.0, 222.221, 50.556)
    assert (s["rl_entities"], s["rl_tick_ms"], s["rl_mtsync_ms"]) == (17295, 0.26, 0.97)


def test_parse_lines_that_look_alike_are_not_confused():
    s = parse_lines(["VRAM Demoted: 0, OSBudget: 15419 MB", "UniverseTime: Wed Dec 15 10:09:41 2990",
                     "Entities: 20536, PS: 0", "Phys: 0.0ms Stall: 0.0ms Event: 0.0ms"])
    assert all(v is None for k, v in s.items() if k != "ok")
    assert s["ok"] is False
    assert classify("Server FPS 21.8")[0] == "server_fps"
    assert classify("ServerTime: Thu")[0] == "server_time"
    assert classify("Server: pub-apse2a")[0] == "server"
    assert classify("FPS 106.3 [72")[0] == "fps"
    assert classify("Current pla")[0] == "location"
    # slips seen on small text: S read as 5, m read as n
    assert classify("FP5 101.8 [72..144]")[0] == "fps"
    assert classify("ServerTine: Thu")[0] == "server_time"
    assert classify("5ession: b36")[0] == "session"


def test_parse_ok_needs_server_fps_and_pop_or_ping():
    assert parse_lines(["Server FPS 21.8 [21.2..22.3] - 45.9ms [44.8..47.3], Hitches: 0"])["ok"] is False
    assert parse_lines(["Net: ping 24.4ms, loss 0.0% BwIn 1.000kbps, BwOut 1.000kbps"])["ok"] is False
    assert parse_lines(["Server FPS 21.8 [21.2..22.3] - 45.9ms [44.8..47.3], Hitches: 0",
                        "Net: ping 24.4ms, loss 0.0% BwIn 1.000kbps, BwOut 1.000kbps"])["ok"] is True
    assert parse_lines([])["ok"] is False
    assert parse_lines(["", "garbage", "|||"])["ok"] is False


def test_parse_drops_implausible_values():
    s = parse_lines(["Server FPS 21.8 [21.2..22.3] - 45.9ms [44.8..47.3], Hitches: 0",
                     "Net: ping 24.4ms, loss 400.0% BwIn 1.000kbps, BwOut 1.000kbps",
                     "VRAM(MB): 99250 / 15423"])
    assert s["loss_pct"] is None
    assert s["vram_used_mb"] is None and s["vram_total_mb"] is None


@pytest.mark.parametrize("raw", [
    "pub apse2a 12881860 090", "pub_apse2a_12881860_090", "pub apse2a_12881860 090",
    "pub-apse2a-12881860-090", "pubapse2a12881860090", "PUB APSE2A 1288186O O9O", "pub  apse2a 12881860  090 ",
])
def test_shard_id_normalised(raw):
    assert norm_shard_id(raw) == "pub_apse2a_12881860_090"


# --------------------------------------------------------------------------
# OverlayReader on the fixtures
# --------------------------------------------------------------------------

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")
pytest.importorskip("rapidocr")


def frame(name, size=None, width=3840):
    """Rebuild a full 4K frame (or a wider one) from a fixture crop, then
    optionally downscale it to another resolution."""
    crop = cv2.imread(str(FIX / name))
    assert crop is not None, name
    f = np.full((2160, width, 3), 18, np.uint8)
    f[0:crop.shape[0], width - crop.shape[1]:width] = crop
    if size:
        f = cv2.resize(f, size, interpolation=cv2.INTER_AREA)
    return f


@pytest.fixture(scope="module")
def reader():
    return OverlayReader()


def test_fixtures_have_no_session_info():
    for p in FIX.glob("overlay_*.jpg"):
        assert p.stat().st_size < 300_000, p.name
        img = cv2.imread(str(p))
        assert img.shape[1] <= 1600 and img.shape[0] <= 820, "fixtures must be crops, not full screenshots"


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_reader_4k(reader, name):
    reader.reset()
    s = reader.read(frame(name), ts=123.0)
    assert s["ok"] is True and s["ts"] == 123.0
    assert reader.last_path == "search"
    _assert_matches(s, EXPECTED[name])


def test_reader_fast_path_and_block_move():
    r = OverlayReader()
    s = r.read(frame("overlay_4k_1.jpg"))
    assert s["ok"] and r.last_path == "search"
    for name in ("overlay_4k_2.jpg", "overlay_4k_3.jpg"):
        s = r.read(frame(name))
        assert r.last_path == "fast"
        _assert_matches(s, EXPECTED[name])
    # QR code switched on: the block moves left, the cached position no longer
    # fits, and the reader must search again rather than return stale or cut-off text
    s = r.read(frame("overlay_4k_4_qr.jpg"))
    assert r.last_path == "search"
    _assert_matches(s, EXPECTED["overlay_4k_4_qr.jpg"])
    # and back again
    s = r.read(frame("overlay_4k_1.jpg"))
    assert r.last_path == "search"
    _assert_matches(s, EXPECTED["overlay_4k_1.jpg"])
    # the reader never holds on to a Session line
    assert "session" not in r._seen
    assert all("b360e83b" not in t for _, t, _ in r._seen.values())


def test_reader_unchanged_lines_are_reused():
    r = OverlayReader()
    f = frame("overlay_4k_2.jpg")
    r.read(f)
    calls = []
    orig = r._rec
    r._rec = lambda crops: calls.append(len(crops)) or orig(crops)
    s = r.read(f)
    assert r.last_path == "fast" and sum(calls) == 0
    _assert_matches(s, EXPECTED["overlay_4k_2.jpg"])


def test_reader_no_block_returns_quickly():
    r = OverlayReader()
    r.read(frame("overlay_4k_1.jpg"))                  # warm the models up
    r.reset()
    f = frame("overlay_4k_qr_only.jpg")
    t = time.perf_counter()
    s = r.read(f)
    took = time.perf_counter() - t
    assert s["ok"] is False and r.last_path is None
    assert all(s[k] is None for k in FIELDS)
    assert took < 3.0, f"no-overlay frame took {took:.2f}s"


@pytest.mark.parametrize("size", [(2560, 1440), (1920, 1080)])
@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_reader_lower_resolutions(reader, name, size):
    reader.reset()
    s = reader.read(frame(name, size=size))
    assert s["ok"] is True
    exp = EXPECTED[name]
    if size[1] >= 1440:
        _assert_matches(s, exp)
    else:
        # A 4K JPEG squeezed to 1080p leaves ~8 px text, where 0 and 8 blur
        # together (loss 0.0 -> 8.0, shard ..._090 -> ..._098). The core numbers
        # must be right and nearly everything else.
        _assert_matches(s, exp, CORE)
        right = sum(s[k] == v for k, v in exp.items())
        assert right >= len(exp) - 3, {k: (s[k], v) for k, v in exp.items() if s[k] != v}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_reader_ultrawide(reader, name):
    reader.reset()
    s = reader.read(frame(name, width=5120))          # 5120x2160, block at the right edge
    assert s["ok"] is True
    _assert_matches(s, EXPECTED[name])


def test_reader_rejects_bad_input(reader):
    for bad in (None, np.zeros((100, 100, 3), np.uint8), np.zeros((1080, 1920), np.uint8)):
        s = reader.read(bad)
        assert s["ok"] is False


@pytest.mark.parametrize("where", ["top-right", "centred", "top-left"])
def test_reader_game_smaller_than_screen(reader, where):
    """GitHub issue #2: the game drawn at 1440p on a 4K monitor. The text is 1440p-sized on a 4K screen, so the
    reader has to try the game's size, not just the screen's. Only the top-right of the screen is grabbed, as the
    companion does."""
    name = sorted(EXPECTED)[0]
    small = frame(name, size=(2560, 1440))
    big = np.zeros((2160, 3840, 3), np.uint8)
    y, x = {"top-right": (0, 3840 - 2560), "centred": (360, 640), "top-left": (0, 0)}[where]
    big[y:y + 1440, x:x + 2560] = small
    crop = big[0:int(2160 * 0.4), 1920:3840]
    f = np.zeros_like(big)
    f[0:crop.shape[0], 3840 - crop.shape[1]:] = crop
    reader.reset()
    old = reader.wide_search_every
    reader.wide_search_every = 0
    try:
        for _ in range(3):
            s = reader.read(f)
            if s["ok"]:
                break
    finally:
        reader.wide_search_every = old
    assert s["ok"] is True
    _assert_matches(s, EXPECTED[name], CORE)


def test_ptu_long_server_line_at_1440p():
    """4.10.3 PTU at 2560x1440 (Ray, 7 Nov): the text stays near its 4K size and the Server line starts left of the
    search area, so its label was cut off and the server and its player counts were never read. The rows that run
    off the area's left edge get a second look at a strip to their left; the rest of the search is unchanged."""
    crop = cv2.imread(str(FIX / "overlay_ptu_1440_long_server.jpg"))
    f = np.full((1440, 2560, 3), 18, np.uint8)
    f[0:crop.shape[0], 2560 - crop.shape[1]:] = crop
    r = OverlayReader()
    s = r.read(f)
    assert s["ok"]
    assert s["server_name"] == "ptu-use1b-sc-alpha-4100-13132336-game-09"
    assert (s["pop_shard"], s["pop_srv"]) == (96, 16)
    assert s["server_fps"] == 30.0 and s["shard_id"] == "ptu_use1b_13132336_010"
    s = r.read(f)                       # and again from the remembered position
    assert r.last_path == "fast" and s["server_name"] == "ptu-use1b-sc-alpha-4100-13132336-game-09"


@pytest.mark.parametrize("raw,want", [
    ("ptu-uselb-sc-alpha-4100-13132336-game-09", "ptu-use1b-sc-alpha-4100-13132336-game-09"),
    ("pub-apse2a-sc-alphal4102-12974691-game-11", "pub-apse2a-sc-alpha-4102-12974691-game-11"),
    ("pub-apse2a-scalpha4102-12974691-game-11", "pub-apse2a-sc-alpha-4102-12974691-game-11"),
    ("pub-apse2a-sg-alpha-4102-129746911game-11", "pub-apse2a-sc-alpha-4102-12974691-game-11"),
    ("ptu-use1b-sc-alpha-4100-13132336game-09", "ptu-use1b-sc-alpha-4100-13132336-game-09"),
    ("pub-apse2a-sc-alpha-4102-12974691-gamme-55", "pub-apse2a-sc-alpha-4102-12974691-game-55"),
    ("pubeapse2a-sc-alpha-4102-12974691-game-33", None),          # env and region run together: no guess
])
def test_server_name_misreads_put_back_in_shape(raw, want):
    """Real misreads from Ray's readings (LAB and LIVE, Oct to Nov 2026): 219 readings had a server name with a
    dash dropped or a letter for a digit, each counted as another server."""
    from scstatus.overlay import norm_server_name
    assert norm_server_name(raw) == want


def test_a_guessed_region_needs_the_shard_to_agree():
    from scstatus.overlay import parse_lines
    line = "Server: ptu-uselpsc-alpha-4100-13132336-game-09, restarts 0, pop. [shard 113, srv 25]"
    assert parse_lines([line])["server_name"] is None
    s = parse_lines(["ShardId: ptu use1b 13132336 010", "Server: ptu-uselbralpha-4100-13132336-game-09, restarts 0, pop. [shard 113, srv 25]"])
    assert s["server_name"] == "ptu-use1b-sc-alpha-4100-13132336-game-09" and s["pop_srv"] == 25
    assert "_server_unsure" not in s


def test_ink_mask_keeps_the_overlays_own_text_and_drops_tinted_banners():
    """The overlay draws white, yellow, orange and red text with a black drop shadow down and to the right; the
    ship banner and pop-ups are tinted (cyan, blue, green) and have no such shadow."""
    from scstatus.overlay import ink_mask
    img = np.full((40, 120, 3), 40, np.uint8)
    img[10:14, 10:30] = (235, 235, 235)          # white overlay stroke...
    img[14:17, 13:33] = 0                         # ...with its shadow below and right
    img[10:14, 50:70] = (0, 165, 255)             # orange (BGR)
    img[14:17, 53:73] = 0
    img[10:14, 90:110] = (235, 220, 90)           # cyan banner stroke, shadowed or not, is dropped
    img[14:17, 93:113] = 0
    m = ink_mask(img)
    assert m[10:14, 10:30].any() and m[10:14, 50:70].any()
    assert not m[:, 85:].any()


def test_second_look_only_fills_gaps_and_checks_them():
    """A second look through the banner never replaces a value already read, never takes hitches, the location or
    the shard id, and keeps server fps only when it agrees with its own frame time."""
    from scstatus.overlay import INK_FIELDS, OverlayReader
    assert "shard" not in INK_FIELDS and "location" not in INK_FIELDS and INK_FIELDS["server"] == ("server_name",)
    assert all("hitches" not in v for v in INK_FIELDS.values())
    r = OverlayReader()
    img = np.zeros((400, 800, 3), np.uint8)
    blk = {"pitch": 19.3, "right": 780.0, "rect": (100.0, 0.0, 790.0, 300.0)}
    rows = [("server_fps", 300.0, 100.0), ("net", 300.0, 140.0)]
    answers = iter([["Server FPS 50.0 [49.0..51.0] - 33.3ms [32.0..34.0], Hitches: 9",
                     "Net: ping 31.0ms, loss 0.0% BwIn 1.0kbps, BwOut 1.0kbps"], ["Server FPS 50.0 - 33.3ms"]])
    r._rec = lambda crops: next(answers)
    snap = {"server_fps": None, "server_ms": None, "hitches": None, "ping_ms": 24.4, "loss_pct": None,
            "pop_shard": 400, "pop_srv": None}
    fixed = r._ink_look(img, blk, rows, {}, snap)
    assert snap["server_fps"] is None and snap["server_ms"] is None      # 50 fps is 20 ms, not 33.3: dropped
    assert snap["hitches"] is None
    assert snap["ping_ms"] == 24.4 and snap["loss_pct"] == 0.0 and fixed == {"net"}


def test_a_reading_through_a_banner_leaves_out_what_pop_ups_cover():
    from scstatus.overlay import _banner_drop
    snap = {"server_fps": 11.0, "server_ms": 90.6, "ping_ms": 26.3, "pop_shard": 330, "pop_srv": 53, "hitches": 0,
            "location": "locatioh__Stantonla", "shard_id": "pub_apse2a_12881860_090", "server_name": "x", "ok": True}
    _banner_drop(snap)
    assert snap["ok"] and snap["server_fps"] == 11.0 and snap["ping_ms"] == 26.3 and snap["server_name"] == "x"
    assert all(snap[f] is None for f in ("pop_shard", "pop_srv", "hitches", "location", "shard_id"))
    snap = {"server_fps": 11.0, "ping_ms": None, "pop_shard": 330}
    _banner_drop(snap)
    assert snap["ok"] is False              # fps alone isn't a reading
