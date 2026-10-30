"""What's shared with the community board, and the code that shares it.

Nothing is sent unless you switch sharing on (Set up tab). When it's on, the app
sends one 5-minute summary of your overlay readings; the Set up tab shows the
exact last payload. Reading the board (other shards in your region) is a
separate switch and sends nothing about you.

Rules: no handle, no other players' names, no account or entity numbers, no
session id, no IP address, no file paths. Times are rounded to the minute.
"""

import hashlib
import json
import statistics as st
import time
import urllib.error
import urllib.request

from .redact import Redactor, leaks

PAYLOAD_VERSION = 1


def _r(v, step):
    return None if v is None else round(round(v / step) * step, 3)


REGION_TAGS = {"apse2": "AU", "apse1": "AS", "ape1": "AS", "apne1": "AS", "use1": "USE", "use2": "USE", "usw1": "USW",
               "usw2": "USW", "euw1": "EU", "euw2": "EU", "euc1": "EU", "eun1": "EU"}


def shard_name(shard_id):
    """CIG don't name shards; ours is the region tag and shard number: pub_apse2a_12881860_020 -> AU-20."""
    import re
    m = re.fullmatch(r"[a-z]+_([a-z]+\d)[a-z]?_\d+_(\d+)", shard_id or "")
    return f"{REGION_TAGS.get(m.group(1), m.group(1).upper())}-{int(m.group(2))}" if m else (shard_id or "")


def shard_report(snap, install_id, build, findings=(), app_version=None, where=None):
    """One health reading (or a 5-minute summary of several) for the live shard status board. `where` is the
    area only (a planet, a jump point or open space: {system, area, area_name}), never the exact place."""
    out = {
        "v": PAYLOAD_VERSION, "kind": "shard", "install": install_id, "build": build,
        "ts": int(snap["ts"] // 60 * 60),
        "shard_id": snap.get("shard_id"),
        "server": (snap.get("server_name") or "").rsplit("-", 1)[-1] or None,   # e.g. "game-07" -> "07"
        "server_fps": snap.get("server_fps"), "server_fps_min": snap.get("server_fps_min"),
        "server_fps_max": snap.get("server_fps_max"), "hitches": snap.get("hitches"),
        "restarts": snap.get("restarts"), "pop_shard": snap.get("pop_shard"), "pop_srv": snap.get("pop_srv"),
        "ping_ms": _r(snap.get("ping_ms"), 10), "loss_pct": snap.get("loss_pct"),
        "issues": sorted({f["rule_id"] for f in findings if f.get("rule_id")}),
        "readings": snap.get("readings", 1), "app": app_version,
    }
    if where:
        out.update(system=where.get("system"), area=where.get("area"), area_name=where.get("area_name"))
    return out


def sessions_report(install_id, sessions, since, now=None):
    """Finished game sessions for the patch report card: build, length, load time, whether it crashed, and the
    error codes of any disconnects. No shard, place, handle or anything else."""
    from .logparse import NORMAL_CAUSES
    now = now or time.time()
    rows = []
    for s in sessions:
        start = s.get("start")
        if not start or start <= since or start < now - 6 * 86400 or not s.get("build"):
            continue
        rows.append({"start": int(start), "build": str(s["build"]), "region": s.get("region"),
                     "minutes": s.get("minutes"), "load_s": s.get("load_s"), "crashed": bool(s.get("crashed")),
                     "disconnects": [c for c in s.get("disconnect_causes", []) if c not in NORMAL_CAUSES][:10]})
    rows.sort(key=lambda r: r["start"])
    return {"v": PAYLOAD_VERSION, "kind": "sessions", "install": install_id, "sessions": rows[:20]} if rows else None


SHARE_EVERY_S = 300
BOARD_EVERY_S = 120
RSI_EVERY_S = 600
SESSIONS_EVERY_S = 1800


def summarise(snaps, now=None, window_s=SHARE_EVERY_S):
    """The last 5 minutes of overlay readings on one shard as a single reading: medians, the lowest server
    fps seen, and how many times the server node restarted in that time (not its lifetime count)."""
    now = now or time.time()
    recent = [s for s in snaps if s.get("ok") and now - s["ts"] <= window_s and s.get("server_fps") is not None]
    if not recent:
        return None
    shard = recent[-1].get("shard_id")
    recent = [s for s in recent if s.get("shard_id") == shard]
    if len(recent) < 3 or not shard:
        return None

    def med(k):
        v = [s[k] for s in recent if s.get(k) is not None]
        return st.median(v) if v else None
    rs = [s["restarts"] for s in recent if s.get("restarts") is not None]
    mins = [s.get("server_fps_min", s["server_fps"]) for s in recent if s.get("server_fps_min", s["server_fps"]) is not None]
    return {
        "ts": recent[-1]["ts"], "shard_id": shard, "server_name": recent[-1].get("server_name"),
        "server_fps": round(med("server_fps"), 1), "server_fps_min": min(mins) if mins else None,
        "server_fps_max": max((s.get("server_fps_max") or s["server_fps"]) for s in recent),
        "hitches": max((s.get("hitches") or 0) for s in recent),
        "restarts": (max(rs) - min(rs)) if rs else None,
        "pop_shard": _int(med("pop_shard")), "pop_srv": _int(med("pop_srv")), "ping_ms": med("ping_ms"),
        "loss_pct": med("loss_pct"), "readings": len(recent),
        "location": _most_common([s.get("location") for s in recent if s.get("location")]),
    }


def _most_common(vals):
    return max(set(vals), key=vals.count) if vals else None


def _int(v):
    return None if v is None else int(round(v))


class Community:
    """Sends your 5-minute summaries (if sharing is on) and keeps a copy of the board (if that's on)."""

    def __init__(self, app, url, version):
        self.app, self.url, self.version = app, (url or "").rstrip("/"), version
        self.board = None
        self.board_at = 0
        self.board_error = None
        self.sent_at = 0
        self.sent = 0
        self.last_payload = None
        self.share_status = "starting" if app.cfg.get("share_readings") else "off"
        self.retry_at = 0
        self.rsi = None
        self.rsi_at = 0
        self.sessions_at = 0
        self.sessions_sent = 0

    def _req(self, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(self.url + path, data=data, headers={
            "content-type": "application/json", "user-agent": f"SCShardStatus/{self.version}"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode() or "{}")
            except Exception:
                return e.code, {}

    @property
    def places(self):
        """Place and area names from the game's text file, read once."""
        from .locations import Places
        gd = getattr(self.app, "game_dir", None)
        key = str(gd)
        if getattr(self, "_places_key", None) != key:
            self._places, self._places_key = Places(gd, self.app.cfg.get("language", "english")), key
        return self._places

    def send_sessions(self, now=None):
        """Finished game sessions since the last ones sent (patch report card). Only with sharing on."""
        now = now or time.time()
        since = float(self.app.store.meta("sessions_sent_upto", 0) or 0)
        payload = sessions_report(self.app.store.install_id(), self.app.store.sessions(limit=60), since, now)
        if not payload:
            return 0
        code, d = self._req("/api/v1/sessions", payload)
        if code == 200:
            self.app.store.set_meta("sessions_sent_upto", max(r["start"] for r in payload["sessions"]))
            self.sessions_sent += len(payload["sessions"])
            return len(payload["sessions"])
        return 0

    def tick(self, now=None):
        now = now or time.time()
        cfg = self.app.cfg
        if not self.url:
            return
        if cfg.get("community_board") and now - self.rsi_at >= RSI_EVERY_S:
            self.rsi_at = now
            try:
                code, d = self._req("/api/v1/rsi")
                self.rsi = d if code == 200 else self.rsi
            except Exception:
                pass
        if cfg.get("share_readings") and now - self.sessions_at >= SESSIONS_EVERY_S:
            self.sessions_at = now
            try:
                self.send_sessions(now)
            except Exception:
                pass
        if cfg.get("community_board") and now - self.board_at >= BOARD_EVERY_S:
            self.board_at = now
            try:
                code, d = self._req("/api/v1/board")
                self.board, self.board_error = (d, None) if code == 200 else (self.board, f"board answered {code}")
            except Exception as e:
                self.board_error = f"couldn't reach the board ({e.__class__.__name__})"
        if not cfg.get("share_readings"):
            self.share_status = "off"
            return
        if now - self.sent_at < SHARE_EVERY_S or now < self.retry_at:
            return
        with self.app.lock:
            snaps = list(self.app.snaps)
        snap = summarise(snaps, now)
        if not snap:
            self.share_status = "waiting for overlay readings"
            return
        last = self.app.last_result or {}
        findings = last.get("findings", []) if now - (last.get("checked_at") or 0) < 1800 else []
        payload = shard_report(snap, self.app.store.install_id(), self.app.build, findings, self.version,
                               self.places.where(snap.get("location")))
        self.last_payload = payload
        try:
            code, d = self._req("/api/v1/report", payload)
        except Exception as e:
            self.share_status = f"couldn't reach the board ({e.__class__.__name__}); trying again in 5 minutes"
            self.sent_at = now
            return
        self.sent_at = now
        if code == 200:
            self.sent += 1
            self.share_status = "sharing"
        elif code == 429:
            self.retry_at = now + SHARE_EVERY_S
            self.share_status = "the board asked to slow down; trying again in 5 minutes"
        else:
            self.share_status = f"the board refused the reading ({d.get('error') or code})"

    def had(self, rule_id):
        """'I had this too' on the board's page for this issue. Sends the issue id and this install's random id."""
        import re
        if not re.fullmatch(r"[a-z0-9-]{2,80}", rule_id or ""):
            raise ValueError("That finding isn't on the community board.")
        try:
            code, d = self._req(f"/api/v1/issue/{rule_id}/had", {"voter": self.app.store.install_id(), "on": True})
        except Exception as e:
            raise ValueError(f"Couldn't reach the community board ({e.__class__.__name__}).")
        if code != 200:
            raise ValueError(d.get("error") or f"The board answered {code}.")
        return "Counted on the community board. Thanks: it shows others it's still happening."

    def run(self, stop):
        while not stop.wait(15):
            try:
                self.tick()
            except Exception as e:
                self.share_status = f"error: {e}"

    def region_view(self, shard_id, region_code):
        """Your region from the board: every shard with its score, yours marked, and the best one."""
        from .logparse import region_name
        if not self.board:
            return None
        name = region_name(region_code) if region_code else None
        group = next((g for g in self.board.get("regions", []) if g.get("name") == name), None)
        shards = group["shards"] if group else []
        mine = next((s for s in shards if s["shard_id"] == shard_id), None)
        best = shards[0] if shards else None
        picks = next((a for a in self.board.get("areas", []) if a.get("region") == name), None)
        return {"region": name, "shards": shards[:8], "mine": mine, "best": best, "areas": picks,
                "reporters": self.board.get("reporters"), "updated": self.board.get("updated"),
                "error": self.board_error}


def review_request(finding, session, redactor, install_id, contracts=()):
    """An unknown error, stripped of identifiers, for the admin review queue."""
    sig = finding.get("fields", {}).get("sig") or finding.get("rule_id") or finding["title"]
    rid = hashlib.sha1(f"{install_id}|{sig}".encode()).hexdigest()[:10]
    examples = redactor.lines([x[:600] for x in finding.get("examples", [])])
    payload = {
        "v": PAYLOAD_VERSION, "kind": "review", "ticket": rid, "install": install_id,
        "created": int(time.time() // 60 * 60), "build": session.get("build"), "version": session.get("version"),
        "region": session.get("region"), "sig": sig, "area": finding.get("area"), "count": finding.get("count"),
        "examples": examples, "contracts": sorted(set(contracts)),
    }
    problems = leaks(repr(payload), redactor.handles)
    # The signature itself is already normalised; anything left is stripped again rather than sent
    if problems:
        payload["examples"] = [redactor.line(x) for x in payload["examples"]]
    payload["checked_clean"] = not leaks(repr(payload["examples"]), redactor.handles)
    return rid, payload


def make_redactor(log_path):
    """A redactor that knows every handle in this log (own, renamed, friends, party members)."""
    from .logparse import records
    try:
        with open(log_path, encoding="utf-8", errors="replace") as f:
            recs = list(records(f))
    except OSError:
        recs = []
    return Redactor.from_lines(recs)
