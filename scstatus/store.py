"""The app's database (data\\status.db, SQLite): overlay readings, past sessions, reviews."""

import json
import secrets
import sqlite3
import statistics as st
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
  ts REAL, shard_id TEXT, server_name TEXT, server_fps REAL, pop_shard INT, pop_srv INT,
  ping_ms REAL, loss_pct REAL, client_fps REAL, build TEXT, data TEXT
);
CREATE INDEX IF NOT EXISTS snapshots_ts ON snapshots (ts);
CREATE INDEX IF NOT EXISTS snapshots_shard ON snapshots (shard_id);
CREATE TABLE IF NOT EXISTS sessions (
  name TEXT PRIMARY KEY, size INT, start REAL, end REAL, build TEXT, version TEXT, shard_id TEXT, region TEXT,
  minutes REAL, load_s INT, joins INT, bad_disconnects INT, errors INT, clean_exit INT, data TEXT
);
CREATE TABLE IF NOT EXISTS reviews (
  id TEXT PRIMARY KEY, created REAL, sig TEXT, status TEXT, data TEXT
);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""


class Store:
    def __init__(self, path):
        self.path = str(path)
        self.lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.lock:
            self.db.executescript(SCHEMA)
            self.db.commit()

    # -- meta
    def meta(self, k, default=None):
        with self.lock:
            r = self.db.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r["v"] if r else default

    def set_meta(self, k, v):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (k, str(v)))
            self.db.commit()

    def install_id(self):
        """A random id for this install. Not linked to your account or handle."""
        v = self.meta("install_id")
        if not v:
            v = secrets.token_hex(8)
            self.set_meta("install_id", v)
        return v

    # -- overlay readings
    def add_snapshot(self, s, build=None):
        with self.lock:
            self.db.execute("INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                            (s["ts"], s.get("shard_id"), s.get("server_name"), s.get("server_fps"),
                             s.get("pop_shard"), s.get("pop_srv"), s.get("ping_ms"), s.get("loss_pct"),
                             s.get("client_fps"), build, json.dumps(s)))
            self.db.commit()

    def snapshots(self, since=0, shard_id=None, limit=5000):
        q = "SELECT data FROM snapshots WHERE ts >= ?"
        args = [since]
        if shard_id:
            q += " AND shard_id = ?"
            args.append(shard_id)
        q += " ORDER BY ts DESC LIMIT ?"
        args.append(limit)
        with self.lock:
            rows = self.db.execute(q, args).fetchall()
        return [json.loads(r["data"]) for r in reversed(rows)]

    def shard_history(self, build=None):
        """Per shard: readings, median server fps and population, when you were on it."""
        q = "SELECT shard_id, server_fps, pop_shard, pop_srv, ping_ms, ts, build FROM snapshots WHERE shard_id IS NOT NULL"
        args = []
        if build:
            q += " AND build = ?"
            args.append(build)
        with self.lock:
            rows = self.db.execute(q, args).fetchall()
        by = {}
        for r in rows:
            by.setdefault(r["shard_id"], []).append(r)
        out = []
        for sid, rs in by.items():
            f = [r["server_fps"] for r in rs if r["server_fps"] is not None]
            p = [r["pop_shard"] for r in rs if r["pop_shard"] is not None]
            pg = [r["ping_ms"] for r in rs if r["ping_ms"] is not None]
            out.append({"shard_id": sid, "readings": len(rs), "first": min(r["ts"] for r in rs),
                        "last": max(r["ts"] for r in rs),
                        "server_fps": round(st.median(f), 1) if f else None,
                        "server_fps_low": round(min(f), 1) if f else None,
                        "pop_shard": round(st.median(p)) if p else None,
                        "ping_ms": round(st.median(pg)) if pg else None})
        out.sort(key=lambda x: -x["last"])
        return out

    def hourly(self):
        """Median server fps by local hour of day, across all your readings."""
        with self.lock:
            rows = self.db.execute("SELECT ts, server_fps FROM snapshots WHERE server_fps IS NOT NULL").fetchall()
        by = {}
        for r in rows:
            h = time.localtime(r["ts"]).tm_hour
            by.setdefault(h, []).append(r["server_fps"])
        return [{"hour": h, "server_fps": round(st.median(v), 1), "readings": len(v)} for h, v in sorted(by.items())]

    def build_fps(self, build):
        with self.lock:
            rows = self.db.execute("SELECT server_fps FROM snapshots WHERE build=? AND server_fps IS NOT NULL",
                                   (build,)).fetchall()
        return [r["server_fps"] for r in rows]

    # -- sessions (one per Game.log)
    def session_known(self, name, size):
        with self.lock:
            r = self.db.execute("SELECT size FROM sessions WHERE name=?", (name,)).fetchone()
        return r is not None and r["size"] == size

    def save_session(self, summary, size):
        s = summary
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                            (s["name"], size, s["start"], s["end"], s["build"], s["version"], s["shard_id"],
                             s["region"], s["minutes"], s["load_s"], s["joins"], s["bad_disconnects"],
                             s["errors"], int(s["clean_exit"]), json.dumps(s, default=str)))
            self.db.commit()

    def sessions(self, limit=200):
        with self.lock:
            rows = self.db.execute("SELECT * FROM sessions ORDER BY start DESC LIMIT ?", (limit,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            data = json.loads(d.pop("data") or "{}")
            d["contracts"] = [{"name": c["name"], "result": c["result"]} for c in data.get("contracts", [])]
            d["disconnect_causes"] = [x["cause"] for x in data.get("disconnects", [])]
            d["hardware"] = data.get("hardware", {})
            out.append(d)
        return out

    # -- review queue (kept locally until the community service exists)
    def add_review(self, rid, sig, data):
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO reviews VALUES (?,?,?,?,?)",
                            (rid, time.time(), sig, "saved", json.dumps(data)))
            self.db.commit()

    def reviews(self):
        with self.lock:
            rows = self.db.execute("SELECT * FROM reviews ORDER BY created DESC").fetchall()
        return [dict(r, data=json.loads(r["data"])) for r in rows]
