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
    # Earlier sessions inside the window live in logbackups (the game starts a new Game.log every launch)
    earlier = []
    if backups_dir:
        try:
            earlier = sorted((p for p in Path(backups_dir).glob("*.log") if p.stat().st_mtime >= since),
                             key=lambda p: p.stat().st_mtime)
        except OSError:
            earlier = []
    lines = []
    for p in earlier:
        lines += read_window(p, since)
    lines += read_window(log_path, since)
    if session is None:
        session = _parse(log_path)
    sessions = [(p, _parse(p)) for p in earlier] + [(Path(log_path), session)]

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
    item_findings = list(findings)
    for p, sess in sessions:
        findings += _disconnects(sess, since, library)
        findings += _contracts(sess, since, item_findings, names, now)
    if session.crash:
        findings += crash_findings(log_path, library, session)
    for p, sess in sessions[:-1]:
        findings += _ended_badly(p, sess, library)
    findings += _overlay(snapshots or [], since)
    if backups_dir and session.start and session.start >= since - 600:
        prev = _last_session_crash(backups_dir, session.start, library)
        findings += [f for f in prev if f["fields"].get("log") not in {p.name for p in earlier}]

    findings.sort(key=lambda f: (SEVERITY_ORDER.get(f["severity"], 3), f["rank"], -(f["count"] or 0)))
    unk = sorted(unknown.values(), key=lambda f: -f["count"])
    sid = session.shard_id
    return {
        "generated": now, "since": since, "lookback_min": lookback_min,
        "lines_checked": len(lines), "noise_lines": noise, "logs": [p.name for p, _ in sessions],
        "findings": findings, "info": infos, "unknown": unk,
        "session": {"build": session.build, "version": session.version, "branch": getattr(session, "branch", None), "shard_id": sid,
                    "region": region_name(session.joins[-1]["region"]) if session.joins else None,
                    "started": session.start, "clean_exit": session.clean_exit},
        "headline": headline(findings, unk),
    }


def _parse(path):
    sess = Session(Path(path).name)
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for raw in _joined_lines(f):
                sess.add(parse_line(raw))
    except OSError:
        pass
    return sess


def _ended_badly(path, sess, library):
    """An earlier session in the window that crashed, or stopped without a normal shutdown."""
    when = dt.datetime.fromtimestamp(sess.end).strftime("%H:%M") if sess.end else "?"
    if sess.crash:
        out = crash_findings(path, library, sess)
        for f in out:
            f["title"] = f"Session ending {when}: " + f["title"][0].lower() + f["title"][1:]
            f["fields"]["log"] = Path(path).name
        return out
    if sess.clean_exit:
        return []
    return [_finding(severity="high", area="Game", title=f"The session ending {when} stopped without a normal shutdown",
                     explain="That log stops without the lines the game writes when it closes properly, and without "
                             "a crash report. That points to a freeze you had to kill, or a power or PC problem.",
                     fixes=["Repeated freezes: verify the game files in the RSI launcher.",
                            "Note what you were doing when it happened for the Issue Council report."],
                     ic_title="Client froze (game closed without normal shutdown)",
                     fields={"log": Path(path).name}, first_ts=sess.end, last_ts=sess.end)]


def headline(findings, unknown):
    high = [f for f in findings if f["severity"] == "high"]
    if high:
        return f"{len(high)} serious problem{'s' if len(high) != 1 else ''} found. Top of the list: {high[0]['title']}."
    if findings:
        return f"{len(findings)} problem{'s' if len(findings) != 1 else ''} found, none of them serious."
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


def _contracts(session, since, findings, names, now=None):
    """Contracts that aren't progressing, joined with freight elevator cycles and item errors."""
    now = now or time.time()
    out = []
    by_name = {}
    for c in session.contracts.values():
        by_name.setdefault(c["name"], []).append(c)
    item_findings = [f for f in findings if f["fields"].get("item")]
    deliveries = [c for c in session.contracts.values()
                  if any(_is_delivery(k, o["text"]) for k, o in c["objectives"].items())]

    def only_delivery_at(c, t):
        """True when c was the only delivery contract open at time t, so an elevator trip then was for it."""
        return not any(d is not c and (d["accepted"] or 0) <= t <= (d["ended"] or now) for d in deliveries)

    for name, cs in by_name.items():
        if any(c["result"] == "complete" or c["progress"] for c in cs):
            continue        # the same contract worked this session, so it isn't broken
        delivery = any(_is_delivery(k, o["text"]) for c in cs for k, o in c["objectives"].items())
        # Elevator trips inside the look-back window, while this contract was the only delivery contract open
        per = {id(c): [t for t in session.freight_cycles if since <= t <= now
                       and (c["accepted"] or 0) <= t <= (c["ended"] or now) and only_delivery_at(c, t)]
               if delivery else [] for c in cs}
        tries = [c for c in cs if c["result"] in ("active", "abandoned", "dropped", "failed")
                 and ((c["accepted"] or 0) >= since or per[id(c)])]
        if not tries:
            continue
        objectives = list(dict.fromkeys(o["text"] for c in tries for o in c["objectives"].values()))
        cycles = sorted({t for c in tries for t in per[id(c)]})
        tries_with_cycles = sum(1 for c in tries if per[id(c)])
        if not cycles and len(tries) < 2:
            continue
        linked = []
        for f in item_findings:
            disp = f["fields"].get("item_name") or f["fields"]["item"]
            if any(disp.lower() in o.lower() or len(_words(disp) & _words(o)) >= 2 for o in objectives):
                linked.append((disp, f))
        items = sorted({d for d, _ in linked})
        dropped = [c for c in tries if c["result"] == "dropped"]
        n, k = len(tries), len(cycles)
        strong = tries_with_cycles >= 2
        bits, ic = [], []
        if strong:
            bits.append(f"You took this contract {n} times. On {tries_with_cycles} of those attempts the freight elevator "
                        "went down while it was your only delivery contract open, and the server never registered any "
                        "progress on the objective. The same thing happening across attempts points at the contract or "
                        "its items rather than anything you did.")
            ic.append(f"I accepted \"{name}\" {n} times. On {tries_with_cycles} attempts I sent the required items down the "
                      "freight elevator; the elevator cycled normally but the objective never progressed (Game.log shows "
                      "no objective update for the mission).")
        elif cycles:
            bits.append(f"The freight elevator went down {k} time{'s' if k != 1 else ''} while this was your only delivery "
                        "contract open, and the objective didn't move. If those trips carried this contract's items, the "
                        "delivery didn't register. If you were moving other cargo, ignore this.")
            ic.append(f"I sent items for \"{name}\" down the freight elevator and the objective did not progress "
                      "(Game.log shows no objective update for the mission).")
        else:
            bits.append(f"You've taken this contract {n} times and no objective has moved.")
            ic.append(f"I accepted \"{name}\" {n} times and no objective ever progressed.")
        if items:
            what = f"{linked[0][1]['area'].lower() or 'item'} error{'s' if len(items) > 1 else ''}"
            bits.append(f"The game also logged {what} for {_and(items)}. Those turn up on deliveries that do count "
                        "too, so on their own they aren't the cause.")
            ic.append(f"Game.log also shows {what} for {_and(items)}, though the same messages appear on "
                      "deliveries that do count.")
        if dropped:
            bits.append("Leaving the server dropped the contract at least once, so it had to be taken again.")
        out.append(_finding(
            severity="high" if strong else "medium", area="Contracts", rank=0,
            title=(f"\"{name}\": deliveries never counted" if strong
                   else f"\"{name}\": a delivery may not have counted" if cycles
                   else f"\"{name}\" taken {n} times without progress"),
            explain=" ".join(bits), ic_summary=" ".join(ic),
            fixes=["Hold off sending more items for this contract; they don't seem to be counting.",
                   "Take your items back out of the elevator before you leave the server. Items left in it stay on "
                   "that shard, and the kiosk on a new one can't find them.",
                   "Check the Issue Council for this contract and add your confirmation, or report it with the draft below."],
            ic_title=(f"{name}: delivered items never count toward the objective" if strong
                      else f"{name}: delivery through the freight elevator didn't count" if cycles
                      else f"{name}: objectives never progress"),
            first_ts=min((c["accepted"] or now) for c in tries), last_ts=max(cycles) if cycles else None,
            count=n,
            examples=[x for _, f in linked for x in f["examples"][:2]][:4],
            fields={"contract": name, "items": items, "objectives": objectives, "times_accepted": n,
                    "elevator_cycles": k, "dropped": len(dropped)}))
    return out


DELIVERY_TEXT = re.compile(r"^(Need \d+/\d+ of|Deliver|Drop ?off|Hand in|Turn in)", re.I)


def _is_delivery(objective_id, text):
    """Objectives handed in through a freight elevator or drop-off."""
    return str(objective_id).startswith("dropoff") or bool(DELIVERY_TEXT.match(text or ""))


def _deliveries_that_counted(session):
    """Freight elevator cycles followed within 10 seconds by an objective update for some contract."""
    ups = [e["ts"] for e in session.events if e["kind"] in ("objective_state", "objective_complete")]
    return [t for t in session.freight_cycles if any(0 <= u - t <= 10 for u in ups)]


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
    # Restarts and packet loss only count once a value repeats, per server (a lone misread such as a restart
    # counter of 435 is thrown away, the same rules as the live score; see clean.py)
    from . import clean
    rises = []
    by_server = {}
    for x in recent:
        by_server.setdefault(x.get("server_name") or "?", []).append(x)
    for rows in by_server.values():
        vals = [x.get("restarts") for x in rows]
        if clean.restart_rises(vals):
            settled = clean.settle(vals, 5)
            prev = None
            for x, v in zip(rows, settled):
                if v is not None and prev is not None and v > prev:
                    rises.append(x)
                prev = v if v is not None else prev
    rises.sort(key=lambda x: x["ts"])
    if rises:
        out.append(_finding(severity="high", area="Server", title="Your server node restarted",
                            explain="The overlay's restart count went up while you were on this server node. Things "
                                    "nearby can reset or vanish, and contracts can break.",
                            fixes=["Check your ship and cargo are still where you left them.",
                                   "If a contract stopped updating, a server hop is the usual fix."],
                            first_ts=rises[0]["ts"], last_ts=rises[-1]["ts"], count=len(rises)))
    settled_loss = clean.settle([s.get("loss_pct") for s in recent], 2)
    lossy = [s for s, v in zip(recent, settled_loss) if (v or 0) >= 2]
    if len(lossy) >= 3:
        out.append(_finding(severity="medium", area="Connection", title="Packet loss",
                            explain=f"Packet loss reached {max(v for v in settled_loss if v is not None):g}%. That causes "
                                    "rubber-banding and actions that don't go through.",
                            fixes=["Check your own connection first: Wi-Fi, other downloads or streams.",
                                   "If your connection is fine, the route to this region may be the problem."],
                            first_ts=lossy[0]["ts"], last_ts=lossy[-1]["ts"], count=len(lossy)))
    return out


def crash_findings(path, library, session=None):
    """Explain a crash from the block the game's crash handler writes at the end of the log."""
    try:
        with open(path, "rb") as f:
            size = Path(path).stat().st_size
            f.seek(max(0, size - 60000))
            tail = f.read().decode("utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out, seen = [], set()
    when = session.end if session else None
    for line in tail:
        if LINE.match(line):
            continue
        rule, fields = library.match(None, "", line.strip())
        if rule is None or rule.kind == "noise" or rule.id in seen:
            continue
        seen.add(rule.id)
        out.append(_finding(severity=rule.severity, kind=rule.kind, area=rule.area or "Game", rule_id=rule.id,
                            title=rule.text("title", fields) or rule.id, explain=rule.text("explain", fields) or "",
                            fixes=rule.text("fixes", fields) or [], ic_title=rule.text("ic_title", fields),
                            fields=dict(fields), first_ts=when, last_ts=when, examples=[line.strip()],
                            links=rule.d.get("links", [])))
    if not any(f["kind"] == "problem" for f in out):
        out.append(_finding(severity="high", area="Game", title="The game crashed", first_ts=when, last_ts=when,
                            explain="The log ends with the game's crash handler taking over.",
                            fixes=["Repeated crashes: verify the game files in the RSI launcher.",
                                   "Note what you were doing when it happened for the Issue Council report."],
                            ic_title="Client crash"))
    return [f for f in out if f["kind"] == "problem"]


def _last_session_crash(backups_dir, current_start, library=None):
    """Did the session before this one crash, or end without the game shutting down normally?"""
    try:
        logs = sorted(Path(backups_dir).glob("*.log"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return []
    if not logs:
        return []
    last = logs[-1]
    if current_start - last.stat().st_mtime > 3 * 3600:
        return []
    try:
        with open(last, "rb") as f:
            f.seek(max(0, last.stat().st_size - 60000))
            tail = f.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    when_ts = last.stat().st_mtime
    when = dt.datetime.fromtimestamp(when_ts).strftime("%H:%M")
    if "crash handler taking over" in tail and library is not None:
        out = crash_findings(last, library)
        for f in out:
            f["title"] = "Last session: " + f["title"][0].lower() + f["title"][1:]
            f["first_ts"] = f["last_ts"] = when_ts
            f["fields"]["log"] = last.name
        return out
    if any(k in tail for k in ("CCIGBroker::FastShutdown", "Shutting down all force feedback", "<SystemQuit>")):
        return []
    return [_finding(severity="high", area="Game", title="Your last session ended without a normal shutdown",
                     explain=f"The previous log stops at {when} without the lines the game writes when it closes "
                             "properly, and without a crash report. That points to a freeze you had to kill, or a "
                             "power or PC problem.",
                     fixes=["Repeated freezes: verify the game files in the RSI launcher.",
                            "Note what you were doing when it happened for the Issue Council report."],
                     ic_title="Client froze (game closed without normal shutdown)",
                     fields={"log": last.name}, first_ts=when_ts, last_ts=when_ts)]
