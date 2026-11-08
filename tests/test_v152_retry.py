"""The update download tries again when GitHub answers 502/503/504 for a moment (Ray's TEST copy, 8 Nov)."""
import hashlib
import io
import urllib.error

from scstatus import updater


class _Resp(io.BytesIO):
    def __init__(self, data):
        super().__init__(data)
        self.headers = {"Content-Length": str(len(data))}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _setup(monkeypatch, fails, code=504):
    data = b"x" * 1000
    calls = {"n": 0}

    def fake_get(url, timeout=20):
        if url.endswith(".sha256"):
            return _Resp((hashlib.sha256(data).hexdigest() + "  f.zip\n").encode())
        calls["n"] += 1
        if calls["n"] <= fails:
            raise urllib.error.HTTPError(url, code, "Gateway Time-out", {}, None)
        return _Resp(data)

    monkeypatch.setattr(updater, "_get", fake_get)
    monkeypatch.setattr(updater, "RETRY_WAIT_S", 0)
    return calls


def _u():
    u = updater.Updater.__new__(updater.Updater)
    u.progress, u.state = 0.0, "downloading"
    return u


def test_a_504_is_tried_again_and_the_download_finishes(monkeypatch, tmp_path):
    calls = _setup(monkeypatch, fails=2)
    _u()._download({"sha_url": "https://x/f.zip.sha256", "setup_url": "https://x/f.zip"}, tmp_path / "f.zip")
    assert calls["n"] == 3
    assert (tmp_path / "f.zip").stat().st_size == 1000


def test_it_gives_up_after_four_tries(monkeypatch, tmp_path):
    calls = _setup(monkeypatch, fails=10)
    try:
        _u()._download({"sha_url": "https://x/f.zip.sha256", "setup_url": "https://x/f.zip"}, tmp_path / "f.zip")
        raise AssertionError("should have failed")
    except urllib.error.HTTPError as e:
        assert e.code == 504
    assert calls["n"] == updater.RETRIES


def test_a_404_is_not_retried(monkeypatch, tmp_path):
    calls = _setup(monkeypatch, fails=10, code=404)
    try:
        _u()._download({"sha_url": "https://x/f.zip.sha256", "setup_url": "https://x/f.zip"}, tmp_path / "f.zip")
    except urllib.error.HTTPError:
        pass
    assert calls["n"] == 1


def test_release_files_come_through_the_api_address_with_the_download_link_kept_as_second_choice():
    rel = {"tag_name": "test-next", "assets": [
        {"name": "Verse-Shards-test-1.5.1-abc1234.zip", "size": 10,
         "url": "https://api.github.com/repos/Aurelius-Draco/sc-shard-status/releases/assets/1",
         "browser_download_url": "https://github.com/Aurelius-Draco/sc-shard-status/releases/download/test-next/Verse-Shards-test-1.5.1-abc1234.zip"},
        {"name": "Verse-Shards-test-1.5.1-abc1234.zip.sha256", "size": 1,
         "url": "https://api.github.com/repos/Aurelius-Draco/sc-shard-status/releases/assets/2",
         "browser_download_url": "https://github.com/x/sha"}]}
    L = updater.parse_test_release(rel)
    assert L["setup_url"].endswith("/releases/assets/1") and L["setup_alt"].startswith("https://github.com/")
    assert L["sha_url"].endswith("/releases/assets/2") and L["sha_alt"] == "https://github.com/x/sha"


def test_the_api_address_is_asked_for_the_file_itself(monkeypatch):
    seen = {}

    def fake_open(req, timeout=20):
        seen["accept"] = req.get_header("Accept")
        return None
    monkeypatch.setattr(updater.urllib.request, "urlopen", fake_open)
    updater._get("https://api.github.com/repos/a/b/releases/assets/9")
    assert seen["accept"] == "application/octet-stream"
    updater._get("https://api.github.com/repos/a/b/releases/latest")
    assert seen["accept"] == "application/vnd.github+json"


def test_a_failed_try_switches_between_the_two_addresses(monkeypatch, tmp_path):
    data, tried = b"y" * 50, []

    def fake_get(url, timeout=20):
        tried.append(url)
        if url.endswith("sha"):
            return _Resp((hashlib.sha256(data).hexdigest() + "\n").encode())
        if url == "https://api/zip":
            raise urllib.error.HTTPError(url, 504, "x", {}, None)
        return _Resp(data)
    monkeypatch.setattr(updater, "_get", fake_get)
    monkeypatch.setattr(updater, "RETRY_WAIT_S", 0)
    _u()._download({"setup_url": "https://api/zip", "setup_alt": "https://gh/zip", "sha_url": "https://api/sha", "sha_alt": "https://gh/sha"}, tmp_path / "z")
    assert [u for u in tried if "zip" in u] == ["https://api/zip", "https://gh/zip"]
