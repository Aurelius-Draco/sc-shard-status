"""Where you are, in words: the game's location codes (overlay and Game.log) turned into a system, an area and a
place name.

The overlay and the log use internal codes: RR_CRU_L4, Pyro3, RR_P3_LEO, PyroSolarSystem, RR_JP_StantonPyro.
The *area* is the planet (or jump point, or open space) a place belongs to: that's what a game server looks after
since server meshing, so it's what the board groups players by. Only the area is ever shared, never the exact place.
Names come from the game's own text file (global.ini) on the player's PC when it has them.
"""

import re
from pathlib import Path

SYSTEMS = {"stanton": "Stanton", "pyro": "Pyro", "nyx": "Nyx"}

# area key -> (system, fallback name, global.ini key for the name)
AREAS = {
    "hurston": ("stanton", "Hurston", "Stanton1"), "crusader": ("stanton", "Crusader", "Stanton2"),
    "arccorp": ("stanton", "ArcCorp", "Stanton3"), "microtech": ("stanton", "microTech", "Stanton4"),
    "pyro1": ("pyro", "Pyro I", "Pyro1"), "pyro2": ("pyro", "Monox", "Pyro2"), "pyro3": ("pyro", "Bloom", "Pyro3"),
    "pyro4": ("pyro", "Pyro IV", "Pyro4"), "pyro5": ("pyro", "Pyro V", "Pyro5"), "pyro6": ("pyro", "Terminus", "Pyro6"),
    "nyx1": ("nyx", "Nyx I", "Nyx1"), "nyx2": ("nyx", "Nyx II", "Nyx2"), "nyx3": ("nyx", "Nyx III", "Nyx3"),
    "stanton-space": ("stanton", "Stanton, open space", None), "pyro-space": ("pyro", "Pyro, open space", None),
    "nyx-space": ("nyx", "Nyx, open space", None),
    "gate-stanton-pyro": ("stanton", "Stanton to Pyro jump point", None),
    "gate-pyro-stanton": ("pyro", "Pyro to Stanton jump point", None),
    "gate-stanton-nyx": ("stanton", "Stanton to Nyx jump point", None),
    "gate-nyx-stanton": ("nyx", "Nyx to Stanton jump point", None),
    "gate-pyro-nyx": ("pyro", "Pyro to Nyx jump point", None),
    "gate-nyx-pyro": ("nyx", "Nyx to Pyro jump point", None),
}
STANTON_BODIES = {"1": "hurston", "2": "crusader", "3": "arccorp", "4": "microtech"}
SHORT = {"hur": "hurston", "cru": "crusader", "arc": "arccorp", "mic": "microtech"}
AREA_KEY_RX = re.compile(r"^[a-z0-9-]{2,24}$")


# The overlay's small text mixes up some letters and digits. Seen in real readings: "Stantoni", "StantonI_WeepingCove",
# "Stanton3_Areal8", "Stanton1__Lorville", "RR_P3_LE0", "vINVALID_LOCATION_ID".
_OCR_FIXES = [
    (re.compile(r"(?i)^(stanton|pyro|nyx)[il|](?=_|$)"), r"\g<1>1"),     # a trailing 1 read as i, l or |
    (re.compile(r"(?i)area[li]8"), "Area18"),
    (re.compile(r"(?i)le0"), "LEO"),
    (re.compile(r"_{2,}"), "_"),
    (re.compile(r"(?i)^[a-z]?(invalid_location)"), r"INVALID_LOCATION"),
]


def clean_code(code):
    """A location code with the overlay's usual misreads put right."""
    c = (code or "").strip()
    for rx, rep_ in _OCR_FIXES:
        c = rx.sub(rep_, c)
    return c


def area_of(code):
    """Location code -> area key (see AREAS), or None when it can't be told."""
    c = clean_code(code).lower()
    if not c or "invalid" in c:
        return None
    if m := re.search(r"jp_?(stanton|pyro|nyx)(stanton|pyro|nyx)", c):
        return f"gate-{m.group(1)}-{m.group(2)}"
    for sysname in SYSTEMS:
        if c in (sysname, f"{sysname}solarsystem") or c.startswith(f"{sysname}solarsystem"):
            return f"{sysname}-space"
    if m := re.search(r"pyro_?(\d)", c) or re.search(r"(?:^|_)p(\d)(?:_|$)", c):
        return f"pyro{m.group(1)}" if 1 <= int(m.group(1)) <= 6 else "pyro-space"
    if m := re.search(r"stanton_?(\d)", c):
        return STANTON_BODIES.get(m.group(1), "stanton-space")
    if m := re.search(r"nyx_?(\d)", c):
        return f"nyx{m.group(1)}" if f"nyx{m.group(1)}" in AREAS else "nyx-space"
    for tok in re.split(r"[_\W]+", c):
        if tok in SHORT:
            return SHORT[tok]
    for sysname in SYSTEMS:
        if sysname in c:
            return f"{sysname}-space"
    return None


def _readable(code):
    """CuttersRig -> Cutters Rig, ShubinMining_SCD1 -> Shubin Mining SCD1."""
    words = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Za-z])(?=\d{2,})", " ", code.replace("_", " "))
    return re.sub(r"\s+", " ", words).strip()


class Places:
    """Names for areas and places, from global.ini when the game has them."""

    KEY_RX = re.compile(r"^(RR_[A-Za-z0-9_]+|(?:Stanton|Pyro|Nyx)\d[A-Za-z0-9_]*|[A-Za-z]+_[A-Za-z0-9]+_Name|Pyro_[a-z]+)$")

    def __init__(self, game_dir=None, language="english"):
        self.names = {}
        if not game_dir:
            return
        path = Path(game_dir) / "Data" / "Localization" / language / "global.ini"
        try:
            with open(path, encoding="utf-8-sig", errors="replace") as f:
                for line in f:
                    key, sep, val = line.rstrip("\n").partition("=")
                    if not sep:
                        continue
                    key = key.split(",")[0]
                    low = key.lower()
                    if "desc" in low or "clinic" in low or not self.KEY_RX.match(key):
                        continue
                    val = val.strip()
                    if val and len(val) <= 60:
                        self.names.setdefault(low, val)
        except OSError:
            pass

    def area(self, key):
        """(system key, area name) for an area key."""
        sysname, fallback, ini = AREAS.get(key, (None, key, None))
        return sysname, (self.names.get(ini.lower()) if ini else None) or fallback

    def place(self, code):
        """A readable name for a place code: the game's own name, or the area it's in."""
        if not code:
            return ""
        c = clean_code(code)
        if "invalid" in c.lower():
            return ""
        if name := self.names.get(c.lower()):
            return name
        key = area_of(c)
        if not key:
            return re.sub(r"_+", " ", c)
        # A place on a planet or moon, e.g. Stanton1_CuttersRig or Stanton2b_ShubinMining_SCD1: name the place
        # (the game's name if it has one, else the code made readable) and the body it's on
        if m := re.fullmatch(r"(?i)(stanton|pyro|nyx)(\d)([a-z])?_(.+)", c):
            body_code = f"{m.group(1).capitalize()}{m.group(2)}{(m.group(3) or '').lower()}"
            _, planet = self.area(key)
            body = self.names.get(body_code.lower()) or (f"a moon of {planet}" if m.group(3) else planet)
            spot = _readable(m.group(4))
            if spot and not re.fullmatch(r"(?i)l\d", m.group(4)):
                return f"{spot}, {body}"
        _, area = self.area(key)
        if c.lower().startswith("rr_"):
            return f"station at the {area}" if key.startswith("gate-") else f"station near {area}"
        if re.fullmatch(r"(?i)(stanton|pyro|nyx)\d", c):
            return area
        if key.endswith("-space") or key.startswith("gate-"):
            return area
        return f"near {area}"

    def where(self, code):
        """Everything the board needs about a code: {system, area, area_name} or None."""
        key = area_of(code)
        if not key:
            return None
        sysname, name = self.area(key)
        return {"system": sysname, "area": key, "area_name": name}


# Places a player can name when reporting pirates somewhere else: stations, rest stops, outposts, settlements, caves,
# wrecks, Lagrange points, gateways, planets and moons in Stanton, Pyro and Nyx (library/places.json, built by
# tools/build_places.py from a researched list checked against the live patch). Each is tied to the area (game server)
# it belongs to, so the board files the report under the right area. Only the area's name goes on the report, never
# the place.
PLACES_FILE = Path(__file__).resolve().parent / "library" / "places.json"
_places = None


def report_places():
    """Every place: [{name, type, area, system}] (type is the short label shown in the suggestions)."""
    return [{"name": p["name"], "type": p["label"], "area": p["area"], "system": p["system"]} for p in _load()]


def _load():
    global _places
    if _places is None:
        try:
            import json
            _places = [p for p in json.loads(PLACES_FILE.read_text(encoding="utf-8"))["places"] if p.get("area") in AREAS]
        except (OSError, ValueError, KeyError):
            _places = [{"name": n, "label": "planet", "area": k, "system": sysname, "body": True}
                       for k, (sysname, n, _) in AREAS.items() if not k.endswith("-space") and not k.startswith("gate-")]
    return _places


def _in(systems):
    """Places in these systems; a jump point only when the system at its far end is on the shard too."""
    return [p for p in _load() if p["system"] in systems
            and (not p["area"].startswith("gate-") or p["area"].split("-")[2] in systems)]


def _out(p):
    return {"name": p["name"], "type": p["label"], "area": p["area"], "system": p["system"]}


def suggest_places(q, systems, limit=7):
    """Places whose name (or another name for it) holds q, in the given systems.

    Order: an exact name first; then names that start with what was typed (a planet or moon before the places named
    after it, so "cr" offers Crusader before CRU-L1); then other places, then planets and moons. Places only one source
    lists come after the rest of their group. Rarely named sites (coded mining bases, cloned facilities) only once 3 or
    more letters are typed, and always last."""
    q = (q or "").strip().lower()
    rows = []
    for p in _in(systems):
        names = [p["name"].lower()] + [a.lower() for a in p.get("aliases", [])]
        if q and not any(q in n for n in names):
            continue
        if p.get("minor") and len(q) < 3:
            continue
        tier = 0 if names[0].startswith(q) else 1 if any(n.startswith(q) for n in names[1:]) else 2  # name, other name, inside
        body = bool(p.get("body"))
        rows.append((bool(p.get("minor")), names[0] != q, tier, body == (tier == 2) if q else body,
                     bool(p.get("uncertain")), names[0], p))
    rows.sort(key=lambda r: r[:6])
    return [_out(r[6]) for r in rows[:limit]]


def find_place(name, systems):
    """The place with exactly this name, or one of its other names (any case), in the given systems, or None."""
    n = (name or "").strip().lower()
    if not n:
        return None
    hit = next((p for p in _in(systems) if p["name"].lower() == n), None) or \
        next((p for p in _in(systems) if n in (a.lower() for a in p.get("aliases", []))), None)
    return _out(hit) if hit else None
