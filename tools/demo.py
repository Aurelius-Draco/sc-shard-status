"""Run the dashboard against a copy of real logs and made-up overlay readings (for development and screenshots).

    python tools/demo.py <StarCitizen LIVE folder> [--port 8790]
"""
import argparse
import random
import shutil
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scstatus import config  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("live")
    ap.add_argument("--log", help="log to use as Game.log (default: the newest in logbackups)")
    ap.add_argument("--port", type=int, default=8790)
    ap.add_argument("--slow", action="store_true", help="make the server struggle")
    a = ap.parse_args()
    src = Path(a.live)
    tmp = Path(tempfile.mkdtemp(prefix="scstatus-demo-"))
    game = tmp / "LIVE"
    (game / "logbackups").mkdir(parents=True)
    backups = sorted((src / "logbackups").glob("*.log"), key=lambda p: p.stat().st_mtime)
    log = Path(a.log) if a.log else backups[-1]
    shutil.copy2(log, game / "Game.log")
    for p in backups[-12:]:
        if p != log:
            shutil.copy2(p, game / "logbackups" / p.name)
    loc = src / "Data" / "Localization"
    if loc.exists():
        (game / "Data").mkdir()
        shutil.copytree(loc, game / "Data" / "Localization")
    config.DATA = tmp / "data"
    import scstatus.app as appmod
    import scstatus.store  # noqa: F401
    appmod.DATA = config.DATA
    import scstatus.issues as issues
    issues.DATA = config.DATA
    config.DATA.mkdir(exist_ok=True)
    if not config.LIBRARY.exists():
        shutil.copy2(Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "mini_issues.json",
                     config.DATA / "issues.json")
    cfg = dict(config.DEFAULT_CONFIG, game_dir=str(game), dashboard_port=a.port, open_browser=False,
               # Never talk to the real community site from a demo (made-up readings would land on the live board)
               community_url="http://127.0.0.1:9", share_readings=False, community_board=False)
    app = appmod.App(cfg)
    app.start(overlay=False)
    now = time.time()
    rnd = random.Random(4)
    pop = 431
    for i in range(70):
        ts = now - (70 - i) * 50
        f = (6 + rnd.random() * 3) if a.slow and i > 40 else 20.5 + rnd.random() * 1.6
        pop += rnd.choice((-2, -1, 0, 1, 2))
        app.on_reading({"ts": ts, "ok": True, "shard_id": "pub_apse2a_12881860_090",
                        "server_name": "pub-apse2a-sc-alpha-4102-12974691-game-07",
                        "server_fps": round(f, 1), "server_fps_min": round(f - .8, 1), "server_fps_max": round(f + .6, 1),
                        "server_ms": round(1000 / f, 1), "hitches": 0, "restarts": 0, "pop_shard": pop,
                        "pop_srv": 34 + i // 18, "ping_ms": round(24 + rnd.random() * 7, 1), "loss_pct": 0.0,
                        "client_fps": round(100 + rnd.random() * 10, 1), "vram_used_mb": 9250, "vram_total_mb": 15423,
                        "location": "RR_CRU_L4"})
    from scstatus.dashboard import start_server
    server, url = start_server(app)
    print("DEMO", url, flush=True)
    while True:
        time.sleep(1)


if __name__ == "__main__":
    main()
