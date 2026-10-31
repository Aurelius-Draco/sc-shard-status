"""Issue Council report drafts.

Builds a ready-to-paste report from a finding, and a folder holding everything
to attach: the report text, the relevant log lines, your full Game.log and any
screenshots you took around that time. You review it and submit it yourself on
the Issue Council; this tool never sends anything to CIG.
"""

import datetime as dt
import re
import shutil
import time
from pathlib import Path

from .config import APP_NAME, AUTHOR, DATA, REPO, VERSION

ISSUE_COUNCIL = "https://issue-council.robertsspaceindustries.com/projects/STAR-CITIZEN"

DISCLAIMER = (f"Report data compiled by {APP_NAME} v{VERSION} (community tool by {AUTHOR}, {REPO}) "
              "from the reporter's local Game.log and screenshots. Reviewed and submitted by the player.")
# The same, short enough to fit inside the Issue Council's boxes
CREDIT = "Compiled from my Game.log by SC Shard Status (Verse Shards); checked and sent by me."

# The Issue Council form's limits (characters), so every part pastes in without being cut off
LIMITS = {"title": 60, "step": 150, "steps": 10, "happened": 520, "expected": 320, "workaround": 320}
SEVERITIES = ("Polish", "Playable", "Hardly Playable", "Critical")
# A starting point for the form's Category box, from the library's area. The player picks the closest match.
CATEGORY = {"Network": "Desynchronization", "Connection": "Network", "Loading": "Loading", "Game": "Game client",
            "Vehicles": "Vehicles", "Quantum": "Quantum travel", "Transit": "Transit", "Freight elevator": "Cargo",
            "Cargo": "Cargo", "Inventory": "Inventory", "Shops": "Shops", "Services": "Services", "Audio": "Audio",
            "Character": "Character", "Contracts": "Missions", "Server": "Server performance"}
# Where a library entry is better described by something other than its area
CATEGORY_BY_RULE = {"vehicle-lost-control-slow-collision": "Desynchronization"}


def _utc(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if ts else "unknown"


def _hm(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%H:%M UTC") if ts else ""


def fit(text, n):
    """Trim to n characters at a word boundary, with an ellipsis when cut."""
    t = re.sub(r"[ \t]+", " ", str(text or "")).strip()
    if len(t) <= n:
        return t
    cut = t[:n - 1].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…"


def ic_version(branch, build, channel="LIVE"):
    """The game version as the Issue Council asks for it: 'LIVE 4.10.2 / 4.10.2-live.12913470'."""
    ch = (channel or "LIVE").upper()
    if not branch:
        return f"{ch} (build {build})" if build else ch
    return f"{ch} {branch} / {branch}-{ch.lower()}" + (f".{build}" if build else "")


def severity_for(f):
    if f.get("severity") == "high":
        return "Critical" if f.get("area") in ("Connection", "Loading", "Game") else "Hardly Playable"
    return {"medium": "Playable", "low": "Polish"}.get(f.get("severity"), "Playable")


def where_text(code, places, shard_id=None, server=None):
    """'Cutters Rig, Hurston, Stanton; shard AU-90, server game-37' from a location code and the shard."""
    from .community import shard_name
    bits = []
    if code and places is not None:
        place = places.place(code)
        w = places.where(code) or {}
        system = (w.get("system") or "").capitalize()
        if place and place.startswith("near "):
            place = place[5:]
        if place:
            bits.append(place + (f", {system}" if system and system.lower() not in place.lower() else ""))
    sh = ", ".join(x for x in ([f"shard {shard_name(shard_id)}"] if shard_id else []) + ([f"server {server}"] if server else []))
    return "; ".join(x for x in (", ".join(bits), sh) if x)


def doing_text(session, places=None, names=None, at=None, window_s=1200, contract=None):
    """A starting point for 'What were you doing?' from the log: contracts, where you were, items you were moving,
    the ship you were in. The player edits it; nothing here is guessed beyond what the log says."""
    if session is None:
        return ""
    at = at or session.end or time.time()
    out = []
    active = [c["name"] for c in session.contracts.values()
              if (c.get("accepted") or 0) <= at and (c.get("result") == "active" or (c.get("ended") or 0) >= at)]
    if contract and contract in active:
        active.append(contract)                   # the contract the problem is about, if it's one of them
    out.append(f"On the contract \"{active[-1]}\"." if active else "No active contract.")
    loc = next((e for e in reversed(session.travel) if e["kind"] == "location" and (e["ts"] or 0) <= at), None)
    place = where_text(loc["code"], places).split(";")[0] if loc and places is not None else ""
    items = []
    for ts, cls in reversed(session.item_moves):
        if ts is None or ts > at or at - ts > window_s:
            continue
        for c in cls:
            n = names.display(c) if names is not None else c
            n = re.sub(r"(?i)^harvestable_", "", n).replace("_", " ").strip()
            if n and n not in items and not re.search(r"(?i)\bmag(azine)?\b|_mag$", c):
                items.append(n)
    ship = None
    for e in reversed(session.travel):
        if (e["ts"] or 0) > at:
            continue
        if e["kind"] in ("qt_target", "ship_retrieved") and e.get("ship"):
            from .timeline import ship_name
            ship = ship_name(e["ship"])
            break
    if items:
        out.append(f"Moving items{f' at {place}' if place else ''} ({', '.join(items[:3])})"
                   + (f", then flying the {ship}." if ship else "."))
    elif place:
        out.append(f"At {place}" + (f", in the {ship}." if ship else "."))
    elif ship:
        out.append(f"Flying the {ship}.")
    return " ".join(out)


def draft(finding, result, snapshot=None, location_hint=None, session=None, places=None, names=None, mark=None,
          channel="LIVE", ic_link=None):
    """An Issue Council report laid out box by box like the form, each part inside the form's limit."""
    s = result.get("session", {})
    title = fit(re.sub(r"\s+", " ", finding.get("ic_title") or finding["title"]), LIMITS["title"])
    if snapshot and s.get("shard_id") and snapshot.get("shard_id") and snapshot["shard_id"] != s["shard_id"]:
        snapshot = None         # an overlay reading from a different shard says nothing about this one
    at = (mark or {}).get("ts") or finding.get("first_ts")
    server = (snapshot or {}).get("server_name") or (mark or {}).get("server")
    if server and "-" in server:
        server = "-".join(server.split("-")[-2:])          # pub-sc-alpha-game-37 -> game-37
    code = (mark or {}).get("location") or location_hint or (snapshot or {}).get("location")
    if not code and session is not None:            # where the log last put you before it happened
        code = next((e["code"] for e in reversed(getattr(session, "travel", []))
                     if e["kind"] == "location" and (e["ts"] or 0) <= (at or 1e18)), None)
    where = where_text(code, places, s.get("shard_id"), server)
    version = ic_version(s.get("branch"), s.get("build"), channel)

    # Steps: where you were and the server's state (from Verse Shards), then what the log shows you did
    lead_steps = []
    if where:
        lead_steps.append(fit(f"Be {'on' if where.startswith('shard ') else 'at'} {where}.", LIMITS["step"]))
    if snapshot and snapshot.get("server_fps") is not None:
        facts = f"Server fps was {snapshot['server_fps']:g}"
        if snapshot.get("pop_srv") is not None:
            facts += f" with {snapshot['pop_srv']} players on the server"
        lead_steps.append(fit(facts + " (game overlay, recorded by Verse Shards, verseshards.com).", LIMITS["step"]))
    body_steps = steps_for(finding, session, places)
    if body_steps and body_steps[0].startswith("(") and session is not None and finding.get("area") == "Vehicles":
        ship = _ship_at(session, at)
        if ship:
            body_steps = [x for x in body_steps if not x.startswith("(")]
            body_steps.insert(0, f"Take off in the {ship}.")
    if body_steps and body_steps[0].startswith("(") and lead_steps:
        body_steps = body_steps[1:]
    steps = [fit(x, LIMITS["step"]) for x in lead_steps + body_steps]
    if len(steps) > LIMITS["steps"]:
        steps = steps[:2] + steps[-(LIMITS["steps"] - 2):]

    doing = doing_text(session, places, names, at, contract=finding.get("fields", {}).get("contract"))
    base = finding.get("ic_summary", "").strip() or (
        f"{finding['title'].rstrip('.')}. {finding.get('explain', '').strip()}".strip())
    if mark and mark.get("ts"):
        base = f"I marked the moment at {_hm(mark['ts'])}. " + base
    happened = compose_happened(doing, base)
    expected = fit(expected_for(finding), LIMITS["expected"])
    fixes = finding.get("fixes") or []
    workaround = fit("(If anything got you out of it, say what here." +
                     (f" Others found this helps: {fixes[0].rstrip('.')}.)" if fixes else ")"), LIMITS["workaround"])
    env = [f"Game version: {version}", f"Where: {where or 'unknown'}"]
    if snapshot:
        bits = []
        if snapshot.get("server_fps") is not None:
            bits.append(f"server fps {snapshot['server_fps']:g}")
        if snapshot.get("pop_shard") is not None:
            bits.append(f"shard pop {snapshot['pop_shard']}, server pop {snapshot.get('pop_srv')}")
        if snapshot.get("ping_ms") is not None:
            bits.append(f"ping {snapshot['ping_ms']:g} ms")
        if bits:
            env.append("At the time: " + ", ".join(bits))
    env.append(f"First seen: {_utc(finding.get('first_ts'))}; last seen: {_utc(finding.get('last_ts'))}; "
               f"times logged: {finding.get('count', 1)}" + (f"; marked at {_utc(mark['ts'])}" if mark and mark.get("ts") else ""))
    excerpt = "\n".join(x[:400] for x in finding.get("examples", [])[:5]) or "(no log lines; see attached Game.log)"
    shot_time = _hm(at) if at else "the time it happened"
    evidence = (f"Attach the Game.log from the report folder, and any screenshots from around {shot_time} "
                "(the session QR code helps CIG find your session, if you had it on).")
    sections = [
        {"key": "title", "label": "Issue title", "text": title, "limit": LIMITS["title"]},
        {"key": "version", "label": "Game version", "text": version},
        {"key": "category", "label": "Issue category (suggested)", "text": CATEGORY_BY_RULE.get(finding.get("rule_id")) or CATEGORY.get(finding.get("area"), "Other"),
         "note": "Pick the closest match in the Issue Council's list."},
        {"key": "severity", "label": "How bad is it? (suggested)", "text": severity_for(finding), "options": SEVERITIES},
        {"key": "doing", "label": "What were you doing?", "text": doing, "note": "From your Game.log. Edit it; it starts What happened."},
        {"key": "steps", "label": "How did you get there?", "steps": steps, "text": "\n".join(steps),
         "limit": LIMITS["step"], "max": LIMITS["steps"]},
        {"key": "happened", "label": "What happened?", "text": happened, "base": base, "limit": LIMITS["happened"]},
        {"key": "expected", "label": "What should have happened?", "text": expected, "limit": LIMITS["expected"]},
        {"key": "workaround", "label": "Did you find a workaround?", "text": workaround, "limit": LIMITS["workaround"]},
        {"key": "evidence", "label": "Evidence", "text": evidence},
        {"key": "environment", "label": "Details for reference", "text": "\n".join(env)},
        {"key": "logs", "label": "Log lines (from Game.log)", "text": excerpt},
    ]
    contribution = None
    if ic_link:
        hw = (getattr(session, "hardware", None) or {}) if session is not None else {}
        setup = ", ".join(x for x in (hw.get("cpu"), hw.get("gpu"), f"{round(hw['ram_mb'] / 1000)} GB RAM" if hw.get("ram_mb") else None) if x)
        contribution = {"url": ic_link.get("url"), "title": ic_link.get("title"), "sections": [
            {"key": "c_version", "label": "Version", "text": version},
            {"key": "c_setup", "label": "Setup", "text": setup or "(Your PC: CPU, graphics card, memory.)"},
            {"key": "c_more", "label": "More info", "text": fit(" ".join(x for x in (doing, f"Where: {where}." if where else "",
                f"Marked at {_hm(mark['ts'])}." if mark and mark.get("ts") else "", CREDIT) if x), LIMITS["happened"])},
            {"key": "c_severity", "label": "Severity (suggested)", "text": severity_for(finding), "options": SEVERITIES},
        ]}
    numbered = "\n".join(f"{i}. {x}" for i, x in enumerate(steps, 1))
    body = "\n\n".join(
        f"{sec['label'].upper()}\n{numbered if sec['key'] == 'steps' else sec['text']}" for sec in sections
    ) + f"\n\n{DISCLAIMER}\n"
    return {"title": title, "sections": sections, "body": body, "contribution": contribution, "limits": LIMITS}


def _ship_at(session, at):
    from .timeline import ship_name
    for e in reversed(getattr(session, "travel", [])):
        if (e["ts"] or 0) <= (at or 1e18) and e["kind"] in ("qt_target", "ship_retrieved") and e.get("ship"):
            return ship_name(e["ship"])
    d = [x for x in getattr(session, "deaths", []) if (x["ts"] or 0) >= (at or 0) - 300]
    return ship_name(d[0]["ship"]) if d else None


def compose_happened(doing, base):
    """'What happened?': what you were doing, then what went wrong, then the credit line, inside 520 characters."""
    room = LIMITS["happened"] - len(CREDIT) - 2
    text = fit(" ".join(x for x in (doing.strip(), base.strip()) if x), room)
    return text + "\n" + CREDIT


def steps_for(f, session=None, places=None):
    """Steps as a list, one per Issue Council step box. Built from what the log shows you did in the 30 minutes
    before the problem when it can be; otherwise a template to fill in."""
    base = _template_steps(f)
    first = f.get("first_ts")
    if session is not None and first:
        from .timeline import STEP_KINDS, steps_from, timeline
        # A contract problem runs from taking it to the last delivery, so its steps run to the last sighting
        until = max(first, f.get("last_ts") or first) if f.get("area") == "Contracts" else first
        items = timeline(session, places, since=first - 1800, until=until)
        if any(i["kind"] in STEP_KINDS and i["kind"] != "armistice" for i in items):
            return steps_from(items, _final_step(f, base))
    return base


def _final_step(f, base):
    """The step that says what went wrong, worded for the end of a list of real steps."""
    if f.get("fields", {}).get("contract") or f.get("area") == "Contracts" \
            or (base and base[-1] == "The objective does not progress."):
        return "The objective does not progress."
    if base and not base[-1].startswith("("):
        return base[-1]
    return f["title"].rstrip(".") + "."


def _template_steps(f):
    c = f.get("fields", {}).get("contract")
    items = f.get("fields", {}).get("items") or ([f["fields"]["item_name"]] if f.get("fields", {}).get("item_name") else [])
    if c and items:
        return [f"Accept the contract \"{c}\".", f"Collect the required item(s): {', '.join(items)}.",
                "Deliver them as the contract asks (freight elevator).", "The objective does not progress."]
    if items:
        return [f"Send {', '.join(items)} through the freight elevator or cargo system.",
                "The items are not handled (see the log lines)."]
    if f.get("area") == "Connection":
        return ["Play normally on the shard listed in Environment.", "The connection drops (see the log lines)."]
    return ["(Describe what you were doing.)", "(What you did just before it went wrong.)", f["title"].rstrip(".") + "."]


def expected_for(f):
    if f.get("fields", {}).get("contract"):
        return "Delivered items count toward the objective and the contract completes."
    return {"Connection": "Stay connected.", "Network": "Stay connected, with everything where the game shows it.",
            "Vehicles": "The ship keeps responding to the controls and flies normally.",
            "Transit": "The elevator or tram arrives and takes me where I asked.",
            "Freight elevator": "The freight elevator takes the items and they arrive where they should.",
            "Inventory": "Items move where I put them and stay there.", "Quantum": "Quantum travel takes me to the destination.",
            "Loading": "The game loads into the universe.", "Shops": "The purchase or sale goes through.",
            }.get(f.get("area"), "It works without the error.")


def bundle(finding, result, report, game_dir, out_root=None, minutes_around=20):
    """Make a folder with the report, the log and nearby screenshots. Returns its path."""
    out_root = Path(out_root or DATA / "reports")
    stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M")
    slug = re.sub(r"[^a-z0-9]+", "-", (finding.get("rule_id") or finding["title"]).lower()).strip("-")[:40]
    folder = out_root / f"{stamp}_{slug}"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "issue-council-report.txt").write_text(report["body"], encoding="utf-8")
    game = Path(game_dir or ".")
    log = game / "Game.log"
    old = finding.get("fields", {}).get("log")
    if old and (game / "logbackups" / old).exists():
        shutil.copy2(game / "logbackups" / old, folder / old)      # the earlier session the finding is about
    elif log.exists():
        shutil.copy2(log, folder / "Game.log")
    lo = (finding.get("first_ts") or time.time()) - minutes_around * 60
    hi = (finding.get("last_ts") or time.time()) + minutes_around * 60
    shots = game / "screenshots"
    n = 0
    if shots.exists():
        for p in sorted(shots.iterdir()):
            if p.suffix.lower() in (".jpg", ".png") and lo <= p.stat().st_mtime <= hi and n < 10:
                shutil.copy2(p, folder / p.name)
                n += 1
    return folder, n
