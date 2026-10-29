"""Feature screenshots for the README and release page.

    python tools/showcase.py <StarCitizen LIVE folder> [--out docs/screenshots] [--keep]

Takes real logs, swaps every handle, account and entity number, session id,
address, PC name and Windows user for made-up ones, moves the times so the
newest log ends a few minutes ago, then runs the dashboard with made-up overlay
readings for a healthy, a struggling and a bad shard and screenshots each page.
Nothing from the source logs that identifies anyone ends up in the images.
"""
import argparse
import os
import random
import re
import shutil
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scstatus import config, redact  # noqa: E402

FAKE_OWN = "Demo_Pilot"
FAKE_OTHERS = ["Nova_Rook", "KestrelVane", "Ashfall_Jin", "Morrow_Teague", "Quill_Haddad", "Brisk_Okafor",
               "Tamsin_Vey", "Halcyon_Reyes", "Corvid_Lin", "Dusty_Abara", "SableMarsh", "Orrin_Pike"]
TS = re.compile(r"<(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d+)?Z>")
NUM = re.compile(r"(?<!\d)\d{6,}(?!\d)")
LOCAL = timezone(timedelta(hours=10))   # file names use local time, like the game does


def first_ts(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            m = TS.search(line)
            if m:
                return datetime.fromisoformat(m.group(1)).replace(tzinfo=timezone.utc)
    return None


def last_ts(path):
    with open(path, "rb") as f:
        f.seek(max(0, os.path.getsize(path) - 200_000))
        tail = f.read().decode("utf-8", "replace")
    ms = TS.findall(tail)
    return datetime.fromisoformat(ms[-1][0]).replace(tzinfo=timezone.utc) if ms else None


class Anon:
    """Consistent swaps: the same real value always becomes the same made-up one, so the logs still parse."""

    def __init__(self, own, others, shift, seed=7):
        self.rnd = random.Random(seed)
        self.shift = shift
        self.map = {}
        names = {}
        for h in own:
            names[h] = FAKE_OWN
            names[h.replace("_", " ")] = FAKE_OWN.replace("_", " ")
        pool = iter(FAKE_OTHERS)
        for h in others:
            if h not in names:
                names[h] = next(pool, None) or f"Pilot_{len(names):02d}"
                if "_" in h:
                    names.setdefault(h.replace("_", " "), names[h].replace("_", " "))
        self.names = names
        self.name_rx = re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(
            re.escape(n) for n in sorted(names, key=len, reverse=True)) + r")(?![A-Za-z0-9_])") if names else None

    def _swap(self, kind, real, make):
        key = (kind, real)
        if key not in self.map:
            self.map[key] = make(real)
        return self.map[key]

    def _num(self, m):
        s = m.group(0)
        return self._swap("n", s, lambda x: str(self.rnd.randint(1, 9)) +
                          "".join(str(self.rnd.randint(0, 9)) for _ in x[1:]))

    def _hex(self, m):
        s = m.group(0)
        return self._swap("h", s.lower(), lambda x: "".join(
            c if c == "-" else self.rnd.choice("0123456789abcdef") for c in x))

    def _ip(self, m):
        s = m.group(0)
        port = s.split(":")[1] if ":" in s else None
        ip = self._swap("ip", s.split(":")[0], lambda x: f"10.{self.rnd.randint(1, 250)}."
                        f"{self.rnd.randint(1, 250)}.{self.rnd.randint(1, 250)}")
        return ip + (":" + port if port else "")

    def _ts(self, m):
        t = datetime.fromisoformat(m.group(1)) + self.shift
        return "<" + t.strftime("%Y-%m-%dT%H:%M:%S") + (m.group(2) or "") + "Z>"

    def line(self, s):
        s = TS.sub(self._ts, s)
        s = redact.HOSTNAME.sub(r"\1DEMO-PC\2demo-pc", s)
        s = redact.COMPUTER.sub(r"\1\2DEMO-PC", s)
        s = redact.USERS_DIR.sub(r"\1Pilot", s)
        for rx in redact.WINUSER_FORMS:
            s = rx.sub(r"\1Pilot\2", s)
        if self.name_rx:
            s = self.name_rx.sub(lambda m: self.names[m.group(1)], s)
        for rx in redact.NAME_FORMS:           # anyone the first pass didn't list
            s = rx.sub(self._blank, s)
        s = redact.GUID.sub(self._hex, s)
        s = redact.HEX32.sub(self._hex, s)
        s = redact.IPV6.sub(lambda m: "fd00::1" if m.group(0).count(":") >= 2 else m.group(0), s)
        s = redact.IP.sub(self._ip, s)
        s = NUM.sub(self._num, s)
        return s

    def _blank(self, m):
        out = m.group(0)
        for n in m.groups():
            if n and redact._is_name(n) and n not in self.names.values() and n not in FAKE_OTHERS:
                fake = self._swap("p", n, lambda x: f"Pilot_{self.rnd.randint(100, 999)}")
                out = re.sub(r"(?<![A-Za-z0-9_])" + re.escape(n) + r"(?![A-Za-z0-9_])", fake, out)
        return out


def build_logs(src, dest, sessions=12):
    """Copy the newest logs, made anonymous and moved in time. Returns the made-up LIVE folder."""
    logs = [p for p in (src / "logbackups").glob("*.log")]
    logs = sorted(logs, key=lambda p: first_ts(p) or datetime.min.replace(tzinfo=timezone.utc))[-sessions:]
    current = src / "Game.log"
    every = logs + [current]
    end = last_ts(current)
    shift = datetime.now(timezone.utc) - timedelta(minutes=4) - end
    print(f"Reading names from {len(every)} logs...", flush=True)
    lines = []
    for p in every:
        with open(p, encoding="utf-8", errors="replace") as f:
            lines.extend(f.readlines())
    own = list(dict.fromkeys(m.group(1) for line in lines for m in re.finditer(r"\bHandle\[([^\]]+)\]", line)))
    others = [h for h in redact.find_handles(lines) if h not in own]
    anon = Anon(own, others, shift)
    del lines
    game = dest / "LIVE"
    (game / "logbackups").mkdir(parents=True)
    (game / "screenshots").mkdir()
    for p in every:
        start = first_ts(p) + shift
        out = game / "Game.log" if p == current else \
            game / "logbackups" / f"Game Build(12913470) {start.astimezone(LOCAL).strftime('%d %b %y (%H %M %S)')}.log"
        with open(p, encoding="utf-8", errors="replace") as f, open(out, "w", encoding="utf-8", newline="") as g:
            for line in f:
                g.write(anon.line(line))
        t = (last_ts(out) or start).timestamp()
        os.utime(out, (t, t))
    loc = src / "Data" / "Localization"
    if loc.exists():
        shutil.copytree(loc, game / "Data" / "Localization")
    # Last check: nothing real left
    real = own + [h for h in others if len(h) >= 4]
    left = []
    for p in game.rglob("*.log"):
        text = p.read_text(encoding="utf-8", errors="replace")
        left += [f"{p.name}: {x}" for x in redact.leaks(text, real) if x.startswith("handle")]
        for h in own:                     # parts of your own handle, any case ("draco", "AURELIUS")
            for part in re.split(r"[_\-\s]+", h):
                if len(part) >= 4 and re.search(re.escape(part), text, re.I):
                    left.append(f"{p.name}: part of your handle ({part})")
    if left:
        sys.exit("Stopped: real names left in the made-up logs:\n" + "\n".join(left[:20]))
    return game


SCENARIOS = {
    # median server fps, spread, ping, loss %, hitches, restart rises
    "healthy": dict(fps=21.2, spread=1.4, ping=28, loss=0.0, hitches=0, restart=False, client=104),
    "struggling": dict(fps=7.2, spread=2.4, ping=118, loss=0.8, hitches=3, restart=False, client=71),
    "bad": dict(fps=3.4, spread=1.6, ping=262, loss=4.0, hitches=6, restart=True, client=58),
}
LOCATIONS = ["RR_CRU_L4", "Area18", "Orison", "Lorville", "New Babbage", "Baijini Point", "Port Tressler"]


def readings(app, shard, kind, rnd, now):
    sc = SCENARIOS[kind]
    out = []
    pop = 431 if kind == "healthy" else 612
    for i in range(72):
        ts = now - (72 - i) * 50
        # Healthy for most of the hour; the trouble starts in the last 25 minutes
        bad_now = kind != "healthy" and i > 42
        base = SCENARIOS["healthy"] if not bad_now else sc
        f = max(1.0, base["fps"] + (rnd.random() - .5) * base["spread"])
        pop += rnd.choice((-2, -1, 0, 1, 2))
        out.append({"ts": ts, "ok": True, "shard_id": shard,
                    "server_name": "pub-apse2a-sc-alpha-4102-12974691-game-07",
                    "server_fps": round(f, 1), "server_fps_min": round(max(.5, f - .9), 1),
                    "server_fps_max": round(f + .6, 1), "server_ms": round(1000 / f, 1),
                    "hitches": base["hitches"] if bad_now else 0,
                    "restarts": (1 if sc["restart"] and i > 60 else 0),
                    "pop_shard": pop, "pop_srv": 34 + i // 18 + (9 if bad_now else 0),
                    "ping_ms": round(base["ping"] + rnd.random() * 9, 1), "loss_pct": base["loss"],
                    "client_fps": round(base["client"] + rnd.random() * 8, 1),
                    "vram_used_mb": 9250, "vram_total_mb": 16304,
                    "location": LOCATIONS[(i // 12) % len(LOCATIONS)]})
    return out


def past_readings(app, rnd, now):
    """A few days of readings on other shards, for the History page."""
    shards = [("pub_apse2a_43711962_020", 21.0), ("pub_apse2a_43711962_060", 16.5),
              ("pub_euw1b_43711962_100", 20.4), ("pub_apse2a_43711962_040", 21.3), ("pub_use1c_43711962_030", 11.8)]
    for d in range(1, 4):
        for h in (7, 12, 15, 19, 21, 23):
            shard, fps = shards[(d * 7 + h) % len(shards)]
            peak = 1.0 - (0.12 if h in (19, 21) else 0)
            start = now - d * 86400 - (now % 86400) + h * 3600 - 10 * 3600   # Brisbane hours
            for k in range(30):
                f = max(1, fps * peak + (rnd.random() - .5) * 2)
                app.store.add_snapshot({"ts": start + k * 60, "ok": True, "shard_id": shard,
                                        "server_fps": round(f, 1), "server_fps_min": round(f - 1, 1),
                                        "pop_shard": rnd.randint(380, 640), "pop_srv": rnd.randint(25, 48),
                                        "ping_ms": 28 if "apse2" in shard else 240, "loss_pct": 0,
                                        "hitches": 0, "restarts": 0, "client_fps": 100}, app.build)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("live")
    ap.add_argument("--out", default=str(ROOT / "docs" / "screenshots"))
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--keep", action="store_true", help="leave the dashboard running after the screenshots")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="scstatus-showcase-"))
    game = build_logs(Path(a.live), tmp)

    config.DATA = tmp / "data"
    config.DATA.mkdir()
    import scstatus.app as appmod
    import scstatus.issues as issues
    appmod.DATA = config.DATA
    issues.DATA = config.DATA
    cfg = dict(config.DEFAULT_CONFIG, game_dir=str(game), dashboard_port=a.port, open_browser=False,
               read_screenshots=False)
    app = appmod.App(cfg)
    app.start(overlay=False)

    class Reading:                       # the overlay pill shows what a player with it switched on sees
        status = "reading"
    app.watcher = Reading()
    for _ in range(600):
        if "past sessions" in (app.import_status or ""):
            break
        time.sleep(0.5)
    rnd = random.Random(4)
    now = time.time()
    past_readings(app, rnd, now)
    shard = (app.session.shard_id if app.session and app.session.shard_id else "pub_apse2a_43711962_090")

    from scstatus.dashboard import start_server
    server, url = start_server(app)
    print("Dashboard", url, flush=True)

    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch()

        def page(scheme="dark", w=1440, h=1000):
            p = b.new_page(viewport={"width": w, "height": h}, color_scheme=scheme, device_scale_factor=1)
            p.goto(url)
            p.wait_for_timeout(1500)
            return p

        def shot(p, name, full=False, h=None):
            p.wait_for_timeout(900)
            kw = {"full_page": True} if full else {}
            if h:
                kw = {"clip": {"x": 0, "y": 0, "width": p.viewport_size["width"], "height": h}}
            p.screenshot(path=str(out / f"{name}.png"), **kw)
            print("  saved", name, flush=True)

        def scenario(kind):
            with app.lock:
                app.snaps.clear()
            for s in readings(app, shard, kind, random.Random(kind), time.time()):
                app.on_reading(s)

        for i, kind in enumerate(("healthy", "struggling", "bad")):
            scenario(kind)
            p = page()
            shot(p, f"{i + 1}-now-{kind}", full=True)
            p.close()

        # What's gone wrong, while the bad readings are still in
        p = page()
        p.click('[data-tab="check"]')
        p.wait_for_timeout(500)
        p.select_option("#mins", "240")
        p.click("#runCheck")
        p.wait_for_function("() => !document.getElementById('runCheck').disabled", timeout=180_000)
        p.wait_for_timeout(1500)
        shot(p, "4-whats-gone-wrong", full=True)
        # The Issue Council draft for the top finding
        p.click('[data-report="0"]')
        p.wait_for_timeout(2000)
        shot(p, "5-issue-council-draft")
        p.close()

        scenario("healthy")
        for n, tab in (("6-history", "history"), ("7-my-pc", "pc"), ("8-known-issues", "issues"),
                       ("9-set-up", "setup"), ("10-about", "about")):
            p = page()
            p.click(f'[data-tab="{tab}"]')
            p.wait_for_timeout(1500)
            shot(p, n, full=tab not in ("issues", "setup"), h=1400 if tab in ("issues", "setup") else None)
            p.close()
        p = page("light")
        shot(p, "11-now-light-theme", full=True)
        p.close()
        p = page(w=390, h=844)
        shot(p, "12-phone-width", h=844)
        p.close()
        b.close()
    print("Done:", out)
    if a.keep:
        while True:
            time.sleep(1)
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
