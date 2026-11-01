#!/usr/bin/env python3
"""Build scstatus/library/places.json, the places a player can pick when reporting pirates somewhere else.

    python3 tools/build_places.py <researched sc-places.json>

The source is a researched list of named locations (Stanton, Pyro, Nyx; checked against the live patch). Each place is
tied to the board's area key (the planet a game server looks after; moons and their sites belong to their planet,
stations and Lagrange points to the planet they orbit, gateways to the jump point), given a short label for the
autocomplete ("trading post, Ignis (Pyro V)"), and checked against the site's rule for place names.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "scstatus" / "library" / "places.json"
NAME_RX = re.compile(r"^[\w ,.'&()-]{2,40}$")          # the site's NAME_RX (letters, numbers, space , . ' & ( ) -)

PLANETS = {
    "Hurston": "hurston", "Crusader": "crusader", "ArcCorp": "arccorp", "microTech": "microtech",
    "Pyro I": "pyro1", "Monox": "pyro2", "Bloom": "pyro3", "Pyro IV": "pyro4", "Pyro V": "pyro5", "Terminus": "pyro6",
    "Nyx I": "nyx1", "Nyx II": "nyx2", "Nyx III": "nyx3",
}
MOONS = {"Arial": "Hurston", "Aberdeen": "Hurston", "Magda": "Hurston", "Ita": "Hurston",
         "Cellin": "Crusader", "Daymar": "Crusader", "Yela": "Crusader", "Lyria": "ArcCorp", "Wala": "ArcCorp",
         "Calliope": "microTech", "Clio": "microTech", "Euterpe": "microTech",
         "Adir": "Pyro V", "Fairo": "Pyro V", "Fuego": "Pyro V", "Ignis": "Pyro V", "Vatra": "Pyro V", "Vuur": "Pyro V"}
LABEL = {"outpost": "outpost", "mining or research facility": "facility", "asteroid base": "asteroid base",
         "cave or underground facility": "cave", "settlement or colonial outpost": "settlement", "space station": "station",
         "Lagrange point": "Lagrange point", "asteroid belt or cluster": "asteroid field", "moon": "moon",
         "rest stop": "rest stop", "derelict or wreck site": "wreck", "comm array": "comm array", "planet": "planet",
         "distribution centre": "distribution centre", "jump point gate": "jump point", "landmark": "landmark",
         "landing zone": "landing zone", "city": "city", "contested zone": "contested zone"}
SYS = {"Stanton": "stanton", "Pyro": "pyro", "Nyx": "nyx"}
GATE_RX = re.compile(r"(Stanton|Pyro|Nyx) - (Stanton|Pyro|Nyx) jump point")


def body_where(b):
    """'Ignis (Pyro V)' for a moon, the planet's own name for a planet."""
    return f"{b} ({MOONS[b]})" if b in MOONS else b


def area_of(p):
    """The board's area key for a researched place, or None when it can't be tied to one."""
    sysname, body, near = SYS[p["system"]], p["body"], p.get("near")
    for b in (body, near):
        if b in PLANETS:
            return PLANETS[b]
        if b in MOONS:
            return PLANETS[MOONS[b]]
    if p["type"] == "jump point gate":
        m = GATE_RX.search(near or "") or GATE_RX.search(p["name"])
        if m and SYS[m.group(1)] == sysname:
            return f"gate-{SYS[m.group(1)]}-{SYS[m.group(2)]}"
        return None
    if body == "Delamar":
        return "nyx-space"                       # Delamar isn't one of the areas the board knows; Nyx open space
    if body == "space":
        return f"{sysname}-space"                # belts, clusters, the star, the system edge
    return None


def label_of(p):
    """The short text on the right of a suggestion: 'trading post, Ignis (Pyro V)', 'rest stop, Hurston'."""
    t, body, near = p["type"], p["body"], p.get("near")
    if "contested zone" in (p.get("tags") or []) or t == "contested zone":
        return f"contested zone, {p['system']}"
    if t == "planet":
        return f"planet, {p['system']}"
    if t == "moon":
        return f"moon of {MOONS.get(p['name'], p['system'])}"
    kind = "trading post" if "trading post" in (p.get("note") or "").lower() else LABEL.get(t, t)
    if body != "space":
        return f"{kind}, {body_where(body)}"
    if near in PLANETS or near in MOONS:
        return f"{kind}, {body_where(near)}"
    return f"{kind}, {p['system']}"


def build(src):
    out, dropped, renamed = [], [], []
    for p in src:
        name = p["name"].replace("’", "'")
        aliases = [a.replace("’", "'") for a in (p.get("aliases") or [])]
        if "#" in name:                              # Mining Base #01K-I43 -> Mining Base 01K-I43 (the site has no #)
            renamed.append(name)
            aliases.append(name)
            name = re.sub(r"\s*#\s*", " ", name).strip()
        area = area_of(p)
        if not area or not NAME_RX.match(name) or "_" in name:
            dropped.append(f"{p['name']} ({p['system']}, {p['body']}{', near ' + p['near'] if p.get('near') else ''})")
            continue
        row = {"name": name, "label": label_of(p), "area": area, "system": SYS[p["system"]],
               "body": p["type"] in ("planet", "moon")}
        if aliases:
            row["aliases"] = sorted(set(aliases) - {name})
        if p.get("minor"):
            row["minor"] = True
        if p.get("uncertain"):
            row["uncertain"] = True                  # in only one source: ranked after the rest
        if "contested zone" in (p.get("tags") or []):
            row["contested"] = True
        out.append(row)
    return out, dropped, renamed


if __name__ == "__main__":
    src = json.loads(Path(sys.argv[1] if len(sys.argv) > 1 else "/home/claude/sc-places.json").read_text(encoding="utf-8"))
    rows, dropped, renamed = build(src)
    OUT.write_text(json.dumps({"version": "4.10.2", "places": rows}, ensure_ascii=False, separators=(",", ":")) + "\n",
                   encoding="utf-8")
    by = {}
    for r in rows:
        by[r["system"]] = by.get(r["system"], 0) + 1
    print(f"{len(rows)} places {by}; renamed {len(renamed)}; dropped {len(dropped)}")
    for d in dropped:
        print("  dropped:", d)
