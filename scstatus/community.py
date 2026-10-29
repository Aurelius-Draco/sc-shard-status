"""What would be shared with the community service (v2), built now so it can be
checked before any network code exists.

v1 never sends anything. These functions build the exact payloads and the app
shows them to you (and saves review submissions locally), so you can see that
nothing identifying is in them.

Rules: no handle, no other players' names, no account or entity numbers, no
session id, no IP address, no file paths. Times are rounded to the minute.
"""

import hashlib
import time

from .redact import Redactor, leaks

PAYLOAD_VERSION = 1


def _r(v, step):
    return None if v is None else round(round(v / step) * step, 3)


def shard_report(snap, install_id, build, findings=()):
    """One health reading for the live shard status board."""
    return {
        "v": PAYLOAD_VERSION, "kind": "shard", "install": install_id, "build": build,
        "ts": int(snap["ts"] // 60 * 60),
        "shard_id": snap.get("shard_id"),
        "server": (snap.get("server_name") or "").rsplit("-", 1)[-1] or None,   # e.g. "game-07" -> "07"
        "server_fps": snap.get("server_fps"), "server_fps_min": snap.get("server_fps_min"),
        "server_fps_max": snap.get("server_fps_max"), "hitches": snap.get("hitches"),
        "restarts": snap.get("restarts"), "pop_shard": snap.get("pop_shard"), "pop_srv": snap.get("pop_srv"),
        "ping_ms": _r(snap.get("ping_ms"), 10), "loss_pct": snap.get("loss_pct"),
        "issues": sorted({f["rule_id"] for f in findings if f.get("rule_id")}),
    }


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
