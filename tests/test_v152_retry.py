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
