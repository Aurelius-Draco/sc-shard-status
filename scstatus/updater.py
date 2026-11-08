"""Telling players about a new version, and installing it with one click.

Checks GitHub's latest release a minute after start and then every 6 hours, but only once the player has answered
the update question in set-up and said yes (check_updates). Before that, nothing is asked of GitHub.
The installed app (SC Shard Status.exe) can update itself: it downloads SC-Shard-Status-Setup-<version>.exe from the
release, checks it against the .sha256 file published beside it, runs it silently and closes. The installer puts the
new version in place and starts it again. A zip copy just gets a link to the download page."""

import hashlib
import json
import os
import re
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from .config import APP_NAME, FROZEN, GITHUB_COPY, REPO, STORE, STORE_URL, TEST_BUILD, TEST_DIR, VERSION, say

API = "https://api.github.com/repos/Aurelius-Draco/sc-shard-status/releases/latest"
# The TEST copy: the pre-release the installer workflow keeps for the newest next build (never offered to players:
# releases/latest skips pre-releases)
TEST_API = "https://api.github.com/repos/Aurelius-Draco/sc-shard-status/releases/tags/test-next"
TEST_ZIP_RX = re.compile(r"^Verse-Shards-test-[\d.]+-([0-9a-f]{7})\.zip$")
TEST_EVERY_S = 30 * 60
DOWNLOAD_PAGE = "https://verseshards.com/app"
SETUP_RX = re.compile(r"^SC-Shard-Status-Setup-(\d+(?:\.\d+)*)\.exe$")
FIRST_CHECK_S = 60
EVERY_S = 6 * 3600
ASKED_IN = 2            # the set-up version that brought the update question (App.QUESTIONS["updates"])


def vtuple(v):
    """'v1.2.10' -> (1, 2, 10). Anything unreadable sorts lowest."""
    nums = re.findall(r"\d+", str(v or ""))
    return tuple(int(n) for n in nums[:4]) or (0,)


def newer(a, b):
    return vtuple(a) > vtuple(b)


def parse_release(rel):
    """The bits of GitHub's release JSON the app needs."""
    tag = rel.get("tag_name") or ""
    out = {"version": tag.lstrip("vV"), "tag": tag, "url": rel.get("html_url") or REPO + "/releases/latest",
           "notes": (rel.get("body") or "")[:4000], "published": rel.get("published_at"),
           "setup_url": None, "setup_name": None, "setup_size": None, "sha_url": None}
    for a in rel.get("assets") or []:
        name = a.get("name") or ""
        if SETUP_RX.match(name):
            out.update(setup_url=a.get("browser_download_url"), setup_name=name, setup_size=a.get("size"))
    if out["setup_name"]:
        for a in rel.get("assets") or []:
            if a.get("name") == out["setup_name"] + ".sha256":
                out["sha_url"] = a.get("browser_download_url")
    return out


def parse_test_release(rel):
    """The test-next pre-release: its zip, the zip's checksum, the build (commit) it is, and the changes listed."""
    out = {"version": None, "build": None, "tag": rel.get("tag_name"), "url": rel.get("html_url"),
           "notes": (rel.get("body") or "")[:4000], "published": rel.get("published_at"),
           "setup_url": None, "setup_name": None, "setup_size": None, "sha_url": None}
    for a in rel.get("assets") or []:
        m = TEST_ZIP_RX.match(a.get("name") or "")
        if m:
            out.update(setup_url=a.get("browser_download_url"), setup_name=a["name"], setup_size=a.get("size"),
                       build=m.group(1), version=f"TEST next {m.group(1)}")
    for a in rel.get("assets") or []:
        if out["setup_name"] and a.get("name") == out["setup_name"] + ".sha256":
            out["sha_url"] = a.get("browser_download_url")
    return out


def _get(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{VERSION}",
                                               "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)


def _exists(p):
    try:
        return Path(p).exists()
    except OSError:
        return False


class Updater:
    def __init__(self, app, version=VERSION, frozen=FROZEN, store=STORE, test_dir=TEST_DIR, test_build=TEST_BUILD):
        self.app = app
        self.store = store           # the Microsoft Store version: the Store installs updates, so this never checks
        self.test_dir = test_dir if test_build else None      # a TEST copy: updates from the test-next pre-release
        self.test_build = test_build
        self.version = f"TEST next {test_build}" if self.test_dir else version
        self.frozen = frozen
        self.latest = None
        self.checked_at = None
        self.error = None
        self.state = "idle"          # idle, checking, downloading, verifying, starting installer, failed
        self.progress = 0.0
        self.lock = threading.Lock()

    @property
    def asked(self):
        """Whether the player has answered the update question in set-up yet."""
        since = (getattr(self.app, "QUESTIONS", None) or {}).get("updates", ASKED_IN)
        return int(self.app.cfg.get("setup_version") or 0) >= since

    @property
    def enabled(self):
        """On only once the update question is answered, and answered yes. This also covers the About tab's star
        count, which asks GitHub too."""
        if self.test_dir:
            return True                  # Ray's TEST copy always looks for the newest test build
        return not self.store and self.asked and bool(self.app.cfg.get("check_updates", True))

    def run(self, stop):
        if stop.wait(FIRST_CHECK_S):
            return
        while not stop.is_set():
            if self.enabled:
                self.check()
            if stop.wait(TEST_EVERY_S if self.test_dir else EVERY_S):
                return

    def check(self):
        if self.store:
            return self.info()
        with self.lock:
            if self.state in ("downloading", "verifying", "starting installer"):
                return self.info()
            self.state = "checking"
        try:
            if self.test_dir:
                with _get(TEST_API) as r:
                    self.latest = parse_test_release(json.loads(r.read().decode("utf-8")))
            else:
                with _get(API) as r:
                    self.latest = parse_release(json.loads(r.read().decode("utf-8")))
            self.error = None
            if self.available:
                say(f"Version {self.latest['version']} is out (you have {self.version}). Update from the dashboard.")
        except Exception as e:
            self.error = f"Couldn't check for updates ({e.__class__.__name__})"
        finally:
            self.checked_at = time.time()
            with self.lock:
                if self.state == "checking":
                    self.state = "idle"
        return self.info()

    @property
    def available(self):
        if self.test_dir:
            return bool(self.latest and self.latest.get("build") and self.latest["build"] != self.test_build)
        return bool(self.latest and newer(self.latest["version"], self.version))

    def info(self):
        L = self.latest or {}
        return {"current": self.version, "enabled": self.enabled, "checked_at": self.checked_at, "error": self.error,
                "available": self.available, "latest": L.get("version"), "url": L.get("url"),
                "notes": L.get("notes") if self.available else None, "published": L.get("published"),
                "can_install": bool(self.frozen and not self.store and self.available and L.get("setup_url") and L.get("sha_url")),
                "store": self.store, "store_url": STORE_URL,
                "github_copy": bool(self.store and _exists(GITHUB_COPY)),
                "installed_app": self.frozen, "download_page": DOWNLOAD_PAGE, "test": bool(self.test_dir),
                "state": self.state, "progress": round(self.progress, 3)}

    # -- installing
    def install(self, quit_app):
        """Download, check and run the new installer, then call quit_app() so the installer can replace the files."""
        info = self.info()
        if not info["can_install"]:
            raise ValueError("Nothing to install. " + ("This copy was unzipped by hand, so download the installer "
                                                       "from the site once." if not self.frozen else
                                                       "No newer version found."))
        with self.lock:
            if self.state in ("downloading", "verifying", "starting installer"):
                return self.info()
            self.state, self.progress, self.error = "downloading", 0.0, None
        target = self._install_test if self.test_dir else self._install
        threading.Thread(target=target, args=(dict(self.latest), quit_app), daemon=True).start()
        return self.info()

    def _download(self, L, dest):
        """Download L's file to dest, checking it against its .sha256."""
        with _get(L["sha_url"]) as r:
            want = r.read().decode("utf-8", "ignore").split()[0].strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", want):
            raise ValueError("the checksum file is not right")
        h = hashlib.sha256()
        with _get(L["setup_url"], timeout=60) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length") or L.get("setup_size") or 0)
            done = 0
            while True:
                chunk = r.read(256 * 1024)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if total:
                    self.progress = min(done / total, 1.0)
        self.state = "verifying"
        if h.hexdigest() != want:
            Path(dest).unlink(missing_ok=True)
            raise ValueError("the download didn't match its checksum, so it wasn't used")

    def _install_test(self, L, quit_app):
        """TEST copy: unpack the new build beside the running one (app-<build>), point the launcher at it, and start
        it a few seconds after this copy closes. The old build's folder is left for Ray to delete."""
        import zipfile
        try:
            base = Path(self.test_dir)
            zpath = base / L["setup_name"]
            self._download(L, zpath)
            self.state = "unpacking"
            dest = base / f"app-{L['build']}"
            with zipfile.ZipFile(zpath) as z:
                z.extractall(dest)
            if not (dest / "SC Shard Status.exe").exists():
                raise ValueError("the test build's zip doesn't hold the app")
            write_test_launcher(base, L["build"])
            self.state = "starting installer"
            say(f"Updating the TEST copy to next {L['build']}. It closes now and starts again in a few seconds.")
            if os.name == "nt":
                flags = 0x00000008 | 0x00000200
                cmd = base / "Start Verse Shards TEST.cmd"
                subprocess.Popen(["cmd", "/c", f'timeout /t 4 /nobreak >nul & "{cmd}"'], creationflags=flags, close_fds=True)
            time.sleep(1.5)
            quit_app()
        except Exception as e:
            self.state = "failed"
            self.error = f"Update failed: {e}"
            say(self.error)

    def _install(self, L, quit_app):
        try:
            folder = Path(tempfile.mkdtemp(prefix="scss-update-"))
            exe = folder / L["setup_name"]
            with _get(L["sha_url"]) as r:
                want = r.read().decode("utf-8", "ignore").split()[0].strip().lower()
            if not re.fullmatch(r"[0-9a-f]{64}", want):
                raise ValueError("the checksum file is not right")
            h = hashlib.sha256()
            with _get(L["setup_url"], timeout=60) as r, open(exe, "wb") as f:
                total = int(r.headers.get("Content-Length") or L.get("setup_size") or 0)
                done = 0
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if total:
                        self.progress = min(done / total, 1.0)
            self.state = "verifying"
            if h.hexdigest() != want:
                exe.unlink(missing_ok=True)
                raise ValueError("the download didn't match its checksum, so it wasn't run")
            self.state = "starting installer"
            say(f"Installing version {L['version']}. The app closes now and starts again when it's done.")
            flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0     # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            subprocess.Popen([str(exe), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                              f"/LOG={folder / 'install.log'}"], creationflags=flags, close_fds=True)
            time.sleep(1.5)            # let the dashboard show "starting installer" before the app goes
            quit_app()
        except Exception as e:
            self.state = "failed"
            self.error = f"Update failed: {e}"
            say(self.error + ". Download it from " + DOWNLOAD_PAGE + " instead.")


def write_test_launcher(base, build):
    """The TEST copy's launcher: its own data folder and port (in data\\config.json), its label and build, and the
    app folder for that build."""
    text = ("@echo off\r\n"
            "rem Verse Shards TEST: a build from next, run beside the installed app with its own data (data\\) and port (8795).\r\n"
            "rem Written by the TEST copy when it updates itself.\r\n"
            'set "SCSTATUS_DATA=%~dp0data"\r\n'
            'set "SCSTATUS_TEST_DIR=%~dp0"\r\n'
            f'set "SCSTATUS_BUILD={build}"\r\n'
            f'set "SCSTATUS_LABEL=TEST next {build}"\r\n'
            f'start "" "%~dp0app-{build}\\SC Shard Status.exe"\r\n')
    Path(base, "Start Verse Shards TEST.cmd").write_bytes(text.encode("ascii"))
