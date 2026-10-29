"""First start of the installed app: find a zip copy of SC Shard Status (from before there was an installer) and bring
its settings, history and reports across, so nobody starts from scratch.

The zip copy keeps everything in its own data folder (data\\config.json, data\\status.db, data\\reports). Its
shortcuts point at launchers\\status.bat inside it, which is the quickest way to find it; failing that, the usual
places people unzip things are searched a few folders deep."""

import json
import os
import re
import shutil
import string
from pathlib import Path

from .config import _lenient_json, say

SKIP = {"windows", "program files", "program files (x86)", "programdata", "$recycle.bin", "system volume information",
        "appdata", "recovery", "perflogs", "msocache", "intel", "amd", "nvidia"}
NAME_RX = re.compile(r"shard.?status", re.I)
LNK_RX = re.compile(r"([A-Za-z]:\\[^\x00<>\"|?*\r\n]{1,240}?)\\launchers\\[\w\- ]+\.bat", re.I)


def is_zip_copy(p):
    p = Path(p)
    return (p / "status.py").is_file() and (p / "scstatus").is_dir() and (p / "data" / "config.json").is_file()


def from_shortcuts(home=None):
    """Folders the old copy's shortcuts point at (Setup.bat made them on the desktop and in the Start menu)."""
    home = Path(home or os.environ.get("USERPROFILE") or Path.home())
    appdata = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
    places = [home / "Desktop", home / "OneDrive" / "Desktop",
              appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "SC Shard Status"]
    found = []
    for d in places:
        try:
            lnks = [x for x in d.iterdir() if x.suffix.lower() == ".lnk" and NAME_RX.search(x.name)]
        except OSError:
            continue
        for lnk in lnks:
            try:
                raw = lnk.read_bytes()
            except OSError:
                continue
            # A .lnk holds the target path both as plain text and as UTF-16
            for text in (raw.decode("latin-1"), raw.decode("utf-16-le", "ignore"), raw[1:].decode("utf-16-le", "ignore")):
                for m in LNK_RX.finditer(text):
                    p = Path(m.group(1))
                    if p not in found and is_zip_copy(p):
                        found.append(p)
    return found


def _walk(root, depth, out):
    try:
        with os.scandir(root) as it:
            for e in it:
                if not e.is_dir(follow_symlinks=False) or e.name.lower() in SKIP or e.name.startswith("."):
                    continue
                if NAME_RX.search(e.name) and is_zip_copy(e.path):
                    out.append(Path(e.path))
                elif depth > 1:
                    _walk(e.path, depth - 1, out)
    except OSError:
        pass


def by_search(home=None, drives=True):
    """The zip copy anywhere people usually unzip things: Downloads, Desktop, Documents, OneDrive, the home folder,
    and a few folders deep on each drive (C:\\Games\\StarCitizen\\SC-Shard-Status and the like)."""
    home = Path(home or os.environ.get("USERPROFILE") or Path.home())
    out = []
    for d, depth in ((home / "Downloads", 3), (home / "Desktop", 3), (home / "Documents", 3),
                     (home / "OneDrive", 3), (home, 1)):
        _walk(d, depth, out)
    if drives and os.name == "nt":
        for letter in string.ascii_uppercase[2:]:
            root = f"{letter}:\\"
            if os.path.exists(root):
                _walk(root, 3, out)
    seen, uniq = set(), []
    for p in out:
        k = str(p).lower()
        if k not in seen:
            seen.add(k)
            uniq.append(p)
    return uniq


def _last_used(p):
    t = 0
    for f in ("data/status.db", "data/config.json", "data/status.log"):
        try:
            t = max(t, (p / f).stat().st_mtime)
        except OSError:
            pass
    return t


def find_old_install(home=None, drives=True):
    cands = from_shortcuts(home) or by_search(home, drives)
    return max(cands, key=_last_used) if cands else None


def migrate_old_install(data, home=None, drives=True):
    """Copy the zip copy's data folder into the installed app's data folder. Returns the old folder, or None."""
    try:
        old = find_old_install(home, drives)
    except Exception as e:                      # never stop the app starting over this
        say(f"Couldn't look for an older copy of SC Shard Status ({e}).")
        return None
    if not old:
        return None
    src = old / "data"
    data = Path(data)
    try:
        data.mkdir(parents=True, exist_ok=True)
        for name in ("status.db", "status.db-wal", "status.db-shm", "issues.json"):
            if (src / name).is_file():
                shutil.copy2(src / name, data / name)
        if (src / "reports").is_dir() and not (data / "reports").exists():
            shutil.copytree(src / "reports", data / "reports")
        cfg = _lenient_json((src / "config.json").read_text(encoding="utf-8-sig"))
    except Exception as e:
        say(f"Found your older copy in {old} but couldn't bring its settings across ({e}). Starting fresh.")
        return None
    cfg["migrated_from"] = str(old)
    cfg["migrated_notice"] = True
    (data / "config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    say(f"Brought your settings and history across from {old}. That folder isn't used any more; delete it when "
        "you're ready.")
    return old
