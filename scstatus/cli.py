"""Command line: live mode (with the dashboard) and a quick check of any log."""

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

from .config import APP_NAME, VERSION, load_config, say

HELP = """
Examples:
  SC Shard Status shortcut                live mode while you play (opens the dashboard)
  status.py --no-overlay                  live mode without reading the screen
  status.py --check                       what's gone wrong in the last 30 minutes, printed here
  status.py --check --file "logbackups\\Game Build(...).log" --minutes 0     a whole old log
"""


def main(argv=None):
    ap = argparse.ArgumentParser(prog="status.py", description=f"{APP_NAME} {VERSION}", epilog=HELP,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--no-overlay", action="store_true", help="don't read the game's overlay off the screen")
    ap.add_argument("--no-browser", action="store_true", help="don't open the dashboard in the browser")
    ap.add_argument("--check", action="store_true", help="print what's gone wrong and exit")
    ap.add_argument("--file", help="log file for --check (default: the current Game.log)")
    ap.add_argument("--minutes", type=int, help="how far back --check looks (0 = the whole log)")
    args = ap.parse_args(argv)
    cfg = load_config()
    if not cfg.get("game_dir"):
        say("Couldn't find the StarCitizen\\LIVE folder. Put its path in data\\config.json (game_dir).")
    if args.check:
        return check(cfg, args.file, args.minutes)
    return live(cfg, overlay=not args.no_overlay, browser=cfg.get("open_browser", True) and not args.no_browser)


def check(cfg, file=None, minutes=None):
    from .diagnose import diagnose
    from .issues import Library
    from .logparse import parse_file
    from .names import Names
    game = Path(cfg.get("game_dir") or ".")
    path = Path(file) if file else game / "Game.log"
    if not path.is_absolute() and not path.exists():
        path = game / path
    if not path.exists():
        sys.exit(f"No log at {path}")
    s = parse_file(path)
    if minutes is None:
        minutes = cfg.get("lookback_minutes", 30)
    now = (s.end or time.time()) + 1
    look = minutes if minutes else max(1, int(((s.end or now) - (s.start or now)) / 60) + 2)
    res = diagnose(path, Library(), Names(game, cfg.get("language", "english")), lookback_min=look, now=now,
                   session=s, backups_dir=None if file else game / "logbackups")
    print(f"\n{path.name}: {res['lines_checked']} lines checked, {res['noise_lines']} harmless.\n")
    print(res["headline"] + "\n")
    for f in res["findings"]:
        when = dt.datetime.fromtimestamp(f["first_ts"]).strftime("%d %b %H:%M") if f.get("first_ts") else ""
        print(f"[{f['severity'].upper()}] {f['title']}  ({f['count']}x, from {when})")
        print("    " + f["explain"])
        for x in f["fixes"]:
            print("    - " + x)
        print()
    if res["unknown"]:
        print(f"{len(res['unknown'])} kinds of unrecognised error (may be harmless):")
        for u in res["unknown"][:10]:
            print(f"    {u['count']:>4}x  {u['fields']['sig'][:110]}")
    return 0


def live(cfg, overlay=True, browser=True):
    import webbrowser
    from .app import App
    from .dashboard import already_running, start_server
    url = already_running(int(cfg.get("dashboard_port", 8775)))
    if url:
        say(f"SC Shard Status is already running. Opening its dashboard: {url}")
        webbrowser.open(url)
        return 0
    from . import score
    say(f"{APP_NAME} {VERSION}. Game folder: {cfg.get('game_dir') or 'not found'}")
    app = App(cfg)
    app.start(overlay=overlay)
    server, url = start_server(app, open_browser=browser)
    say(f"Dashboard: {url}  (only this PC can open it)")
    if overlay:
        st = app.user_cfg_state()
        if not st.get("has_displayinfo"):
            say("Tip: in game, open the console (~) and type r_displayinfo 3, or use the button on the dashboard "
                "to add it to USER.cfg so it's always on.")
    say("Close this window (or press Ctrl+C) to stop.")
    last = 0
    try:
        while True:
            time.sleep(5)
            if time.time() - last >= 60:
                last = time.time()
                a = score.assess(list(app.snaps))
                if a["score"] is not None:
                    say(f"{a['score']}/100 {a['label']}. {a['summary']}")
                elif app.watcher:
                    say(f"Overlay: {app.watcher.status}")
    except KeyboardInterrupt:
        pass
    app.stop.set()
    server.shutdown()
    say("Stopped.")
    return 0
