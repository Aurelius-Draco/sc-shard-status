"""Settings, folders and small helpers shared by every part of SC Shard Status."""

import datetime as dt
import json
import os
import re
import string
import sys
from pathlib import Path

VERSION = "1.1.0"
# The public community board (Cloudflare Worker in the admin repo)
COMMUNITY_URL = "https://verseshards.com"
APP_NAME = "SC Shard Status"
AUTHOR = "Aurelius_Draco"
REPO = "https://github.com/Aurelius-Draco/sc-shard-status"

# Running from the Windows installer's build (PyInstaller) rather than from the source folder
FROZEN = bool(getattr(sys, "frozen", False))
# The tool's own folder (where status.py or SC Shard Status.exe lives)
HERE = Path(sys.executable).resolve().parent if FROZEN else Path(__file__).resolve().parent.parent


def _data_dir():
    """Where settings, the database and reports live. The source copy keeps them in its own data folder. The installed
    app keeps them in %LOCALAPPDATA%\\SC Shard Status, outside the program folder, so updating or reinstalling
    never touches them. SCSTATUS_DATA overrides both (tests, and the installer's build check)."""
    env = os.environ.get("SCSTATUS_DATA")
    if env:
        return Path(env)
    if FROZEN:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / APP_NAME
    return HERE / "data"


DATA = _data_dir()
LIBRARY = Path(__file__).resolve().parent / "library" / "issues.json"

DEFAULT_CONFIG = {
    # Folder holding Game.log (StarCitizen\LIVE). Leave blank and the tool looks for it.
    "game_dir": "",
    # Game language folder under Data\Localization (for item names)
    "language": "english",
    # Read the game's debug overlay (r_displayinfo) off the screen every this many seconds. 0 = off
    # (screenshots you take are still read).
    "overlay_every_s": 5,
    # Also read any screenshot you take in game (Print Screen) that shows the overlay
    "read_screenshots": True,
    # Which monitor the game is on (1 = main)
    "monitor": 1,
    # "What's gone wrong?" looks back this many minutes
    "lookback_minutes": 30,
    # Local dashboard (only reachable from this PC). The inventory tracker uses 8765.
    "dashboard_port": 8775,
    # Community board (both off until you switch them on in the app's Set up tab).
    # share_readings: send a 5-minute summary of your overlay readings. community_board: show other shards.
    "share_readings": False,
    "community_board": False,
    # Leave blank for the official board
    "community_url": "",
    # Which version of the first-run questions has been answered (the app asks again when new ones are added)
    "setup_version": 0,
    "open_browser": True,
    # Add r_displayinfo to the game's USER.cfg when it's missing (asks first)
    "offer_user_cfg": True,
    # Check GitHub for a newer version (once at start, then every 6 hours). Nothing installs until you click Update.
    "check_updates": True,
    # Fetch newer copies of the known-issues library from the community site (a plain download; nothing sent)
    "library_updates": False,
}


def say(msg):
    """Print a message, and keep it in data\\status.log for checking a run later."""
    line = f"[{dt.datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        DATA.mkdir(parents=True, exist_ok=True)
        log = DATA / "status.log"
        if log.exists() and log.stat().st_size > 2_000_000:
            log.replace(DATA / "status.old.log")
        with open(log, "a", encoding="utf-8") as f:
            f.write(f"{dt.datetime.now():%Y-%m-%d} {line}\n")
    except Exception:
        pass


def _is_game_dir(p):
    p = Path(p)
    return (p / "Game.log").exists() or (p / "Data.p4k").exists()


CHANNELS = ("LIVE", "PTU", "EPTU", "TECH-PREVIEW", "HOTFIX")


def find_game_dir(channel="LIVE"):
    """Look for the StarCitizen\\LIVE folder: next to this app, the usual install places on every drive, then one
    and two folders deep on each drive (custom library folders like D:\\Games\\RSI\\StarCitizen\\LIVE)."""
    cands = [HERE.parent / "StarCitizen" / channel, HERE.parent / channel, HERE.parent]
    tails = [rf"Program Files\Roberts Space Industries\StarCitizen\{channel}",
             rf"Roberts Space Industries\StarCitizen\{channel}",
             rf"Games\Roberts Space Industries\StarCitizen\{channel}",
             rf"StarCitizen\{channel}", rf"Games\StarCitizen\{channel}", rf"Games\StarCitizen\StarCitizen\{channel}"]
    roots = []
    if os.name == "nt":
        for d in string.ascii_uppercase[2:]:
            root = Path(f"{d}:\\")
            try:
                if root.exists():
                    roots.append(root)
            except OSError:
                continue
        cands += [r / t for r in roots for t in tails]
    for c in cands:
        try:
            if _is_game_dir(c):
                return c
        except OSError:
            continue
    for r in roots:
        for pattern in (f"*/StarCitizen/{channel}", f"*/*/StarCitizen/{channel}"):
            try:
                for c in r.glob(pattern):
                    if _is_game_dir(c):
                        return c
            except OSError:
                continue
    return None


def running_game_dir():
    """The folder of a running StarCitizen.exe (Windows), e.g. ...\\StarCitizen\\LIVE. None if it isn't running."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        psapi, kernel32 = ctypes.windll.psapi, ctypes.windll.kernel32
        arr = (wintypes.DWORD * 4096)()
        needed = wintypes.DWORD()
        if not psapi.EnumProcesses(ctypes.byref(arr), ctypes.sizeof(arr), ctypes.byref(needed)):
            return None
        for pid in arr[:needed.value // ctypes.sizeof(wintypes.DWORD)]:
            h = kernel32.OpenProcess(0x1000, False, pid)
            if not h:
                continue
            try:
                buf = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(1024)
                if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    exe = Path(buf.value)
                    if exe.name.lower() == "starcitizen.exe":
                        live = exe.parent.parent         # ...\\LIVE\\Bin64\\StarCitizen.exe
                        return live if _is_game_dir(live) else None
            finally:
                kernel32.CloseHandle(h)
    except Exception:
        return None
    return None


def save_setting(key, value):
    """Change one setting in data\\config.json, keeping the rest."""
    path = DATA / "config.json"
    try:
        cfg = _lenient_json(path.read_text(encoding="utf-8-sig")) if path.exists() else {}
    except Exception:
        cfg = {}
    cfg[key] = value
    path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _lenient_json(text):
    """config.json as people edit it on Windows: single backslashes in paths are taken literally."""
    def has_control(v):
        return any(isinstance(x, str) and any(ord(c) < 32 for c in x) for x in v.values())
    try:
        data = json.loads(text)
        if not has_control(data):
            return data
    except json.JSONDecodeError:
        pass
    return json.loads(re.sub(r'(?<!\\)\\(?![\\"])', r"\\\\", text))


def load_config():
    try:
        DATA.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise SystemExit(f"Can't write to {DATA} ({e}). Move the SC Shard Status folder somewhere you can write to, "
                         "such as next to your StarCitizen folder or in Documents, and run Setup.bat again.")
    cfg_path = DATA / "config.json"
    if FROZEN and not cfg_path.exists():
        # First start of the installed app: bring settings and history across from a zip copy, if there is one
        from .migrate import migrate_old_install
        migrate_old_install(DATA)
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    broken = False
    if cfg_path.exists():
        try:
            cfg.update(_lenient_json(cfg_path.read_text(encoding="utf-8-sig")))
        except Exception as e:
            broken = True
            say(f"Couldn't read {cfg_path} ({e}). Using the defaults for now; your file is left as it is. "
                "Check for a missing comma or quote.")
    if not broken:
        try:
            cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except Exception:
            pass
    if not cfg.get("game_dir") or not _is_game_dir(cfg["game_dir"]):
        if cfg.get("game_dir"):
            say(f"No Game.log in {cfg['game_dir']} (game_dir in {cfg_path}). Looking in the usual places.")
        found = find_game_dir()
        cfg["game_dir"] = str(found) if found else ""
    return cfg


def game_dir_ok(path):
    return bool(path) and _is_game_dir(path)
