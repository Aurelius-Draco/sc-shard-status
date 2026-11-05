"""1.5.0: a copy reading a PTU (or other test) folder shares nothing; LIVE readings say they're LIVE."""
from pathlib import Path

import pytest

from scstatus import community, config, groups


def test_channel_comes_from_the_game_folder():
    assert config.channel_of(Path(r"C:/Games/StarCitizen/StarCitizen/LIVE")) == "LIVE"
    assert config.channel_of(Path(r"C:/Games/StarCitizen/StarCitizen/PTU")) == "PTU"
    assert config.channel_of(Path(r"D:/sc/eptu")) == "EPTU"
    assert config.channel_of(Path(r"D:/Star Citizen")) == "LIVE"
    assert config.channel_of(None) == "LIVE"


def test_reports_say_their_channel():
    snap = {"ts": 1793786400, "shard_id": "pub_use1b_12881860_090", "server_name": "pub-use1b-sc-alpha-game-07", "server_fps": 20}
    assert community.shard_report(snap, "a1b2c3d4e5f60718", "13107423")["channel"] == "LIVE"
    assert community.shard_report(snap, "a1b2c3d4e5f60718", "13107423", channel="PTU")["channel"] == "PTU"


class _Store:
    def install_id(self):
        return "a1b2c3d4e5f60718"


class _App:
    def __init__(self, ch):
        self.channel = ch
        self.cfg = {"share_readings": True, "community_board": False}
        self.store = _Store()
        self.snaps = []
        self.lock = __import__("threading").Lock()
        self.last_result = None
        self.game_dir = Path("PTU")


def test_ptu_copy_shares_nothing_and_says_why(monkeypatch):
    sent = []
    c = community.Community.__new__(community.Community)
    c.app, c.url, c.version = _App("PTU"), "https://example.test", "1.5.0"
    c.rsi_at = c.sessions_at = c.board_at = c.posts_at = c.fed_at = c.sent_at = c.retry_at = 0
    c._req = lambda path, body=None: sent.append(path) or (200, {})
    c.fetch_fed = lambda: None
    c.tick(now=10_000)
    assert "/api/v1/sessions" not in sent and "/api/v1/report" not in sent
    assert c.share_status.startswith("paused: this copy reads a test server (PTU)")


def test_no_group_posts_from_a_test_server():
    g = groups.Groups.__new__(groups.Groups)
    g.app = _App("PTU")
    with pytest.raises(ValueError, match="LIVE servers"):
        g.post("lfg", "Vanduul Incursion")
