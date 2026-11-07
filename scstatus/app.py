"""Everything the app's parts share: settings, database, the live log, overlay readings."""

import collections
import os
import re
import threading
import time
from pathlib import Path

from .overlay import node_of
from . import community, report, score
from .config import DATA, say
from .diagnose import diagnose
from .issues import Library
from .logparse import LogTail, parse_file, region_name
from .names import Names
from .store import Store


def settled_changes(rows):
    """When the game server really changed, from readings in time order: a new server counts once it's read twice in
    a row on the same shard (or it's the newest reading), so one misread name (A, B, A) is no change at all. Returns the time of each change
    (the first reading on the new server)."""
    out, cur, cand = [], None, None
    for r in rows:
        name, shard = r.get("server_name"), r.get("shard_id")
        if not name:
            continue
        if cur is None:
            cur = (shard, name)
        elif (shard, name) == cur:
            cand = None
        elif cand and cand[0] == (shard, name):
            if shard == cur[0]:
                out.append(cand[1])
            cur, cand = (shard, name), None
        else:
            cand = ((shard, name), r["ts"])
    # The newest reading on a new server counts too: nothing after it says it was a misread (a change just before a mark)
    if cand and cur and cand[0][0] == cur[0]:
        out.append(cand[1])
    return out


def moment_findings(found, t, earlier_s=1800):
    """Split diagnosis findings for a marked moment: problems within 10 minutes of it (near_mark), and known problems
    from further back in the half hour before. Some problems are only noticed late: items that failed to move are
    often spotted 20 or 30 minutes after the failure, by which time the failure is outside the 10 minutes."""
    near, earlier = [], []
    for i, f in enumerate(found):
        if f.get("kind", "problem") != "problem":
            continue
        row = {"i": i, "title": f["title"], "severity": f.get("severity"), "rule_id": f.get("rule_id"),
               "first_ts": f.get("first_ts"), "last_ts": f.get("last_ts")}
        last = f.get("last_ts") or f.get("first_ts")
        if f.get("near_mark"):
            near.append(row)
        elif f.get("rule_id") and last and t - earlier_s <= last < t:
            earlier.append(dict(row, min_before=int((t - last) // 60)))
    earlier.sort(key=lambda r: r["min_before"])
    return near, earlier


class App:
    def __init__(self, cfg):
        self.cfg = cfg
        DATA.mkdir(parents=True, exist_ok=True)
        self.store = Store(DATA / "status.db")
        self.library = Library()
        self.game_dir = Path(cfg.get("game_dir") or ".")
        self._names = None
        self._places = None
        self.snaps = collections.deque(maxlen=2000)
        for s in self.store.snapshots(since=time.time() - 3 * 3600):
            self.snaps.append(s)
        self.tail = LogTail(self.game_dir / "Game.log")
        self.watcher = None
        self.shots = None
        self.stop = threading.Event()
        self.lock = threading.RLock()
        self.last_result = None
        self.import_status = "not started"
        from .config import COMMUNITY_URL, VERSION
        self.community = community.Community(self, cfg.get("community_url") or COMMUNITY_URL, VERSION)
        from .updater import Updater
        self.updater = Updater(self)
        from .alerts import Alerts
        self.alerts = Alerts(self)
        from .libsync import LibrarySync
        self.libsync = LibrarySync(self, cfg.get("community_url") or COMMUNITY_URL, VERSION)
        from .groups import Groups
        self.groups = Groups(self, self.community)
        from .profile import Profiles
        self.profiles = Profiles()
        from . import errors
        errors.install()
        self.errors = errors.ErrorReports(self, self.community)
        from .hotkey import Hotkey
        self.hotkey = Hotkey(lambda: self.mark("hotkey"))
        self.quitting = False

    # -- parts that load slowly
    @property
    def names(self):
        if self._names is None:
            self._names = Names(self.game_dir, self.cfg.get("language", "english"))
        return self._names

    @property
    def places(self):
        """Place names from the game's own text file (global.ini), loaded once."""
        if self._places is None:
            from .locations import Places
            self._places = Places(self.game_dir if self.game_found else None, self.cfg.get("language", "english"))
        return self._places

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
        self._overlay_allowed = overlay
        if float(self.cfg.get("overlay_every_s") or 0) > 0:
            self._start_live()
        if self.cfg.get("read_screenshots", True):
            self._start_shots()
        threading.Thread(target=self.import_backups, daemon=True).start()
        threading.Thread(target=self.community.run, args=(self.stop,), daemon=True).start()
        threading.Thread(target=self.updater.run, args=(self.stop,), daemon=True).start()
        threading.Thread(target=self.libsync.run, args=(self.stop,), daemon=True).start()
        threading.Thread(target=self.alerts.run, args=(self.stop,), daemon=True).start()
        threading.Thread(target=self._extras, args=(self.stop,), daemon=True).start()
        if self.cfg.get("mark_hotkey"):
            self.hotkey.set(self.cfg["mark_hotkey"])
        if not self.game_found:
            threading.Thread(target=self._watch_for_game, daemon=True).start()

    def _extras(self, stop):
        """Replies to your group posts, and opt-in error reports. Network only when you've turned something on."""
        from . import errors
        while not stop.wait(15):
            try:
                if self.cfg.get("community_board") or self.cfg.get("share_readings") or self.groups.mine():
                    self.groups.tick()
                self.errors.tick()
            except Exception as e:
                errors.capture("extras", e)

    # -- Mark this moment: a timestamp (and where you were) for "What's gone wrong?" to look at later
    def mark(self, source="button"):
        import json as _json
        snap = self.latest_snap() or {}
        s = self.session
        m = {"ts": time.time(), "source": source, "shard_id": snap.get("shard_id") or (s.shard_id if s else None),
             "server": snap.get("server_name"), "location": snap.get("location") or _last_loc(s)}
        rows = [x for x in self.marks(24 * 3600)] + [m]
        self.store.set_meta("marks", _json.dumps(rows[-30:]))
        if source == "hotkey":
            a = self.alerts
            a.recent.appendleft({"ts": m["ts"], "key": "mark", "title": "Moment marked", "body": "Look at it later with What's gone wrong?"})
            if a.mode:
                try:
                    a.notify("Moment marked", "Keep playing. \"What's gone wrong?\" will look at this moment.", tag="mark", sound=a.mode == "sound")
                except Exception:
                    pass
        say(f"Moment marked ({source}).")
        return m

    def marks(self, within_s=4 * 3600):
        import json as _json
        try:
            rows = _json.loads(self.store.meta("marks", "[]") or "[]")
        except ValueError:
            rows = []
        return [x for x in rows if time.time() - x.get("ts", 0) <= within_s]

    # Live reading and screenshot reading can be switched on and off while the app runs
    def _start_live(self):
        if self.watcher or not getattr(self, "_overlay_allowed", True):
            return
        from .capture import OverlayWatcher
        every = float(self.cfg.get("overlay_every_s") or 5) or 5
        self.watcher = OverlayWatcher(every, self.cfg.get("monitor", 1), self.on_reading)
        self._live_stop = threading.Event()
        threading.Thread(target=self.watcher.run, args=(self._live_stop,), daemon=True).start()

    def _stop_live(self):
        if self.watcher:
            self._live_stop.set()
            self.watcher = None

    def _start_shots(self):
        if self.shots:
            return
        from .screenshots import ScreenshotWatcher

        def reader():
            from .overlay import OverlayReader
            return OverlayReader(threads=2)
        self.shots = ScreenshotWatcher(self.game_dir / "screenshots", reader, self.on_reading)
        self.shots.poll()           # note what's already there; only new screenshots are read
        self._shots_stop = threading.Event()
        threading.Thread(target=self.shots.run, args=(self._shots_stop,), daemon=True).start()

    def _stop_shots(self):
        if self.shots:
            self._shots_stop.set()
            self.shots = None

    def _watch_for_game(self):
        """No game folder yet: when Star Citizen starts, take its folder from the running game."""
        from .config import running_game_dir
        while not self.stop.is_set() and not self.game_found:
            found = running_game_dir()
            if found:
                self.set_game_dir(str(found), source="the running game")
                return
            self.stop.wait(10)

    def set_game_dir(self, path, source="you"):
        """Point the app at a StarCitizen\\LIVE folder (saved to data\\config.json)."""
        from .config import game_dir_ok, save_setting
        path = (path or "").strip().strip('"')
        p = Path(path)
        if p.name.lower() == "game.log":
            p = p.parent
        if p.name.lower() == "bin64":
            p = p.parent
        if not game_dir_ok(p) and game_dir_ok(p / "LIVE"):
            p = p / "LIVE"
        if not game_dir_ok(p) and game_dir_ok(p / "StarCitizen" / "LIVE"):
            p = p / "StarCitizen" / "LIVE"
        if not game_dir_ok(p):
            raise ValueError(f"No Game.log or Data.p4k in {p}. Pick the StarCitizen\\LIVE folder (the one with "
                             "Bin64 and Game.log in it).")
        self.cfg["game_dir"] = str(p)
        save_setting("game_dir", str(p))
        self.game_dir = p
        self.tail.path = p / "Game.log"
        self.tail.ident = None          # read it fresh
        if self.shots:
            self.shots.folder = p / "screenshots"
        self._names = None
        self._places = None
        pending = self.cfg.pop("pending_user_cfg", None)
        if pending:
            for name, on in pending.items():
                try:
                    self.set_user_cfg(name, on)
                except Exception as e:
                    say(f"Couldn't update USER.cfg ({e}).")
            save_setting("pending_user_cfg", None)
        threading.Thread(target=self.import_backups, daemon=True).start()
        say(f"Game folder set to {p} (from {source}).")
        return f"Game folder set to {p}."

    @property
    def channel(self):
        """LIVE, or the test channel (PTU, EPTU, TECH-PREVIEW, HOTFIX) this copy is reading, from the game folder."""
        from .config import channel_of
        return channel_of(self.game_dir)

    def on_reading(self, snap):
        # Game.log is the authority on which shard you're on; small text at 1080p can misread a digit
        s = self.session
        if s and s.joins and (not snap.get("shard_id") or snap["shard_id"] != s.shard_id):
            if not snap.get("shard_id") or _close(snap["shard_id"], s.shard_id):
                snap["shard_id"] = s.shard_id
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
        # 1.4 adds ships retrieved to each session's summary, so read every file once more
        again = self.store.meta("summary_v") != "2"
        for i, p in enumerate(files):
            self.import_status = f"reading past sessions ({i + 1}/{len(files)})"
            size = p.stat().st_size
            if self.store.session_known(p.name, size) and not again:
                continue
            try:
                self.store.save_session(parse_file(p).summary(), size)
                new += 1
            except Exception as e:
                say(f"Couldn't read {p.name} ({e}).")
        self.import_status = f"{len(files)} past sessions" + (f" ({new} new)" if new and not again else "")
        if again:
            self.store.set_meta("summary_v", "2")

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
        out = {
            "health": a, "compare": cmp, "spark": spark,
            "overlay_status": self.watcher.status if self.watcher else "off",
            "screenshot_readings": self.shots.count if self.shots else None,
            "session": {k: sess.get(k) for k in ("build", "version", "shard_id", "start", "end", "load_s", "minutes",
                                                  "joins", "bad_disconnects", "errors", "clean_exit")},
            "shard": {"id": shard, "name": community.shard_name(shard), "region": region_name(_region(shard)),
                      "region_code": _region(shard)},
            "where": self._where(a), "rsi": (self.community.rsi if (self.community.rsi or {}).get("problem") else None),
            "contracts": _active_contracts(sess.get("contracts", [])),
            "game_dir": str(self.game_dir), "game_found": (self.game_dir / "Game.log").exists(),
            "user_cfg": self.user_cfg_state(), "import_status": self.import_status,
            "library": {"version": self.library.version, **self.library.counts()},
            "community": self.community.region_view(shard, _region(shard)) if self.cfg.get("community_board") else None,
            # {on, fed_week, status}: fed_week is how many of your summaries the site counted this week (None: unknown)
            "sharing": {"on": bool(self.cfg.get("share_readings")),
                        "fed_week": self.community.fed_week if self.cfg.get("share_readings") else 0,
                        "status": self.community.share_status if self.cfg.get("share_readings") else "off"},
            "pirates_here": self.groups.pirates_here() if self.cfg.get("community_board")
            else {"here": None, "elsewhere": None, "area_name": None},
            "groups_on_shard": self.groups.groups_on_shard() if self.cfg.get("community_board") else 0,
            "crash": self.crash_state(),
            "unplayable": self.alerts.unplayable,
            "setup_needed": self.setup_needed, "setup_ask": self.setup_ask,
            "update": self.updater.info(), "patch": self.patch_state(), "notice": self.notice_state(), "alerts": list(self.alerts.recent)[:5],
            "migrated_from": self.cfg.get("migrated_from") if self.cfg.get("migrated_notice") else None,
            "marks": self.marks(), "hotkey": self.hotkey.status,
            "readings_paused": bool(self.watcher and self.watcher.status.startswith("overlay off")),
            "groups": {"open": self.groups.open, "mine": self.groups.mine(), "interest": self.groups.interest_rows()[:10],
                       "offer": self.groups.pirate_offer()},
        }
        from .groups import chat_lines
        out["chat_lines"] = chat_lines(out, a)
        return out

    def _where(self, health):
        """Where you are from the latest overlay reading: the place, its area and your game server's number."""
        with self.lock:
            last = next((x for x in reversed(self.snaps) if x.get("location")), None)
        if not last or time.time() - last["ts"] > 900:
            return None
        p = self.community.places
        w = p.where(last["location"]) or {}
        node = node_of(last.get("server_name"))
        return {"place": p.place(last["location"]), "area_name": w.get("area_name"), "server": node,
                "pop_srv": last.get("pop_srv")}

    PATCH_NOTICE_S = 36 * 3600

    def patch_state(self):
        """Notices a new game build: the first day after a patch, servers are often busier and slower, and the
        'your usual fps on this patch' comparison starts again from nothing."""
        b = self.build
        if not b:
            return None
        last = self.store.meta("last_build")
        if last != b:
            if last:
                self.store.set_meta("prev_build", last)
                self.store.set_meta("patch_seen_at", int(time.time()))
            self.store.set_meta("last_build", b)
        prev, at = self.store.meta("prev_build"), int(self.store.meta("patch_seen_at", 0) or 0)
        new = bool(prev and prev != b and time.time() - at < self.PATCH_NOTICE_S
                   and self.store.meta("patch_dismissed") != b)
        out = {"build": b, "previous": prev, "new": new, "since": at or None}
        if new:
            out["fixes"] = self.patch_fixes(b, at)
        return out

    FIX_LOOKBACK_S = 14 * 86400

    def patch_fixes(self, build, since):
        """CIG's listed fixes for this patch, each marked "you" when this player hit the problem in the fortnight
        before the patch (from their own logbackups and session list, read once per build in the background)."""
        # The fixes this build brought: its number is at or past the PTU build that listed them, and the build
        # before wasn't (the Branch line can't be trusted to name the patch)
        prev = str(self.store.meta("prev_build") or "")
        b = str(build or "")
        fixes = [f for f in getattr(getattr(self, "library", None), "cig_fixes", [])
                 if f.get("ptu") and b.isdigit() and int(b) >= f["ptu"] and not (prev.isdigit() and int(prev) >= f["ptu"])]
        if not fixes:
            return []
        import json
        key = f"patch_fix_hits:{build}"
        cached = self.store.meta(key)
        if cached is None:
            if not getattr(self, "_fix_scan", None):
                self._fix_scan = threading.Thread(target=self._scan_fix_hits, args=(key, fixes, since), daemon=True)
                self._fix_scan.start()
            hits = None
        else:
            try:
                hits = set(json.loads(cached))
            except ValueError:
                hits = set()
        rules = {r.id: r for r in self.library.rules}
        return [{"id": f["id"], "said": f["said"], "starc": f["starc"], "ask": f["ask"], "patch": f["patch"],
                 "titles": [rules[r].d.get("title", r) for r in f["rules"] if r in rules],
                 "you": None if hits is None else f["id"] in hits} for f in fixes]

    def _scan_fix_hits(self, key, fixes, since):
        """Which listed fixes this player would have noticed: a linked rule matched in their logs, or a crash for
        the crash fixes, in the 14 days before the patch arrived."""
        import json
        from .logparse import LINE, TEAMS, _joined_lines
        start, end = (since or time.time()) - self.FIX_LOOKBACK_S, since or time.time()
        want = {r: f["id"] for f in fixes for r in f["rules"]}
        hits = set()
        try:
            folder = self.game_dir / "logbackups"
            files = [p for p in folder.glob("*.log") if start <= p.stat().st_mtime <= end + 3600] if folder.exists() else []
            for p in files:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    for raw in _joined_lines(fh):
                        m = LINE.match(raw)
                        if not m or not (m.group(2) or m.group(3)):
                            continue
                        msg = TEAMS.sub("", m.group(4) or "").rstrip()
                        rule, _ = self.library.match(m.group(2), m.group(3) or "", msg)
                        if rule is not None and rule.id in want:
                            hits.add(want[rule.id])
            if any(f.get("measure") == "crashes" for f in fixes):
                if any(s.get("crashed") or s.get("crash") for s in self.store.sessions(limit=80)
                       if start <= (s.get("start") or 0) <= end):
                    hits.update(f["id"] for f in fixes if f.get("measure") == "crashes")
        except Exception as e:
            say(f"Couldn't check past logs against the patch notes ({e}).")
        self.store.set_meta(key, json.dumps(sorted(hits)))
        self._fix_scan = None

    def notice_state(self, now=None):
        """The message of the week from verseshards.com: it comes with the board the app already downloads when "Show
        other shards" is on, so it costs no extra request and sends nothing. Shown until its end date or until Hide."""
        if not self.cfg.get("community_board"):
            return None
        n = (self.community.board or {}).get("notice") if isinstance(self.community.board, dict) else None
        if not isinstance(n, dict) or not n.get("id") or not n.get("text"):
            return None
        url = str(n.get("url") or "")
        try:
            ends = float(n.get("ends") or 0)          # a bad value from the board hides the message, never the Now tab
        except (TypeError, ValueError):
            ends = 0
        if not url.startswith("https://") or ends <= (now or time.time()):
            return None
        if self.store.meta("notice_dismissed") == str(n["id"]):
            return None
        return {"id": str(n["id"])[:16], "text": str(n["text"])[:200], "label": str(n.get("label") or "Have a look")[:40], "url": url[:300]}

    def quit(self):
        """Close the app (the updater calls this once the new installer is running)."""
        self.quitting = True
        self.stop.set()

    def dismiss(self, what):
        from .config import save_setting
        if what == "migrated":
            self.cfg["migrated_notice"] = False
            save_setting("migrated_notice", False)
            return "OK."
        if what == "patch":
            self.store.set_meta("patch_dismissed", self.build or "")
            return "OK."
        if what == "notice":
            n = (self.community.board or {}).get("notice") if isinstance(self.community.board, dict) else None
            self.store.set_meta("notice_dismissed", str((n or {}).get("id") or ""))
            return "OK."
        raise ValueError("Unknown notice.")

    def _live_session(self):
        """The session the live tail has already read, so a check doesn't parse the whole Game.log again (a long
        session took seconds). Only when the tail is on Game.log and caught up; otherwise None (diagnose parses)."""
        t = getattr(self, "tail", None)
        s = getattr(t, "session", None)
        try:
            if s is None or Path(t.path) != Path(self.game_dir / "Game.log"):
                return None
            return s if Path(t.path).stat().st_size - (t.pos or 0) < 512 * 1024 else None
        except (OSError, TypeError, AttributeError):
            return None

    RED_TTL_S = 120

    def _redactor(self):
        """The redactor for this Game.log (every handle in it), made once and reused for two minutes, or until the
        game starts a new log: building it reads the whole file."""
        path = self.game_dir / "Game.log"
        try:
            st = path.stat()
            key = (str(path), st.st_ino, st.st_size // (4 * 1024 * 1024))
        except OSError:
            key = (str(path), None, None)
        c = getattr(self, "_red_cache", None)
        if c and c[0] == key and time.time() - c[1] < self.RED_TTL_S:
            return c[2]
        red = community.make_redactor(path)
        self._red_cache = (key, time.time(), red)
        return red

    def run_diagnosis(self, minutes=None, mark_ts=None):
        minutes = int(minutes or self.cfg.get("lookback_minutes", 30))
        mark = next((m for m in self.marks(24 * 3600) if mark_ts and abs(m["ts"] - float(mark_ts)) < 1), None)
        if mark:
            import math
            # Back to half an hour before the mark however late it's opened, for the "earlier" problems (EARLIER_S)
            minutes = min(24 * 60, max(minutes, math.ceil((time.time() - mark["ts"]) / 60) + self.EARLIER_S // 60 + 1))
        with self.lock:
            snaps = list(self.snaps)
        res = diagnose(self.game_dir / "Game.log", self.library, self.names, snaps, lookback_min=minutes,
                       backups_dir=self.game_dir / "logbackups", session=self._live_session())
        res["checked_at"] = time.time()
        res["mark"] = mark
        # What CIG's patch notes say about each problem: a fix coming in a later patch, or one listed that hasn't held
        from .issues import fix_for
        branch = getattr(self.session, "branch", None) or (res.get("session") or {}).get("branch")
        for f in res.get("findings", []):
            note = fix_for(getattr(self.library, "cig_fixes", []), f.get("rule_id"), branch,
                           getattr(self, "build", None) or (res.get("session") or {}).get("build"))
            if note:
                f["cig_fix"] = note
        if mark:
            # The marked moment first: findings within 10 minutes of it, nearest first
            def dist(f):
                a, b = f.get("first_ts") or 0, f.get("last_ts") or f.get("first_ts") or 0
                return 0 if a - 600 <= mark["ts"] <= b + 600 else min(abs(mark["ts"] - a), abs(mark["ts"] - b))
            for f in res["findings"]:
                f["near_mark"] = dist(f) == 0
            res["findings"].sort(key=lambda f: (not f["near_mark"], dist(f)))
        self.last_result = res
        return res

    def history(self):
        return {"sessions": self.store.sessions(), "shards": self.store.shard_history(),
                "hourly": self.store.hourly(), "import_status": self.import_status,
                "ships_retrieved": self.ships_retrieved()}

    def ships_retrieved(self):
        """Ships you called from an ASOP terminal on this patch, most first: past sessions plus this one."""
        from .timeline import ship_name
        build = self.build or (self.session.build if self.session else None)
        counts = self.store.ships_retrieved(build)
        if self.session:
            for k, n in self.session.ships_retrieved().items():
                counts[k] = counts.get(k, 0) + n
        return [{"ship": ship_name(k), "times": n} for k, n in sorted(counts.items(), key=lambda x: -x[1])][:12]

    def crash_state(self):
        """The game log ended with the crash handler taking over: when, and the library entry it matched, if any."""
        s = self.session
        if not s or not s.crash:
            return None
        ts = s.crash.get("ts") or s.end
        key = (s.name, ts)
        if getattr(self, "_crash_key", None) != key:
            code = None
            try:
                from .diagnose import crash_findings
                found = [f for f in crash_findings(self.game_dir / "Game.log", self.library, s) if f.get("rule_id")]
                code = found[0]["rule_id"] if found else None
            except Exception:
                code = None
            self._crash_key, self._crash_code = key, code
        return {"ts": ts, "after_code": self._crash_code}

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

    def timeline(self, minutes=60):
        """What happened in the last `minutes` of the current session, in plain English."""
        from .timeline import GROUPS, timeline
        try:
            minutes = max(5, min(int(minutes or 60), 24 * 60))
        except (TypeError, ValueError):
            minutes = 60
        s = self.session
        end = (s.end if s and s.end else time.time())
        items = timeline(s, self.places, since=end - minutes * 60) if s else []
        for m in self.marks(minutes * 60):
            items.append({"ts": m["ts"], "group": "other", "kind": "mark", "text": "You marked this moment", "code": None, "area": None})
        items.sort(key=lambda x: x["ts"])
        return {"minutes": minutes, "items": items, "groups": GROUPS, "game_found": self.game_found,
                "session_start": s.start if s else None, "session_end": s.end if s else None}

    def _draft(self, f, ic_link=None):
        mark = (self.last_result or {}).get("mark")
        if mark and not f.get("near_mark"):
            mark = None                     # the mark is about something else; this finding has its own time
        at = mark["ts"] if mark else f.get("first_ts")
        snap = self._snap_at(at) if at else None
        if snap is None and (not at or time.time() - at < 900):
            snap = self.latest_snap()
        channel = self.channel
        return report.draft(f, self.last_result, snap, session=self.session, places=self.places, names=self.names,
                            mark=mark, channel=channel, ic_link=ic_link)

    def _snap_at(self, ts):
        with self.lock:
            near = [x for x in self.snaps if x.get("ok") and abs(x["ts"] - ts) <= 300]
        return min(near, key=lambda x: abs(x["ts"] - ts)) if near else None

    def ic_links(self, rule_id):
        """Issue Council reports players have linked for this issue on Verse Shards, most upvoted first (a plain
        lookup, only when the community board or library updates are on)."""
        if not rule_id or not (self.cfg.get("community_board") or self.cfg.get("library_updates")):
            return []
        try:
            code, d = self.community._req(f"/api/v1/issue/{rule_id}")
        except Exception:
            return []
        if code != 200:
            return []
        links = [x for x in d.get("links", []) if x.get("kind") == "issue-council"]
        return sorted(links, key=lambda x: -(x.get("votes") or 0))

    def ic_link(self, rule_id):
        links = self.ic_links(rule_id)
        return links[0] if links else None

    def report_draft(self, group, i):
        f = self._finding(group, i)
        links = self.ic_links(f.get("rule_id")) if group != "unknown" else []
        d = self._draft(f, links[0] if links else None)
        d["url"] = report.ISSUE_COUNCIL
        # For "After you post": this issue's page on Verse Shards, and the reports already linked there
        d["rule_id"] = f.get("rule_id") if group != "unknown" else None
        d["linked"] = []
        for x in links[:6]:
            m = re.search(r"STARC-\d+", x.get("url") or "", re.I)
            if m:
                d["linked"].append({"id": m.group(0).upper(), "title": x.get("title") or m.group(0).upper(),
                                    "url": x.get("url"), "votes": x.get("votes") or 0})
        return d

    # -- Mark this moment: the moment itself, screenshots around it, sent for review, an Issue Council draft
    def _mark_at(self, ts):
        try:
            ts = float(ts)
        except (TypeError, ValueError):
            raise ValueError("No such moment.")
        m = next((x for x in self.marks(24 * 3600) if abs(x["ts"] - ts) < 1), None)
        if not m:
            raise ValueError("That moment is more than a day old, or wasn't marked on this PC.")
        return m

    def _shot_dir(self):
        return self.game_dir / "screenshots"

    def moment_shots(self, ts, now=None):
        """Screenshots from 10 minutes before the moment up to 10 minutes after it (or now, if later)."""
        from .screenshots import list_shots
        m = self._mark_at(ts)
        now = now or time.time()
        return list_shots(self._shot_dir(), m["ts"] - 600, max(m["ts"] + 600, now))

    def moment(self, ts):
        """Everything the app has for a marked second: where, the readings, the log either side, what it found."""
        from .timeline import timeline
        m = self._mark_at(ts)
        t = m["ts"]
        snap = self._snap_at(t)
        if snap is None:
            rows = [x for x in self.store.snapshots(since=t - 300, limit=400) if abs(x.get("ts", 0) - t) <= 300 and x.get("ok", True)]
            snap = min(rows, key=lambda x: abs(x["ts"] - t)) if rows else None
        snap = snap or {}
        shard = m.get("shard_id") or snap.get("shard_id")
        server = node_of(m.get("server") or snap.get("server_name"))
        place = self.places.place(m.get("location") or snap.get("location")) or None
        res = self.run_diagnosis(None, t)
        findings, earlier = moment_findings(res.get("findings", []), t, self.EARLIER_S)
        log = []
        s = self.session
        if s:
            for it in timeline(s, self.places, since=t - 300, until=t + 300):
                bad = it["group"] == "connection" and it["kind"] in ("disconnect", "crash")
                log.append({"ts": it["ts"], "text": it["text"],
                            "kind": "bad" if bad else "travel" if it["group"] in ("travel", "place") else ""})
        for f in findings:
            for when in {f["first_ts"], f["last_ts"]}:
                if when and abs(when - t) <= 300:
                    log.append({"ts": when, "text": f["title"], "kind": "bad"})
        log.append({"ts": t, "text": "You marked this moment", "kind": "mark"})
        log.sort(key=lambda x: x["ts"])
        detail = self._moment_detail(t, res, snap, findings, earlier)
        out = {"ts": t, "shard_id": shard, "shard_name": community.shard_name(shard) if shard else None,
                "server": server, "place": place,
                "readings": {"server_fps": snap.get("server_fps"), "pop_srv": snap.get("pop_srv"), "ping_ms": snap.get("ping_ms")},
                "log": log[-40:], "findings": findings[:6], "earlier": earlier[:6], "shots": self.moment_shots(t),
                "board": bool(self.cfg.get("community_board")),
                "send": {"issues": [f["rule_id"] for f in findings if f.get("rule_id")][:10], "detail": detail,
                         "lines": self._moment_send_lines(detail)}}
        self._moment_last = (t, time.time(), out)
        return out

    # A moment noticed late: known problems this long before the mark go with it as "earlier"
    EARLIER_S = 30 * 60
    # Kinds of thing that happened in the 5 minutes before the mark. Only the kind and how long before, never the
    # text, a place, a ship or a contract name
    EVENT_KINDS = {"join", "loaded", "qt_target", "qt_arrived", "location", "armistice", "ship_retrieved", "accepted",
                   "objective_complete", "objective_failed", "contract_complete", "contract_failed", "contract_abandoned",
                   "contract_dropped", "elevator", "left", "disconnect", "quit", "crash"}

    def _moment_detail(self, t, res, snap, findings, earlier):
        """What a moment sent for review carries besides the description and the issue ids near it, so it can be
        diagnosed without the player's files: known problems from the half hour before, the codes of errors the
        library doesn't know yet (names and numbers already stripped), the kinds of thing that happened in the 5
        minutes before, a server change, the area (never the place), the server's number and fps, the app version."""
        from .timeline import timeline
        d = {"earlier": [{"id": f["rule_id"], "min": f["min_before"]} for f in earlier[:6]]}
        # Errors the library doesn't know, within 10 minutes of the mark. Signatures are already normalised; one
        # that still holds a handle from this log is dropped, not sent
        handles, red = [], None
        try:
            get = getattr(self, "_redactor", None)
            red = get() if callable(get) else community.make_redactor(self.game_dir / "Game.log")
            handles = red.handles
        except Exception:
            pass
        from .redact import leaks
        unk = []
        for f in res.get("unknown", []):
            a, b = f.get("first_ts") or 0, f.get("last_ts") or f.get("first_ts") or 0
            sig = (f.get("fields") or {}).get("sig")
            if not sig or not (a - 600 <= t <= b + 600):
                continue
            from .redact import scrub_code
            if red is not None and red.line(sig) != sig:
                continue                       # a name or number the redactor would strip: not sent at all
            sig = scrub_code(sig)              # quoted text (a channel or org name) becomes '<TEXT>'
            if leaks(sig, handles):
                continue
            level = "error" if "error" in (f.get("title") or "").lower() else "warning"
            unk.append({"sig": sig[:200], "n": int(f.get("count") or 1), "level": level})
        d["unknown"] = unk[:5]
        # What was happening: event kinds in the 5 minutes before, and a change of game server from the readings
        ev = []
        s = self.session
        if s:
            for it in timeline(s, self.places, since=t - 300, until=t):
                if it["kind"] in self.EVENT_KINDS:
                    ev.append({"k": it["kind"], "s": int(max(0, t - it["ts"]))})
        try:
            rows = [x for x in self.store.snapshots(since=t - 300, limit=400) if x.get("ts", 0) <= t and x.get("server_name")]
        except Exception:
            rows = []
        rows.sort(key=lambda x: x["ts"])
        for ts in settled_changes(rows):
            ev.append({"k": "server_change", "s": int(max(0, t - ts))})
        ev.sort(key=lambda e: -e["s"])
        d["events"] = ev[-12:]
        w = self.community.places.where(snap.get("location")) if snap.get("location") else None
        if w and w.get("area_name"):
            d["area"] = {"system": w.get("system"), "area_name": w.get("area_name")}
        node = node_of(snap.get("server_name"))
        if node:
            d["server"] = node
        if snap.get("server_fps") is not None:
            d["fps"] = round(float(snap["server_fps"]), 1)
        return d

    EVENT_WORDS = {"join": "joined a shard", "loaded": "loaded in", "qt_target": "set a quantum course",
                   "qt_arrived": "arrived from quantum", "location": "moved to a new place", "armistice": "armistice zone",
                   "ship_retrieved": "retrieved a ship", "accepted": "accepted a contract",
                   "objective_complete": "finished an objective", "objective_failed": "failed an objective",
                   "contract_complete": "finished a contract", "contract_failed": "contract failed",
                   "contract_abandoned": "contract abandoned", "contract_dropped": "contract dropped",
                   "elevator": "used a freight elevator", "left": "left the server", "disconnect": "disconnected",
                   "quit": "quit", "crash": "crashed", "server_change": "changed game server"}

    def _moment_send_lines(self, d):
        """The extra things Send for review carries, in words, so the player sees them before pressing it."""
        out = []
        if d.get("area"):
            out.append(f"The area: {d['area']['area_name']} (never the exact place)")
        if d.get("server") or d.get("fps") is not None:
            out.append("Your game server's number and its fps then" if d.get("server") else "The server's fps then")
        if d.get("earlier"):
            out.append(f"{len(d['earlier'])} known {'problem' if len(d['earlier']) == 1 else 'problems'} from the half hour before, by id")
        if d.get("events"):
            kinds = list(dict.fromkeys(self.EVENT_WORDS.get(e["k"], e["k"]) for e in d["events"]))
            out.append("What was happening in the 5 minutes before: " + ", ".join(kinds[:6]))
        if d.get("unknown"):
            n = len(d["unknown"])
            out.append(f"{n} error {'code' if n == 1 else 'codes'} the app doesn't know yet, with names and numbers stripped")
        return out

    def moment_review(self, ts, what, issues=None):
        """Send the moment for review: the time, game build, shard, the description, the library ids found near
        it, and the detail from _moment_detail. Never screenshots, log lines or the exact place. Pressing Send for
        review is the player's own yes, so it doesn't depend on Show other shards or sharing being on."""
        m = self._mark_at(ts)
        known = {r["id"] for r in self.library.listing()}
        # What goes is worked out here from the moment itself, the same as the player was shown; ids from the page
        # are only kept if the app found them too
        # The moment as the player was shown it, if they opened it in the last 10 minutes (no second read of the log)
        last = getattr(self, "_moment_last", None)
        try:
            mo = last[2] if last and last[0] == m["ts"] and time.time() - last[1] < 600 else self.moment(m["ts"])
            ids, detail = mo["send"]["issues"], mo["send"]["detail"]
        except Exception as e:
            # Never send an empty review without saying so (audit, 4 Nov): the player is told it couldn't be worked out
            say(f"Couldn't work out the moment at {m['ts']} for review ({e}).")
            raise ValueError("Couldn't work this moment out just now, so nothing was sent. Try again in a minute.")
        ids = [i for i in ids if i in known]
        out = self.community.send_moment(m["ts"], self.build, m.get("shard_id"), what, ids, detail)
        titles = [x.get("title") for x in out["matched"] if x.get("title")]
        return {"matched": out["matched"],
                "message": (f"Counted. It matches \u201c{titles[0]}\u201d, so it shows as a player who hit it today on that issue's page."
                            if titles else "Thanks, sent.")}

    def moment_draft(self, ts, what="", shots=None):
        """An Issue Council draft for the moment: its time, your description and what the log shows, in a report
        folder with Game.log and the screenshots you picked."""
        m = self._mark_at(ts)
        res = self.last_result if (self.last_result or {}).get("mark") and abs(self.last_result["mark"]["ts"] - m["ts"]) < 1 \
            else self.run_diagnosis(None, m["ts"])
        what = re.sub(r"\s+", " ", (what or "")).strip()[:200]
        near = [(i, f) for i, f in enumerate(res["findings"]) if f.get("near_mark") and f.get("kind", "problem") == "problem"]
        from .issues import ask_matching, has_fix
        branch = getattr(self.session, "branch", None) or (res.get("session") or {}).get("branch")
        build = getattr(self, "build", None) or (res.get("session") or {}).get("build")
        ask = ask_matching(getattr(self.library, "cig_fixes", []), branch, what, build)
        if near and not ask:
            i, f = near[0]
        elif ask:
            # Something CIG asked players to report (e.g. hangars overlapping): its own title and words, and the
            # note that the patch notes listed a fix, so the report says it hasn't held
            state = "listed" if has_fix(ask, branch, build) else "coming"
            f = {"title": ask["ic_title"], "ic_title": ask["ic_title"], "area": "Hangar", "severity": "medium", "kind": "problem",
                 "first_ts": m["ts"], "last_ts": m["ts"], "count": 1, "explain": ask["explain"], "fixes": [], "examples": [],
                 "fields": {}, "near_mark": True, "rule_id": None, "moment": True,
                 "cig_fix": {"id": ask["id"], "patch": ask["patch"], "said": ask["said"], "starc": ask["starc"], "how": "same",
                             "ask": True, "state": state}}
            res["findings"].append(f)
            i = len(res["findings"]) - 1
        else:
            f = {"title": what or "Problem at the moment I marked", "area": "", "severity": "medium", "kind": "problem",
                 "first_ts": m["ts"], "last_ts": m["ts"], "count": 1, "explain": "", "fixes": [], "examples": [],
                 "fields": {}, "near_mark": True, "rule_id": None, "moment": True}
            res["findings"].append(f)
            i = len(res["findings"]) - 1
        if what and ask:
            f["ic_summary"] = f"{what.rstrip('.')}. {ask['explain']}"
        if what and not ask:
            base = f.get("ic_summary", "").strip() or f"{f['title'].rstrip('.')}. {f.get('explain', '').strip()}".strip()
            if not base.startswith(what.rstrip(".")):
                f["ic_summary"] = f"{what.rstrip('.')}. {base}" if not f.get("moment") else f"{what.rstrip('.')}."
        d = self._draft(f)
        names = [x for x in (shots or []) if isinstance(x, str)][:10]
        folder, n = report.bundle(f, res, d, self.game_dir, shots=names)
        from .screenshots import shot_path
        return {"folder": str(folder), "screenshots": n, "group": "findings", "i": i,
                "shot_names": [x for x in names if shot_path(self._shot_dir(), x)]}

    def report_bundle(self, group, i, text=None):
        f = self._finding(group, i)
        d = self._draft(f)
        if text and isinstance(text, str):
            d["body"] = text[:200_000]      # the player's edited version from the dashboard
            if report.DISCLAIMER not in d["body"]:
                d["body"] += "\n" + report.DISCLAIMER + "\n"
        folder, n = report.bundle(f, self.last_result, d, self.game_dir)
        return {"folder": str(folder), "screenshots": n}

    def review(self, i, save=False, send=False):
        """Prepare an unrecognised error for review (shown to the player first), keep it, and send it if asked."""
        f = self._finding("unknown", i)
        red = self._redactor()
        sess = dict(self.last_result["session"])
        sess["region"] = _region(sess.get("shard_id"))
        contracts = [c["name"] for c in (self.session.contracts.values() if self.session else [])]
        rid, payload = community.review_request(f, sess, red, self.store.install_id(), contracts)
        if (save or send) and not payload.get("checked_clean"):
            raise ValueError("Something identifying was still in it, so it can't be kept or sent.")
        if save or send:
            self.store.add_review(rid, payload["sig"], payload)
        sent = None
        if send:
            sent = self.libsync.send_review(rid, payload)
        return {"ticket": rid, "payload": payload, "saved": bool(save or send), "sent": bool(sent),
                "status": (sent or {}).get("status"), "answer": (sent or {}).get("answer")}

    def send_saved_review(self, rid):
        r = self.store.review(rid)
        if not r:
            raise ValueError("No such review.")
        if not r["data"].get("checked_clean"):
            raise ValueError("Something identifying was still in it, so it can't be sent.")
        return self.libsync.send_review(rid, r["data"])

    # -- the game's USER.cfg
    def save_settings(self, live=None, screenshots=None, share=None, board=None, updates=None, library=None,
                      alerts=None, errors=None, hotkey=None):
        """Change settings. Saved to data\\config.json. Reading changes take effect on the next start;
        the community switches take effect straight away."""
        from .config import save_setting
        msg = []
        if live is not None:
            self.cfg["overlay_every_s"] = 5 if live else 0
            save_setting("overlay_every_s", self.cfg["overlay_every_s"])
            self._start_live() if live else self._stop_live()
            msg.append("Live screen reading on." if live else "Live screen reading off.")
        if screenshots is not None:
            self.cfg["read_screenshots"] = bool(screenshots)
            save_setting("read_screenshots", self.cfg["read_screenshots"])
            self._start_shots() if screenshots else self._stop_shots()
            msg.append("Reading your screenshots." if screenshots else "Not reading screenshots.")
        if share is not None:
            self.cfg["share_readings"] = bool(share)
            save_setting("share_readings", self.cfg["share_readings"])
            if share:                               # turned on beside the current wording, so no need to ask again
                self.cfg["share_text_seen"] = self.QUESTIONS["share"]
                save_setting("share_text_seen", self.cfg["share_text_seen"])
            if share and self.community.share_status in ("off", ""):
                self.community.share_status = "starting"
            msg.append("Sharing on. Your first summary goes after 5 minutes of overlay readings." if share
                       else "Sharing off. Nothing more is sent.")
        if board is not None:
            self.cfg["community_board"] = bool(board)
            save_setting("community_board", self.cfg["community_board"])
            if board:
                self.community.board_at = 0          # fetch now
            msg.append("Community board on." if board else "Community board off.")
        if updates is not None:
            self.cfg["check_updates"] = bool(updates)
            save_setting("check_updates", self.cfg["check_updates"])
            if updates and not self.updater.checked_at:
                threading.Thread(target=self.updater.check, daemon=True).start()
            msg.append("Checking for new versions." if updates else "Not checking for new versions.")
        if library is not None:
            self.cfg["library_updates"] = bool(library)
            save_setting("library_updates", self.cfg["library_updates"])
            if library and not self.libsync.checked_at:
                threading.Thread(target=self.libsync.update_library, daemon=True).start()
            msg.append("Keeping the known-issues library up to date." if library
                       else "Using the known-issues library that came with the app.")
        if alerts is not None:
            mode = alerts if alerts in ("sound", "quiet") else None
            self.cfg["alerts"] = mode
            save_setting("alerts", mode)
            msg.append({"sound": "Pop-up alerts on, with a sound.", "quiet": "Pop-up alerts on, without a sound."}
                       .get(mode, "Pop-up alerts off."))
        if errors is not None:
            self.cfg["send_errors"] = bool(errors)
            save_setting("send_errors", self.cfg["send_errors"])
            msg.append("Sending app error reports, so faults get fixed." if errors else "Not sending app error reports.")
        if hotkey is not None:
            from .hotkey import CHOICES, LABELS
            combo = hotkey if hotkey in CHOICES else None
            self.cfg["mark_hotkey"] = combo
            save_setting("mark_hotkey", combo)
            st = self.hotkey.set(combo)
            msg.append(f"Mark this moment hotkey: {LABELS[combo]}." if combo and st.startswith("on") else
                       ("Mark this moment hotkey off." if not combo else f"Hotkey not set: {st}."))
        return " ".join(msg) or "Saved."

    # -- first-run questions: every setting is a yes/no the player has to answer once
    # Each question and the set-up version it arrived in. Raise SETUP_VERSION when adding one: players who have
    # already been through set-up are asked only the new ones.
    # share is 3: 1.2 added the area and session stats to what's shared, so sharers are asked again
    # share is 4: 1.3 adds reading-quality counts and the game's wording for disconnects, so sharers are asked again
    QUESTIONS = {"game": 1, "displayinfo": 1, "sessioninfo": 1, "live": 1, "screenshots": 1, "board": 1, "share": 4,
                 "updates": 2, "library": 2, "alerts": 2, "errors": 4}
    SETUP_VERSION = max(QUESTIONS.values())

    @property
    def setup_needed(self):
        return bool(self.setup_ask)

    @property
    def setup_ask(self):
        """The questions this player still has to answer (all of them on a first start)."""
        done = int(self.cfg.get("setup_version") or 0)
        # The sharing question changed in 1.2; only people already sharing need to see it again
        return [k for k, since in self.QUESTIONS.items() if since > done
                and not (k == "share" and done and (not self.cfg.get("share_readings")
                                                    or int(self.cfg.get("share_text_seen") or 0) >= since))]

    def apply_setup(self, c):
        """c: {game: "ok"|"later"|<path>, displayinfo, sessioninfo, live, screenshots, board, share, updates}
        (booleans). Only the questions still to answer are required; any others given are applied too."""
        from .config import save_setting
        given = {k: v for k, v in c.items() if k in self.QUESTIONS and v is not None and v != ""}
        missing = [k for k in self.setup_ask if k not in given]
        if missing:
            raise ValueError("Answer every question first (" + ", ".join(missing) + ").")
        notes = []
        g = given.get("game")
        if g not in (None, "ok", "later"):
            self.set_game_dir(g)
        cfg_wanted = {name: bool(given[k]) for k, name in (("displayinfo", "r_displayinfo"),
                                                         ("sessioninfo", "r_DisplaySessionInfo")) if k in given}
        if cfg_wanted:
            if self.game_found:
                for name, on in cfg_wanted.items():
                    self.set_user_cfg(name, on)
            else:
                # Applied when the game folder turns up (set_game_dir)
                self.cfg["pending_user_cfg"] = cfg_wanted
                save_setting("pending_user_cfg", cfg_wanted)
                notes.append("The USER.cfg choices will be saved once the game folder is found.")
        self.save_settings(**{k: bool(given[k]) for k in ("live", "screenshots", "share", "board", "updates", "library",
                                                          "errors") if k in given})
        if "alerts" in given:
            self.save_settings(alerts=given["alerts"])
        self.cfg["setup_version"] = self.SETUP_VERSION
        save_setting("setup_version", self.SETUP_VERSION)
        return " ".join(["All set. You can change any of these on the Set up tab."] + notes)

    def settings(self):
        c = self.community
        return {"live": float(self.cfg.get("overlay_every_s") or 0) > 0,
                "screenshots": bool(self.cfg.get("read_screenshots", True)),
                "live_running": self.watcher is not None, "screenshot_readings": self.shots.count if self.shots else None,
                "share": bool(self.cfg.get("share_readings")), "board": bool(self.cfg.get("community_board")),
                "share_status": c.share_status, "sent": c.sent, "sent_at": c.sent_at if c.sent else None,
                "last_payload": c.last_payload,
                "board_url": c.url, "board_error": c.board_error,
                # off until the update question is answered, since nothing is checked before then
                "updates": self.updater.enabled, "update": self.updater.info(),
                "library": bool(self.cfg.get("library_updates")), "library_sync": self.libsync.info(),
                "alerts": self.alerts.info(), "errors": bool(self.cfg.get("send_errors")),
                "errors_sent": self.errors.sent_n, "errors_payload": self.errors.last_payload,
                "hotkey": self.cfg.get("mark_hotkey"), "hotkey_status": self.hotkey.status}

    # Settings the app can put in USER.cfg: name -> value to set
    CFG_SETTINGS = {"r_displayinfo": 3, "r_DisplaySessionInfo": 1}

    @property
    def game_found(self):
        from .config import game_dir_ok
        return game_dir_ok(self.cfg.get("game_dir"))

    def user_cfg_state(self):
        if not self.game_found:
            return {"exists": False, "path": None, "game_found": False, "has_displayinfo": None,
                    "has_sessioninfo": None, **{k: None for k in self.CFG_SETTINGS}}
        p = self.game_dir / "USER.cfg"
        out = {"exists": p.exists(), "path": str(p), "game_found": True}
        try:
            txt = read_cfg(p)[0] if p.exists() else ""
        except OSError:
            txt = None
        for name in self.CFG_SETTINGS:
            m = re.search(rf"^\s*{name}\s*=\s*(\d+)", txt or "", re.I | re.M)
            out[name] = int(m.group(1)) if m else None
        out["has_displayinfo"] = bool(out["r_displayinfo"]) if txt is not None else None
        out["has_sessioninfo"] = bool(out["r_DisplaySessionInfo"]) if txt is not None else None
        return out

    def set_user_cfg(self, name, on=True):
        """Add (or turn off) one of CFG_SETTINGS in the game's USER.cfg, keeping its encoding and line endings.
        The file as it was before each change is kept as USER.cfg.bak."""
        if name not in self.CFG_SETTINGS:
            raise ValueError("That setting can't be changed from here.")
        if not self.game_found:
            raise ValueError("Game folder not found yet. Start Star Citizen and the app picks it up, or paste your "
                             "StarCitizen\\LIVE folder in the Game folder box on this tab.")
        p = self.game_dir / "USER.cfg"
        if p.exists():
            txt, enc, nl = read_cfg(p)
        else:
            txt, enc, nl = "", "utf-8", "\r\n"
        val = self.CFG_SETTINGS[name] if on else 0
        rx = re.compile(rf"^(\s*{name}\s*=\s*)\d+", re.I | re.M)
        if rx.search(txt):
            new = rx.sub(lambda m: m.group(1) + str(val), txt)
        elif on:
            new = txt.rstrip("\r\n") + (nl if txt.strip() else "") + f"{name} = {val}" + nl
        else:
            new = txt
        if p.exists():
            p.with_name("USER.cfg.bak").write_bytes(p.read_bytes())
        p.write_bytes(new.encode(enc))
        verb = f"Set {name} = {val}" if on else f"Turned off {name}"
        return f"{verb} in USER.cfg. It takes effect the next time the game starts; type it in the console to use it now."

    def add_displayinfo(self):
        return self.set_user_cfg("r_displayinfo")


def read_cfg(p):
    """USER.cfg -> (text, encoding to write it back in, line ending). Handles UTF-8 (with or without a BOM),
    UTF-16 (Notepad's 'Unicode', PowerShell 5) and old Windows-1252 files."""
    raw = Path(p).read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        enc = "utf-16"
    elif raw.startswith(b"\xef\xbb\xbf"):
        enc = "utf-8-sig"
    else:
        try:
            raw.decode("utf-8")
            enc = "utf-8"
        except UnicodeDecodeError:
            enc = "cp1252"
    txt = raw.decode(enc)
    nl = "\r\n" if "\r\n" in txt or "\n" not in txt else "\n"
    return txt, enc, nl


def _close(a, b):
    """Same length and at most two characters different: an OCR slip, not a different shard."""
    return len(a) == len(b) and sum(x != y for x, y in zip(a, b)) <= 2


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


def _last_loc(session):
    for e in reversed(getattr(session, "travel", []) if session else []):
        if e["kind"] == "location":
            return e["code"]
    return None


def _region(shard_id):
    from .logparse import region_of
    return region_of(shard_id)


def open_folder(path):
    if os.name == "nt":
        os.startfile(str(path))     # noqa: S606 (local folder the app made)
