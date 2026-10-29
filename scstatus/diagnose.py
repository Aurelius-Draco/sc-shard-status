"""What's gone wrong? Looks back over the log (and overlay readings) and explains it.

Three kinds of finding:
- known problems from the library, with plain-English explanations and fixes
- things worked out by joining facts together (a contract that wants an item the
  cargo system just complained about, a disconnect, a crashed last session)
- unknown error lines, grouped, so they can be sent for review
"""

import datetime as dt
import re
import time
from collections import OrderedDict
from pathlib import Path

from .issues import SEVERITY_ORDER
from .logparse import (LINE, NORMAL_CAUSES, TEAMS, Session, _joined_lines, parse_line, parse_ts,
                       region_name, signature)

MAX_EXAMPLES = 3


def read_window(path, since, until=None):
    """Raw lines (continuations joined) from path with since <= time <= until."""
    out = []
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for raw in _joined_lines(f):
                m = LINE.match(raw)
                if not m:
                    continue
                ts = parse_ts(m.group(1))
                if ts < since:
                    continue
                if until and ts > until:
                    break
                out.append((ts, raw))
    except OSError:
        pass
    return out


def _finding(**kw):
    base = {"severity": "medium", "kind": "problem", "area": "", "title": "", "explain": "", "fixes": [],
            "count": 1, "first_ts": None, "last_ts": None, "examples": [], "rule_id": None,
            "ic_title": None, "fields": {}, "links": [], "rank": 1}
    base.update(kw)
    return base


def diagnose(log_path, library, names=None, snapshots=None, lookback_min=30, now=None, backups_dir=None,
             session=None):
    now = now or time.time()
    since = now - lookback_min * 60
    lines = read_window(log_path, since)
    if session is None:
        session = Session(Path(log_path).name)
        try:
            with open(log_path, encoding="utf-8", errors="replace") as f:
                for raw in _joined_lines(f):
                    session.add(parse_line(raw))
        except OSError:
            pass

    hits = OrderedDict()        # (rule id, key fields) -> finding
    unknown = OrderedDict()     # sig -> finding
    noise = 0
    for ts, raw in lines:
        m = LINE.match(raw)
        _, level, tag, msg = m.groups()
        msg = TEAMS.sub("", msg or "").rstrip()
        tag = tag or ""
        rule, fields = library.match(level, tag, msg) if (level or tag) else (None, None)
        if rule is not None:
            if rule.kind == "noise":
                noise += 1
                continue
            if "item" in fields and names is not None:
                fields["item_name"] = names.display(fields["item"])
            key = (rule.id, tuple(sorted((k, v) for k, v in fields.items() if k in ("item", "cause", "item_name"))))
            f = hits.get(key)
            if f is None:
                f = hits[key] = _finding(
                    severity=rule.severity, kind=rule.kind, area=rule.area, rule_id=rule.id,
                    title=rule.text("title", fields) or rule.id, explain=rule.text("explain", fields) or "",
                    fixes=rule.text("fixes", fields) or [], ic_title=rule.text("ic_title", fields),
                    links=rule.d.get("links", []), fields=dict(fields), first_ts=ts, count=0)
            f["count"] += 1
            f["last_ts"] = ts
            if len(f["examples"]) < MAX_EXAMPLES:
                f["examples"].append(raw)
        elif level in ("Error", "Warning"):
            sig = signature(tag, msg)
            f = unknown.get(sig)
            if f is None:
                f = unknown[sig] = _finding(severity="unknown", kind="unknown", area=tag,
                                            title=f"Unrecognised {level.lower()}: {tag or 'no tag'}",
                                            explain="Not in the known-issues library yet.",
                                            first_ts=ts, count=0, fields={"sig": sig})
            f["count"] += 1
            f["last_ts"] = ts
            if len(f["examples"]) < MAX_EXAMPLES:
                f["examples"].append(raw)

    findings = [f for f in hits.values() if f["kind"] == "problem"]
    infos = [f for f in hits.values() if f["kind"] == "info"]
    findings += _disconnects(session, since, library)
    findings += _contracts(session, since, findings, names)
    findings += _overlay(snapshots or [], since)
    if backups_dir and session.start and session.start >= since - 600:
        crash = _last_session_crash(backups_dir, session.start)
        if crash:
            findings.append(crash)

    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 3), f["rank"], -(f["count"] or 0)))
    unk = sorted(unknown.values(), key=lambda f: -f["count"])
    sid = session.shard_id
    return {
        "generated": now, "since": since, "lookback_min": lookback_min,
        "lines_checked": len(lines), "noise_lines": noise,
        "findings": findings, "info": infos, "unknown": unk,
        "session": {"build": session.build, "version": session.version, "shard_id": sid,
                    "region": region_name(session.joins[-1]["region"]) if session.joins else None,
                    "started": session.start, "clean_exit": session.clean_exit},
        "headline": headline(findings, unk),
    }


def headline(findings, unknown):
    high = [f for f in findings if f["severity"] == "high"]
    if high:
        return f"{len(high)} serious problem{'s' if len(high) != 1 else ''} found. Most likely cause: {high[0]['title']}."
    if findings:
        return f"{len(findings)} minor problem{'s' if len(findings) != 1 else ''} found, nothing serious."
    if unknown:
        return "No known problems. Some unrecognised errors were logged; they may be harmless."
    return "Nothing wrong found in the log for this period."


def _disconnects(session, since, library):
    out = []
    for d in session.disconnects:
        if d["ts"] < since or d["cause"] in NORMAL_CAUSES:
            continue
        if library.get(f"disconnect-{d['cause']}"):
            continue        # the library already explained this one from the raw line
        out.append(_finding(severity="high", area="Connection", title=f"Disconnected from the server (code {d['cause']})",
                            explain=f"The game dropped the connection: \"{d['reason']}\". Codes in the 30000s "
                                    "are the infamous 30k disconnects, usually a server crash or a network drop.",
                            fixes=["Wait a minute and log back in; you'll usually land on a new server.",
                                   "If it keeps happening on the same shard, pick another region in the launcher."],
                            ic_title=f"Disconnected with error {d['cause']}: {d['reason']}",
                            first_ts=d["ts"], last_ts=d["ts"], fields={"cause": d["cause"]}))
    return out


def _words(s):
    return {w for w in re.findall(r"[a-z]{3,}", (s or "").lower())} - {"the", "and", "need", "with", "for"}


def _contracts(session, since, findings, names):
    out = []
    by_name = {}
    for c in session.contracts.values():
        by_name.setdefault(c["name"], []).append(c)
    item_findings = [f for f in findings if f["fields"].get("item")]
    for name, cs in by_name.items():
        live = [c for c in cs if (c["accepted"] or 0) >= since or c["result"] == "active"]
        if not live:
            continue
        stuck = [c for c in live if c["result"] == "active" and c["objectives"]
                 and not any(o["state"] == "complete" for o in c["objectives"].values())]
        if not stuck:
            continue
        objectives = [o["text"] for o in stuck[-1]["objectives"].values()]
        linked = []
        for f in item_findings:
            disp = f["fields"].get("item_name") or f["fields"]["item"]
            if any(disp.lower() in o.lower() or len(_words(disp) & _words(o)) >= 2 for o in objectives):
                linked.append((disp, f))
        if linked:
            items = sorted({d for d, _ in linked})
            out.append(_finding(
                severity="high", area="Contracts", rank=0,
                title=f"\"{name}\" can't complete: the game is mishandling {_and(items)}",
                explain=(f"The contract wants {_and(items)}, and the game logged a problem with exactly "
                         f"{'that item' if len(items) == 1 else 'those items'} ({linked[0][1]['title'].lower()}). "
                         "That's why the objective isn't counting. The client log can't see the server's own "
                         "mission check, so this is a strong lead rather than proof."),
                fixes=["Stop sending more of these items for now; they're likely being lost.",
                       "Abandon and re-accept the contract only after a patch or a server hop; re-accepting on the "
                       "same server usually hits the same problem.",
                       "Report it (the Issue Council draft below has the log lines), and check whether someone has "
                       "already reported it so you can add your confirmation."],
                ic_title=f"{name}: delivered {_and(items)} never count toward the objective",
                first_ts=stuck[0]["accepted"], last_ts=max(f["last_ts"] or 0 for _, f in linked), count=len(cs),
                examples=[x for _, f in linked for x in f["examples"][:2]][:MAX_EXAMPLES * 2],
                fields={"contract": name, "items": items, "times_accepted": len(cs)}))
        elif len(cs) >= 2:
            out.append(_finding(
                severity="medium", area="Contracts",
                title=f"\"{name}\" taken {len(cs)} times without completing",
                explain="You've accepted this contract more than once and no objective has completed. "
                        "That usually means something on the server isn't registering progress.",
                fixes=["Try it on a different server (server hop) before spending more items or time.",
                       "Check the Known issues tab and the Issue Council for this contract."],
                ic_title=f"{name}: objectives never progress",
                first_ts=cs[0]["accepted"], last_ts=cs[-1]["accepted"], count=len(cs), fields={"contract": name}))
    return out


def _and(items):
    items = list(items)
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def _overlay(snaps, since):
    out = []
    recent = [s for s in snaps if s.get("ok") and s["ts"] >= since]
    if not recent:
        return out
    low = [s for s in recent if (s.get("server_fps") or 99) < 10]
    if low and low[-1]["ts"] - low[0]["ts"] >= 120:
        worst = min(s["server_fps"] for s in low)
        out.append(_finding(severity="high", area="Server", title="Server running very slowly",
                            explain=f"Server fps was under 10 for {round((low[-1]['ts'] - low[0]['ts']) / 60)} minutes "
                                    f"(lowest {worst:g}). At this speed elevators stall, AI freezes, kiosks and "
                                    "missions don't respond, and ships rubber-band.",
                            fixes=["Server hop: exit to menu and rejoin, or pick a different region.",
                                   "Avoid starting missions or deliveries until it recovers."],
                            first_ts=low[0]["ts"], last_ts=low[-1]["ts"], count=len(low)))
    restarts = [s for s in recent if s.get("restarts")]
    if restarts:
        out.append(_finding(severity="high", area="Server", title="Your server node restarted",
                            explain="The overlay shows the server node restarted while you were on it. Things nearby "
                                    "can reset or vanish, and contracts can break.",
                            fixes=["Check your ship and cargo are still where you left them.",
                                   "If a contract stopped updating, a server hop is the usual fix."],
                            first_ts=restarts[0]["ts"], last_ts=restarts[-1]["ts"], count=len(restarts)))
    lossy = [s for s in recent if (s.get("loss_pct") or 0) >= 2]
    if len(lossy) >= 3:
        out.append(_finding(severity="medium", area="Connection", title="Packet loss",
                            explain=f"Packet loss reached {max(s['loss_pct'] for s in lossy):g}%. That causes "
                                    "rubber-banding and actions that don't go through.",
                            fixes=["Check your own connection first: Wi-Fi, other downloads or streams.",
                                   "If your connection is fine, the route to this region may be the problem."],
                            first_ts=lossy[0]["ts"], last_ts=lossy[-1]["ts"], count=len(lossy)))
    return out


def _last_session_crash(backups_dir, current_start):
    """Did the session before this one end without the game shutting down normally?"""
    try:
        logs = sorted(Path(backups_dir).glob("*.log"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return None
    if not logs:
        return None
    last = logs[-1]
    if current_start - last.stat().st_mtime > 3 * 3600:
        return None
    try:
        with open(last, "rb") as f:
            f.seek(max(0, last.stat().st_size - 20000))
            tail = f.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    if any(k in tail for k in ("CCIGBroker::FastShutdown", "Shutting down all force feedback")):
        return None
    when = dt.datetime.fromtimestamp(last.stat().st_mtime).strftime("%H:%M")
    return _finding(severity="high", area="Game", title="Your last session ended without a normal shutdown",
                    explain=f"The previous log stops at {when} without the lines the game writes when it closes "
                            "properly. That points to a crash, a freeze you had to kill, or a power or PC problem.",
                    fixes=["If the game crashed, check for a crash report in the StarCitizen\\LIVE\\Crashes folder.",
                           "Repeated crashes: verify the game files in the RSI launcher.",
                           "Note what you were doing when it happened for the Issue Council report."],
                    ic_title="Client crash (game closed without normal shutdown)",
                    fields={"log": last.name}, first_ts=last.stat().st_mtime, last_ts=last.stat().st_mtime)
