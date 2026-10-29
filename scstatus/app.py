"""Everything the app's parts share: settings, database, the live log, overlay readings."""

import collections
import os
import re
import threading
import time
from pathlib import Path

from . import community, report, score
from .config import DATA, say
from .diagnose import diagnose
from .issues import Library
from .logparse import LogTail, parse_file, region_name
from .names import Names
from .store import Store


class App:
    def __init__(self, cfg):
        self.cfg = cfg
        DATA.mkdir(exist_ok=True)
        self.store = Store(DATA / "status.db")
        self.library = Library()
        self.game_dir = Path(cfg.get("game_dir") or ".")
        self._names = None
        self.snaps = collections.deque(maxlen=2000)
        for s in self.store.snapshots(since=time.time() - 3 * 3600):
            self.snaps.append(s)
        self.tail = LogTail(self.game_dir / "Game.log")
        self.watcher = None
        self.stop = threading.Event()
        self.lock = threading.RLock()
        self.last_result = None
        self.import_status = "not started"

    # -- parts that load slowly
    @property
    def names(self):
        if self._names is None:
            self._names = Names(self.game_dir, self.cfg.get("language", "english"))
        return self._names

    @property
    def session(self):
        return self.tail.session

    @property
    def build(self):
        return self.session.build if self.session else None

    # -- running
    def start(self, overlay=True):
        self.tail.poll()
        threading.Thread(target=self.tail.run, args=(self.stop,), daemon=True).start()
        if overlay and float(self.cfg.get("overlay_every_s") or 0) > 0:
            from .capture import OverlayWatcher
            self.watcher = OverlayWatcher(self.cfg["overlay_every_s"], self.cfg.get("monitor", 1), self.on_reading)
            threading.Thread(target=self.watcher.run, args=(self.stop,), daemon=True).start()
        threading.Thread(target=self.import_backups, daemon=True).start()

    def on_reading(self, snap):
        with self.lock:
            self.snaps.append(snap)
        try:
            self.store.add_snapshot(snap, self.build)
        except Exception as e:
            say(f"Couldn't save a reading ({e}).")

    def import_backups(self):
        """Read past sessions from logbackups once (skips files already read)."""
        folder = self.game_dir / "logbackups"
        if not folder.exists():
            self.import_status = "no logbackups folder"
            return
        files = sorted(folder.glob("*.log"), key=lambda p: p.stat().st_mtime)
        new = 0
        for i, p in enumerate(files):
            self.import_status = f"reading past sessions ({i + 1}/{len(files)})"
            size = p.stat().st_size
            if self.store.session_known(p.name, size):
                continue
            try:
                self.store.save_session(parse_file(p).summary(), size)
                new += 1
            except Exception as e:
                say(f"Couldn't read {p.name} ({e}).")
        self.import_status = f"{len(files)} past sessions" + (f" ({new} new)" if new else "")

    # -- what the dashboard shows
    def now(self):
        with self.lock:
            snaps = list(self.snaps)
        a = score.assess(snaps)
        s = self.session
        sess = s.summary() if s else {}
        hour_ago = time.time() - 3600
        spark = [{"ts": x["ts"], "server_fps": x.get("server_fps"), "pop_srv": x.get("pop_srv"),
                  "pop_shard": x.get("pop_shard"), "ping_ms": x.get("ping_ms"), "client_fps": x.get("client_fps")}
                 for x in snaps if x["ts"] >= hour_ago and x.get("ok")]
        cmp = None
        if a.get("server_fps") is not None and self.build:
            cmp = score.compare(a["server_fps"], self.store.build_fps(self.build))
        shard = a.get("shard_id") or sess.get("shard_id")
        return {
            "health": a, "compare": cmp, "spark": spark,
            "overlay_status": self.watcher.status if self.watcher else "off",
            "session": {k: sess.get(k) for k in ("build", "version", "shard_id", "start", "load_s", "minutes",
                                                  "joins", "bad_disconnects", "errors", "clean_exit")},
            "shard": {"id": shard, "region": region_name(_region(shard)), "region_code": _region(shard)},
            "contracts": _active_contracts(sess.get("contracts", [])),
            "game_dir": str(self.game_dir), "game_found": (self.game_dir / "Game.log").exists(),
            "user_cfg": self.user_cfg_state(), "import_status": self.import_status,
            "library": {"version": self.library.version, **self.library.counts()},
        }

    def run_diagnosis(self, minutes=None):
        minutes = int(minutes or self.cfg.get("lookback_minutes", 30))
        with self.lock:
            snaps = list(self.snaps)
        res = diagnose(self.game_dir / "Game.log", self.library, self.names, snaps, lookback_min=minutes,
                       backups_dir=self.game_dir / "logbackups")
        self.last_result = res
        return res

    def history(self):
        return {"sessions": self.store.sessions(), "shards": self.store.shard_history(),
                "hourly": self.store.hourly(), "import_status": self.import_status}

    def pc(self):
        hw = dict(self.session.hardware) if self.session else {}
        if not hw:
            for s in self.store.sessions(limit=5):
                if s.get("hardware"):
                    hw = s["hardware"]
                    break
        with self.lock:
            snaps = [x for x in self.snaps if x.get("client_fps") is not None]
        by_loc = {}
        for x in snaps:
            by_loc.setdefault(x.get("location") or "unknown", []).append(x["client_fps"])
        import statistics as st
        locs = sorted(({"location": k, "client_fps": round(st.median(v)), "readings": len(v)}
                       for k, v in by_loc.items()), key=lambda r: -r["readings"])[:15]
        last = snaps[-1] if snaps else {}
        return {"hardware": hw, "by_location": locs, "vram_used_mb": last.get("vram_used_mb"),
                "vram_total_mb": last.get("vram_total_mb"), "client_fps": last.get("client_fps")}

    # -- reports
    def _finding(self, group, i):
        if not self.last_result:
            raise ValueError("Run \"What's gone wrong?\" first.")
        items = self.last_result["unknown"] if group == "unknown" else self.last_result["findings"]
        try:
            return items[int(i)]
        except (IndexError, ValueError, TypeError):
            raise ValueError("That finding is no longer in the list. Run the check again.")

    def latest_snap(self):
        with self.lock:
            return self.snaps[-1] if self.snaps and time.time() - self.snaps[-1]["ts"] < 900 else None

    def report_draft(self, group, i):
        f = self._finding(group, i)
        d = report.draft(f, self.last_result, self.latest_snap())
        d["url"] = report.ISSUE_COUNCIL
        return d

    def report_bundle(self, group, i):
        f = self._finding(group, i)
        d = report.draft(f, self.last_result, self.latest_snap())
        folder, n = report.bundle(f, self.last_result, d, self.game_dir)
        return {"folder": str(folder), "screenshots": n}

    def review(self, i, save=False):
        f = self._finding("unknown", i)
        red = community.make_redactor(self.game_dir / "Game.log")
        sess = dict(self.last_result["session"])
        sess["region"] = _region(sess.get("shard_id"))
        contracts = [c["name"] for c in (self.session.contracts.values() if self.session else [])]
        rid, payload = community.review_request(f, sess, red, self.store.install_id(), contracts)
        if save:
            self.store.add_review(rid, payload["sig"], payload)
        return {"ticket": rid, "payload": payload, "saved": save}

    # -- the game's USER.cfg
    def user_cfg_state(self):
        p = self.game_dir / "USER.cfg"
        try:
            txt = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
        except OSError:
            return {"exists": p.exists(), "has_displayinfo": None}
        m = re.search(r"^\s*r_displayinfo\s*=\s*(\d)", txt, re.I | re.M)
        return {"exists": p.exists(), "has_displayinfo": bool(m and m.group(1) != "0"),
                "value": int(m.group(1)) if m else None}

    def add_displayinfo(self):
        p = self.game_dir / "USER.cfg"
        if not self.game_dir.exists():
            raise ValueError("Game folder not found. Set game_dir in data\\config.json.")
        txt = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
        if re.search(r"^\s*r_displayinfo\s*=", txt, re.I | re.M):
            txt = re.sub(r"^(\s*r_displayinfo\s*=\s*)\d", r"\g<1>3", txt, flags=re.I | re.M)
        else:
            txt = txt.rstrip("\n") + ("\n" if txt.strip() else "") + "r_displayinfo = 3\n"
        if p.exists():
            bak = p.with_suffix(".cfg.bak")
            if not bak.exists():
                bak.write_bytes(p.read_bytes())
        p.write_text(txt, encoding="utf-8")
        return "Added r_displayinfo = 3 to USER.cfg. It takes effect the next time the game starts."


def _active_contracts(contracts):
    """Active contracts, one row per name (the same contract taken again shows as a count)."""
    by = {}
    for c in contracts:
        if c["result"] != "active":
            continue
        row = by.setdefault(c["name"], dict(c, times=0))
        row["times"] += 1
        row["objectives"] = c["objectives"]
    return list(by.values())


def _region(shard_id):
    from .logparse import region_of
    return region_of(shard_id)


def open_folder(path):
    if os.name == "nt":
        os.startfile(str(path))     # noqa: S606 (local folder the app made)
