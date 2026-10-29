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
