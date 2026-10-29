"""Settings, folders and small helpers shared by every part of SC Shard Status."""

import datetime as dt
import json
import os
import re
import string
from pathlib import Path

VERSION = "1.0"
APP_NAME = "SC Shard Status"
AUTHOR = "Aurelius_Draco"
REPO = "https://github.com/Aurelius-Draco/sc-shard-status"

# The tool's own folder (where status.py lives) and its data folder
HERE = Path(__file__).resolve().parent.parent
DATA = HERE / "data"
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
    "open_browser": True,
    # Add r_displayinfo to the game's USER.cfg when it's missing (asks first)
    "offer_user_cfg": True,
}


def say(msg):
    """Print a message, and keep it in data\\status.log for checking a run later."""
    line = f"[{dt.datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    try:
        DATA.mkdir(exist_ok=True)
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


def find_game_dir():
    """Look for the StarCitizen\\LIVE folder in the usual places."""
    cands = [HERE.parent / "StarCitizen" / "LIVE", HERE.parent / "LIVE", HERE.parent]
    tails = [r"Program Files\Roberts Space Industries\StarCitizen\LIVE",
             r"Roberts Space Industries\StarCitizen\LIVE",
             r"Games\Roberts Space Industries\StarCitizen\LIVE",
             r"StarCitizen\LIVE", r"Games\StarCitizen\LIVE", r"Games\StarCitizen\StarCitizen\LIVE"]
    if os.name == "nt":
        for d in string.ascii_uppercase[2:]:
            root = Path(f"{d}:\\")
            if root.exists():
                cands += [root / t for t in tails]
    for c in cands:
        if _is_game_dir(c):
            return c
    return None


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
        DATA.mkdir(exist_ok=True)
    except OSError as e:
        raise SystemExit(f"Can't write to {DATA} ({e}). Move the SC Shard Status folder somewhere you can write to, "
                         "such as next to your StarCitizen folder or in Documents, and run Setup.bat again.")
    cfg_path = DATA / "config.json"
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    broken = False
    if cfg_path.exists():
        try:
            cfg.update(_lenient_json(cfg_path.read_text(encoding="utf-8-sig")))
        except Exception as e:
            broken = True
            say(f"Couldn't read data\\config.json ({e}). Using the defaults for now; your file is left as it is. "
                "Check for a missing comma or quote.")
    if not broken:
        try:
            cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
        except Exception:
            pass
    if not cfg.get("game_dir") or not _is_game_dir(cfg["game_dir"]):
        if cfg.get("game_dir"):
            say(f"No Game.log in {cfg['game_dir']} (game_dir in data\\config.json). Looking in the usual places.")
        found = find_game_dir()
        cfg["game_dir"] = str(found) if found else ""
    return cfg


def game_dir_ok(path):
    return bool(path) and _is_game_dir(path)
