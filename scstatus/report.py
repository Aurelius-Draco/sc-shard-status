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


def _utc(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC") if ts else "unknown"


def draft(finding, result, snapshot=None, location_hint=None):
    """Plain-text Issue Council report for one finding."""
    s = result.get("session", {})
    title = finding.get("ic_title") or finding["title"]
    title = re.sub(r"\s+", " ", title).strip()[:120]
    env = [
        f"Game version: {s.get('version') or 'unknown'} (build {s.get('build') or 'unknown'})",
        f"Shard: {s.get('shard_id') or 'unknown'}" + (f" ({s.get('region')})" if s.get("region") else ""),
    ]
    if snapshot:
        if snapshot.get("server_name"):
            env.append(f"Server: {snapshot['server_name']}")
        bits = []
        if snapshot.get("server_fps") is not None:
            bits.append(f"server fps {snapshot['server_fps']:g}")
        if snapshot.get("pop_shard") is not None:
            bits.append(f"shard pop {snapshot['pop_shard']}, server pop {snapshot.get('pop_srv')}")
        if snapshot.get("ping_ms") is not None:
            bits.append(f"ping {snapshot['ping_ms']:g} ms")
        if bits:
            env.append("At the time: " + ", ".join(bits))
    loc = location_hint or (snapshot or {}).get("location")
    if loc:
        env.append(f"Location: {loc}")
    env.append(f"First seen: {_utc(finding.get('first_ts'))}; last seen: {_utc(finding.get('last_ts'))}; "
               f"times logged: {finding.get('count', 1)}")

    steps = steps_for(finding)
    excerpt = "\n".join(x[:400] for x in finding.get("examples", [])[:5]) or "(no log lines; see attached Game.log)"
    summary = finding.get("explain", "").strip() + "\n\n" + DISCLAIMER
    sections = [
        {"key": "title", "label": "Title", "text": title},
        {"key": "summary", "label": "Summary", "text": summary},
        {"key": "steps", "label": "Steps to reproduce", "steps": steps, "text": "\n".join(steps)},
        {"key": "expected", "label": "Expected result", "text": expected_for(finding)},
        {"key": "actual", "label": "Actual result", "text": finding["title"].rstrip(".") + "."},
        {"key": "environment", "label": "Environment", "text": "\n".join(env)},
        {"key": "logs", "label": "Log lines (from Game.log)", "text": excerpt},
    ]
    numbered = "\n".join(f"{i}. {x}" for i, x in enumerate(steps, 1))
    body = "\n\n".join(
        f"{sec['label'].upper()}\n{numbered if sec['key'] == 'steps' else sec['text']}" for sec in sections
    ) + "\n\nATTACHMENTS\nGame.log from this session, plus screenshots if I took any.\n"
    return {"title": title, "sections": sections, "body": body}


def steps_for(f):
    """Steps as a list, one per Issue Council step box."""
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
    return ["(Describe what you were doing.)", "(What you did just before it went wrong.)", "(What happened.)"]


def expected_for(f):
    if f.get("fields", {}).get("contract"):
        return "Delivered items count toward the objective and the contract completes."
    if f.get("area") == "Connection":
        return "Stay connected."
    return "It works without the error."


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
    if log.exists():
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
