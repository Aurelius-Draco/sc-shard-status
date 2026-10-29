import hashlib
import http.server
import json
import threading
import time

from scstatus import migrate, updater


def _release(ver, with_setup=True, with_sha=True, base="https://example.invalid/"):
    assets = [{"name": f"SC-Shard-Status-{ver}.zip", "browser_download_url": base + "zip", "size": 10}]
    if with_setup:
        assets.append({"name": f"SC-Shard-Status-Setup-{ver}.exe", "browser_download_url": base + "setup", "size": 7})
    if with_sha:
        assets.append({"name": f"SC-Shard-Status-Setup-{ver}.exe.sha256", "browser_download_url": base + "sha"})
    return {"tag_name": "v" + ver, "html_url": "https://github.com/x/releases/tag/v" + ver, "body": "notes",
            "published_at": "2026-11-01T00:00:00Z", "assets": assets}


class _App:
    def __init__(self, **cfg):
        self.cfg = dict(check_updates=True, **cfg)


def test_versions_compare_as_numbers():
    assert updater.newer("1.0.10", "1.0.9") and updater.newer("v1.1", "1.0.1") and not updater.newer("1.0.1", "1.0.1")
    assert not updater.newer("", "1.0") and updater.vtuple("v2.3.4") == (2, 3, 4)


def test_release_parsing_and_what_the_dashboard_sees():
    u = updater.Updater(_App(), version="1.0.1", frozen=True)
    u.latest = updater.parse_release(_release("1.1.0"))
    i = u.info()
    assert i["available"] and i["can_install"] and i["latest"] == "1.1.0" and i["notes"] == "notes"
    # A zip copy is told about it but sent to the download page
    z = updater.Updater(_App(), version="1.0.1", frozen=False)
    z.latest = u.latest
    assert z.info()["available"] and not z.info()["can_install"]
    # No checksum published: never installs
    u.latest = updater.parse_release(_release("1.1.0", with_sha=False))
    assert not u.info()["can_install"]
    # Same version: nothing to do
    u.latest = updater.parse_release(_release("1.0.1"))
    assert not u.info()["available"] and u.info()["notes"] is None


def _serve(files):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = files.get(self.path.lstrip("/"))
            if body is None:
                self.send_response(404); self.end_headers(); return
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}/"


def _wait(u, states, s=5):
    end = time.time() + s
    while u.state not in states and time.time() < end:
        time.sleep(0.05)


def test_install_checks_the_download_then_runs_it_and_closes(monkeypatch):
    exe = b"MZ fake installer"
    srv, base = _serve({"setup": exe, "sha": (hashlib.sha256(exe).hexdigest() + "  x.exe\n").encode()})
    ran, quit_called = [], []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda args, **kw: ran.append(args))
    monkeypatch.setattr(updater.time, "sleep", lambda s: None)
    try:
        u = updater.Updater(_App(), version="1.0.1", frozen=True)
        u.latest = updater.parse_release(_release("1.1.0", base=base))
        u.install(lambda: quit_called.append(1))
        _wait(u, ("starting installer", "failed"))
        end = time.time() + 5
        while not quit_called and time.time() < end:
            time.sleep(0.05)
        assert u.state == "starting installer" and quit_called and u.progress == 1.0
        assert ran[0][0].endswith("SC-Shard-Status-Setup-1.1.0.exe") and "/SILENT" in ran[0]
    finally:
        srv.shutdown()


def test_a_download_that_doesnt_match_is_never_run(monkeypatch):
    srv, base = _serve({"setup": b"tampered", "sha": ("0" * 64).encode()})
    ran = []
    monkeypatch.setattr(updater.subprocess, "Popen", lambda args, **kw: ran.append(args))
    try:
        u = updater.Updater(_App(), version="1.0.1", frozen=True)
        u.latest = updater.parse_release(_release("1.1.0", base=base))
        u.install(lambda: None)
        _wait(u, ("failed",))
        assert u.state == "failed" and "checksum" in u.error and not ran
    finally:
        srv.shutdown()


def test_zip_copy_settings_come_across_to_the_installed_app(tmp_path):
    home = tmp_path / "home"
    old = home / "Downloads" / "SC-Shard-Status (1)"
    (old / "scstatus").mkdir(parents=True)
    (old / "status.py").write_text("")
    (old / "data" / "reports" / "r1").mkdir(parents=True)
    (old / "data" / "config.json").write_text('{"game_dir": "D:\\Games\\StarCitizen\\LIVE", "share_readings": true}')
    (old / "data" / "status.db").write_bytes(b"db")
    data = tmp_path / "LocalAppData" / "SC Shard Status"
    assert migrate.migrate_old_install(data, home=home, drives=False) == old
    cfg = json.loads((data / "config.json").read_text())
    assert cfg["game_dir"] == "D:\\Games\\StarCitizen\\LIVE" and cfg["share_readings"] is True
    assert cfg["migrated_from"] == str(old) and (data / "status.db").read_bytes() == b"db"
    assert (data / "reports" / "r1").is_dir()


def test_old_copy_found_through_its_shortcut(tmp_path, monkeypatch):
    home = tmp_path / "home"
    old = tmp_path / "Games" / "StarCitizen" / "SC-Shard-Status"
    (old / "scstatus").mkdir(parents=True)
    (old / "status.py").write_text("")
    (old / "data").mkdir()
    (old / "data" / "config.json").write_text("{}")
    (home / "Desktop").mkdir(parents=True)
    # Shortcut targets are stored as Windows paths; stand the temp folder in for a drive
    fake = "C:\\Games\\StarCitizen\\SC-Shard-Status\\launchers\\status.bat"
    (home / "Desktop" / "SC Shard Status.lnk").write_bytes(b"\x4c\x00junk" + fake.encode("utf-16-le") + b"\x00\x00")
    monkeypatch.setattr(migrate, "is_zip_copy", lambda p: str(p) == "C:\\Games\\StarCitizen\\SC-Shard-Status")
    assert [str(p) for p in migrate.from_shortcuts(home)] == ["C:\\Games\\StarCitizen\\SC-Shard-Status"]
    assert migrate.from_shortcuts(tmp_path / "nobody") == []
