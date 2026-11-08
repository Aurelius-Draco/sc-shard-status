"""9 Nov: overlay reading follows the game's window to whichever monitor it's on (players with the game on their
second screen got "overlay off" because only monitor 1 was read)."""
import numpy as np

from scstatus import capture

# Two 4K screens side by side, the main one on the left
MONS = [{"left": 0, "top": 0, "width": 7680, "height": 2160},
        {"left": 0, "top": 0, "width": 3840, "height": 2160},
        {"left": 3840, "top": 0, "width": 3840, "height": 2160}]


def test_game_on_the_second_screen_is_read_there():
    region, size, how = capture.pick_area(MONS, 1, (3840, 0, 3840, 2160))
    assert how == "window" and size == (3840, 2160)
    assert region == {"left": 3840 + 1920, "top": 0, "width": 1920, "height": 864}


def test_screen_on_the_left_with_negative_coordinates():
    mons = [{"left": -2560, "top": 0, "width": 6400, "height": 2160},
            {"left": 0, "top": 0, "width": 3840, "height": 2160},
            {"left": -2560, "top": 0, "width": 2560, "height": 1440}]
    region, size, how = capture.pick_area(mons, 1, (-2560, 0, 2560, 1440))
    assert how == "window" and size == (2560, 1440) and region["left"] == -1280


def test_windowed_game_reads_its_own_window():
    region, size, how = capture.pick_area(MONS, 1, (200, 100, 1920, 1080))
    assert how == "window" and size == (1920, 1080)
    assert region == {"left": 200 + 960, "top": 100, "width": 960, "height": 432}


def test_no_window_falls_back_to_the_monitor_in_config():
    assert capture.pick_area(MONS, 1, None)[1:] == ((3840, 2160), "monitor")
    assert capture.pick_area(MONS, 2, None)[0]["left"] == 3840 + 1920
    # a nonsense window (tiny, or off the desktop) falls back too
    assert capture.pick_area(MONS, 1, (0, 0, 300, 200))[2] == "monitor"
    assert capture.pick_area(MONS, 1, (99999, 0, 1920, 1080))[2] == "monitor"


def test_window_a_little_off_the_edge_is_clipped():
    region, size, how = capture.pick_area(MONS, 1, (-4, -4, 3848, 2168))
    assert how == "window" and size == (3840, 2160) and region["left"] == 1920


class FakeSct:
    def __init__(self, mons):
        self.monitors = mons
        self.asked = []

    def grab(self, region):
        self.asked.append(region)
        return np.zeros((region["height"], region["width"], 4), dtype=np.uint8)


def test_grabber_uses_the_window():
    sct = FakeSct(MONS)
    grab = capture.make_grabber(1, sct=sct)
    img, size = grab((3840, 0, 3840, 2160))
    assert size == (3840, 2160) and img.shape == (864, 1920, 3) and sct.asked[-1]["left"] == 5760
    assert grab.how == "window"
    img, size = grab(None)
    assert sct.asked[-1]["left"] == 1920 and grab.how == "monitor"


def test_tick_passes_the_game_window(monkeypatch):
    seen = {}
    w = capture.OverlayWatcher()

    class R:
        def read(self, frame):
            seen["frame"] = frame.shape
            return {"ok": True}
    w.reader = R()
    w.grab = lambda rect: (seen.setdefault("rect", rect), (np.zeros((864, 1920, 3), np.uint8), (3840, 2160)))[1]
    monkeypatch.setattr(capture, "game_in_front", lambda: True)
    monkeypatch.setattr(capture, "game_rect", lambda: (3840, 0, 3840, 2160))
    w.tick()
    assert seen["rect"] == (3840, 0, 3840, 2160) and seen["frame"] == (2160, 3840, 3) and w.screen == "3840x2160"
