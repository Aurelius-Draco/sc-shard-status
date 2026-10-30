"""What you did, in order: a plain-English timeline of a session from Game.log.

Built from the events logparse.Session already collects: shards joined, loading, quantum jumps, places, armistice
zones, ships retrieved, contracts and objectives, freight elevator runs, disconnects and crashes. Place codes are
turned into names with locations.Places (the game's own text file). No handles or player names ever go in.
"""

import re

from .locations import Places
from .logparse import NORMAL_CAUSES

# What each kind is filed under on the Timeline tab
GROUPS = {"travel": "Travel", "place": "Places", "ship": "Ships", "contract": "Contracts",
          "connection": "Connection", "other": "Other"}
REGION_SHORT = {"apse2": "AU", "apse1": "ASIA", "ape1": "ASIA", "apne1": "ASIA", "use1": "USE", "use2": "USE",
                "usw1": "USW", "usw2": "USW", "euw1": "EU", "euw2": "EU", "euc1": "EU", "eun1": "EU"}


def shard_label(shard_id):
    """'pub_apse2a_12881860_020' -> 'AU-20'. Falls back to the id."""
    m = re.match(r"^[a-z]+_([a-z]+\d)[a-z]?_\d+_(\d+)$", shard_id or "")
    if not m:
        return shard_id or ""
    return f"{REGION_SHORT.get(m.group(1), m.group(1).upper())}-{int(m.group(2))}"


def ship_name(cls):
    """'ORIG_m80' -> 'ORIG M80', 'RSI_Constellation_Mk5_Centaurus' -> 'RSI Constellation Mk5 Centaurus'."""
    if not cls:
        return "a ship"
    parts = [p for p in cls.split("_") if p]
    return " ".join([parts[0].upper()] + [p[:1].upper() + p[1:] for p in parts[1:]])


def timeline(session, places=None, since=None, until=None):
    """Session -> [{ts, group, kind, text, area, code}] in time order."""
    places = places or Places()
    items = []

    def add(ts, group, kind, text, code=None, area=None):
        if ts is None or (since and ts < since) or (until and ts > until):
            return
        items.append({"ts": ts, "group": group, "kind": kind, "text": text, "code": code, "area": area})

    if session is None:
        return []
    for j in session.joins:
        add(j["ts"], "connection", "join", f"Joined shard {shard_label(j['shard_id'])}", j["shard_id"])
    for ld in session.loads:
        add(ld["ts"], "connection", "loaded", f"Loaded into the game ({round(ld['seconds'])} s)")
    for e in getattr(session, "travel", []):
        k = e["kind"]
        if k == "qt_target":
            where = _space(places.place(e["dest"]))
            where = where[5:] if where.startswith("near ") else f"a {where}" if where.startswith("station") else where
            add(e["ts"], "travel", k, f"Set course to {where}", e["dest"], _area(places, e["dest"]))
        elif k == "qt_arrived":
            where = _space(places.place(e.get("dest"))) if e.get("dest") else None
            add(e["ts"], "travel", k, f"Arrived {_at(where)}" if where else "Arrived at the quantum destination",
                e.get("dest"), _area(places, e.get("dest")))
        elif k == "location":
            where = _space(places.place(e["code"]))
            add(e["ts"], "place", k, _at(where)[:1].upper() + _at(where)[1:], e["code"], _area(places, e["code"]))
        elif k == "armistice":
            add(e["ts"], "place", k, "Entered an armistice zone" if e["on"] else "Left an armistice zone")
        elif k == "ship_retrieved":
            add(e["ts"], "ship", k, f"Retrieved {ship_name(e['ship'])} from the hangar" if e.get("ship")
                else "Retrieved a ship from the hangar", e.get("ship"))
    for c in session.contracts.values():
        name = c.get("name") or "a contract"
        if c.get("accepted"):
            add(c["accepted"], "contract", "accepted", f"Accepted contract \"{name}\"")
        for o in c.get("objectives", {}).values():
            if o.get("state") in ("complete", "failed"):
                verb = "Completed" if o["state"] == "complete" else "Failed"
                add(o.get("ts"), "contract", f"objective_{o['state']}", f"{verb} objective: {_short(o.get('text'))}")
        if c.get("ended") and c.get("result") != "active":
            res = {"complete": "Contract \"{}\" completed", "failed": "Contract \"{}\" failed",
                   "abandoned": "Contract \"{}\" abandoned", "dropped": "Contract \"{}\" dropped (left the server)"}
            add(c["ended"], "contract", f"contract_{c['result']}", res.get(c["result"], "Contract \"{}\" ended").format(name))
    for ts in session.freight_cycles:
        add(ts, "contract", "elevator", "Sent items down the freight elevator")
    for d in session.disconnects:
        if d.get("frontend") and d["cause"] in NORMAL_CAUSES:
            continue                         # the menu's own connection closing as you join a shard
        if d["cause"] in NORMAL_CAUSES and d.get("view_state") in (None, "eCVS_InGame"):
            add(d["ts"], "connection", "left", "Left the server")
        else:
            reason = (d.get("reason") or "lost the server").strip().rstrip(".")
            add(d["ts"], "connection", "disconnect", f"Disconnected: {reason} (code {d['cause']})")
    if session.quit:
        add(session.quit["ts"], "connection", "quit", "Quit the game")
    if session.crash:
        add(session.crash.get("ts") or session.end, "connection", "crash", "The game crashed",
            session.crash.get("exception"))

    items.sort(key=lambda x: x["ts"])
    out = []
    for it in items:          # the log often says the same thing twice within seconds
        if any(o["text"] == it["text"] and it["ts"] - o["ts"] <= 30 for o in out[-4:]):
            continue
        out.append(it)
    return out


def _space(where):
    """'Pyro, open space' -> 'open space in Pyro'; anything else unchanged."""
    m = re.fullmatch(r"(\w+), open space", where or "")
    return f"open space in {m.group(1)}" if m else where


def _area(places, code):
    w = places.where(code) if code else None
    return w["area"] if w else None


def _at(where):
    """'near Bloom' / 'at the station near Bloom' / 'in Pyro, open space' / 'at CRU-L4 Shallow Fields Station'."""
    if where.startswith("near "):
        return where
    if where.startswith("station"):
        return f"at the {where}"
    if "open space" in where:
        return f"in {where}"
    return f"at {where}"


def _short(text):
    t = re.sub(r"\s+", " ", text or "").strip()
    return t[:90] + ("…" if len(t) > 90 else "")


# --------------------------------------------------------------------------
# Steps to reproduce
# --------------------------------------------------------------------------

STEP_KINDS = ("location", "qt_target", "qt_arrived", "ship_retrieved", "accepted", "objective_complete",
              "objective_failed", "elevator", "join", "armistice")


def steps_from(items, end_text, max_steps=8):
    """Timeline items before a problem -> numbered-step texts, ending with the problem itself."""
    picked = [it for it in items if it["kind"] in STEP_KINDS and it["kind"] != "armistice"]
    # A course set and then arrived reads better as one step
    steps = []
    for i, it in enumerate(picked):
        if it["kind"] == "qt_target" and i + 1 < len(picked) and picked[i + 1]["kind"] == "qt_arrived":
            continue
        text = it["text"]
        if it["kind"] == "qt_arrived" and i > 0 and picked[i - 1]["kind"] == "qt_target":
            text = f"{picked[i - 1]['text']} and arrive"
        steps.append(_imperative(text))
    steps = _dedupe(steps)
    if len(steps) > max_steps - 1:
        steps = steps[-(max_steps - 1):]
    return steps + [end_text]


def _imperative(text):
    """Timeline wording ('Set course to Bloom') -> step wording ('Set course to Bloom.')."""
    t = text
    for a, b in (("At ", "Be at "), ("Near ", "Be near "), ("In ", "Be in "),("Accepted contract", "Accept the contract"), ("Retrieved ", "Retrieve "),
                 ("Sent items down", "Send items down"), ("Joined shard", "Join shard"),
                 ("Completed objective:", "Complete the objective:"), ("Failed objective:", "The objective fails:"),
                 ("Set course to", "Set a quantum course to")):
        if t.startswith(a):
            t = b + t[len(a):]
            break
    return t.rstrip(".") + "."


def _dedupe(steps):
    out = []
    for s in steps:
        if not out or out[-1] != s:
            out.append(s)
    return out
