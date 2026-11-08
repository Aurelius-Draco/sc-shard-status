"""What you've done in game, from your own Game.logs on this PC: blueprints earned and a report for each session.

Nothing here leaves the PC. Blueprints come from "Received Blueprint: <name>" notifications; a wipe isn't logged,
and blueprints earned on another PC or before the logs were kept can't be seen, so the page says the fabricator in
game is the final word.
"""

import datetime as dt
import json
import re
import time

GROUPS = ["Armour", "FPS weapons", "Magazines and batteries", "Ship weapons", "Other"]

# Checked against the 34 blueprints in Ray's logs (Oct and Nov 2026). Order matters: a "Pistol Magazine" is a
# magazine, a "Pulse Laser Pistol" is an FPS weapon, a "Laser Cannon" is a ship weapon.
_GROUP_RULES = [
    (2, r"\b(magazine|battery|cap\)|ammo|canister|cell)\b"),
    (0, r"\b(helmet|core|arms|legs|backpack|undersuit|gloves|shoes|boots|armou?r|torso|jacket|pants|hat)\b"),
    (1, r"\b(pistol|rifle|smg|shotgun|sniper|lmg|launcher|railgun|grenade|knife|multi-tool gun)\b"),
    (3, r"\b(repeater|cannon|gatling|scattergun|mass driver|missile|torpedo|turret|distortion|ballistic)\b"),
]


def group_of(name):
    n = (name or "").lower()
    for g, rx in _GROUP_RULES:
        if re.search(rx, n):
            return g
    return 4


def _bp_id(name):
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def _key(name):
    return re.sub(r"\s+", " ", (name or "").strip()).lower()


# --------------------------------------------------------------------------
# Blueprints
# --------------------------------------------------------------------------

def blueprints(summaries, live=None):
    """Every blueprint received, first time first: [{id, name, group, ts, contract, times, fresh}].
    summaries: past sessions' summaries (any order); live: the current Session, whose blueprints are 'fresh'."""
    seen = {}
    rows = []
    for s in summaries:
        for b in s.get("blueprints") or []:
            rows.append((b, False))
    if live is not None:
        for b in live.blueprints:
            rows.append((b, True))
    for b, fresh in sorted(rows, key=lambda r: r[0].get("ts") or 0):
        k = _key(b["name"])
        if k in seen:
            seen[k]["times"] += 1
            seen[k]["fresh"] = seen[k]["fresh"] or fresh
            continue
        seen[k] = {"id": _bp_id(b["name"]), "name": b["name"], "group": group_of(b["name"]), "ts": b.get("ts"),
                   "contract": b.get("contract"), "times": 1, "fresh": fresh}
    return sorted(seen.values(), key=lambda b: -(b["ts"] or 0))


class WantList:
    """Blueprints the player wants, kept in the app's database. A wanted one that's received comes off the list."""

    MAX = 200

    def __init__(self, store):
        self.store = store

    def get(self):
        try:
            v = json.loads(self.store.meta("bp_want") or "[]")
            return [str(x) for x in v if str(x).strip()]
        except ValueError:
            return []

    def _set(self, names):
        self.store.set_meta("bp_want", json.dumps(names[: self.MAX]))

    def add(self, name, earned=()):
        name = re.sub(r"\s+", " ", str(name or "")).strip()[:60]
        if not name:
            raise ValueError("Type the name of a blueprint you want.")
        if _key(name) in {_key(e) for e in earned}:
            raise ValueError(f"You already have {name}.")
        cur = self.get()
        if _key(name) not in {_key(x) for x in cur}:
            cur.append(name)
            self._set(cur)
        return cur

    def remove(self, name):
        cur = [x for x in self.get() if _key(x) != _key(name)]
        self._set(cur)
        return cur

    def received(self, names):
        """Names just received; returns the ones that were wanted (and takes them off the list)."""
        cur = self.get()
        got = {_key(n) for n in names}
        hit = [x for x in cur if _key(x) in got]
        if hit:
            self._set([x for x in cur if _key(x) not in got])
        return hit


# --------------------------------------------------------------------------
# Session reports
# --------------------------------------------------------------------------

REASONS = {"Combat": "Combat", "SelfDestruct": "Self destruct", "Collision": "Collision", "Crash": "Collision"}


def reason_word(r):
    if not r:
        return "Destroyed"
    return REASONS.get(r, re.sub(r"(?<=[a-z])(?=[A-Z])", " ", r).capitalize())


def session_id(summary):
    """A session's id stays the same when the game moves Game.log into logbackups: its start time."""
    return str(int(summary.get("start") or 0))


def _local(ts):
    return dt.datetime.fromtimestamp(ts) if ts else None


def _clock(d):
    h = d.hour % 12 or 12
    return f"{h}:{d.minute:02d} {'am' if d.hour < 12 else 'pm'}"


def _dur(minutes):
    m = int(round(minutes or 0))
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60} min"


def card(summary, snaps=(), notes=None, marks=(), problems=None, live=False, now=None):
    """One session as the History cards and the report show it."""
    from . import score
    from .overlay import node_of
    from .timeline import shard_label, ship_name
    now = now or time.time()
    start, end = summary.get("start"), summary.get("end")
    d0, d1 = _local(start), _local(end)
    sc = score.session_score(list(snaps))
    word, h = score.band(sc) if sc is not None else ("No score", "none")
    contracts = [c for c in summary.get("contracts") or [] if c.get("accepted") or c.get("result") != "active"]
    acc = [c for c in contracts if c.get("accepted")]
    done = [c for c in contracts if c.get("result") == "complete"]
    failed = [c for c in contracts if c.get("result") == "failed"]
    servers = list(dict.fromkeys(s.get("server_name") for s in snaps if s.get("server_name")))
    shards = []
    for sid in summary.get("shards") or ([summary["shard_id"]] if summary.get("shard_id") else []):
        on = list(dict.fromkeys(node_of(s.get("server_name")) or s.get("server_name") for s in snaps
                                if s.get("shard_id") == sid and s.get("server_name")))
        shards.append({"shard": shard_label(sid), "servers": on})
    n = notes or {}
    bps = summary.get("blueprints") or []
    return {
        "id": session_id(summary), "live": live, "start": start, "end": None if live else end,
        "day": f"{d0:%a} {d0.day} {d0:%b}" if d0 else "",
        "date": f"{d0:%Y-%m-%d}" if d0 else "",
        "time": (f"Started {_clock(d0)}" if live else f"{_clock(d0)} to {_clock(d1)}") if d0 and d1 else "",
        "dur": "" if live else _dur(summary.get("minutes")),
        "minutes": round((now - start) / 60) if live and start else summary.get("minutes"),
        "score": sc, "health": h, "word": word, "readings": len(snaps), "overlay": sc is not None,
        "accepted": len(acc) or len(contracts), "completed": len(done), "failed": len(failed),
        "contracts": [{"name": c.get("title") or c.get("name"), "result": {"complete": "completed", "dropped": "abandoned"}
                       .get(c.get("result"), c.get("result")), "rep": c.get("rep")} for c in contracts],
        "blueprints": [{"name": b["name"], "id": _bp_id(b["name"]), "group": group_of(b["name"])} for b in bps],
        "journal": [j["text"] for j in summary.get("journal") or []],
        "problems": problems if problems is not None else summary.get("problems") or [],
        "lost": [{"ship": ship_name(x.get("ship")), "reason": reason_word(x.get("reason"))}
                 for x in summary.get("ships_lost") or []],
        "moments": len(marks), "shards": shards, "servers": servers,
        "rating": n.get("rating"), "note": n.get("note") or "",
        "auec_start": n.get("auec_start"), "auec_end": n.get("auec_end"),
        "version": summary.get("version"), "branch": summary.get("branch"),
    }


def problems_of(path, library, session, snaps=()):
    """The problems the library sees in one whole log (and its overlay readings), for the session report."""
    from .diagnose import diagnose
    if session is None or not session.start:
        return []
    try:
        r = diagnose(path, library, snapshots=list(snaps), lookback_min=10 ** 7, now=(session.end or time.time()) + 1,
                     session=session)
    except Exception:
        return []
    out = []
    for f in r["findings"]:
        if f.get("kind", "problem") != "problem":
            continue
        out.append({"ts": f.get("first_ts"), "title": f.get("title"), "rule_id": f.get("rule_id"),
                    "severity": f.get("severity")})
    out.sort(key=lambda x: x["ts"] or 0)
    return out[:30]


def time_label(ts):
    d = _local(ts)
    return _clock(d) if d else ""
