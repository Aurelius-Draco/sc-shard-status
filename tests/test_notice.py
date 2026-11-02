"""Message of the week: shown on Now from the board the app already downloads, only with "Show other shards" on,
only https links, until its end date or until Hide (which hides that one message)."""
import time

from scstatus import app as appmod, config


def _app(tmp_path, monkeypatch, board=True):
    for mod in (appmod, config):
        monkeypatch.setattr(mod, "DATA", tmp_path / "data")
    monkeypatch.setattr(config, "save_setting", lambda k, v: None)
    cfg = dict(config.DEFAULT_CONFIG, game_dir=str(tmp_path / "nogame"), open_browser=False, community_board=board)
    return appmod.App(cfg)


def _notice(**k):
    return {"id": "a1b2c3d4", "text": "Help us ask CIG for overlay numbers in Game.log.", "label": "Upvote on Spectrum",
            "url": "https://robertsspaceindustries.com/spectrum/community/SC/forum/50259/thread/x/575752", "ends": time.time() + 3600, **k}


def test_notice_shows_and_hides(tmp_path, monkeypatch):
    a = _app(tmp_path, monkeypatch)
    a.community.board = {"regions": [], "notice": _notice()}
    n = a.notice_state()
    assert n["label"] == "Upvote on Spectrum" and n["url"].startswith("https://robertsspaceindustries.com/")
    assert a.dismiss("notice") == "OK."
    assert a.notice_state() is None
    a.community.board = {"regions": [], "notice": _notice(id="ffff0000", text="A new one")}
    assert a.notice_state()["text"] == "A new one", "Hide hides that message only"


def test_notice_needs_the_board_setting_https_and_a_future_end(tmp_path, monkeypatch):
    a = _app(tmp_path, monkeypatch, board=False)
    a.community.board = {"notice": _notice()}
    assert a.notice_state() is None
    a = _app(tmp_path, monkeypatch)
    for bad in (_notice(url="http://example.com"), _notice(url="javascript:alert(1)"), _notice(ends=time.time() - 1), _notice(text=""), "nope"):
        a.community.board = {"notice": bad}
        assert a.notice_state() is None
    a.community.board = None
    assert a.notice_state() is None
