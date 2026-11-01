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


# Places a player can name when reporting pirates somewhere else, each with the area (game server) it belongs to, so
# the board files it under the right area. Only the area is sent; the place name shows on the report.
# (name, type, area key). Stations orbiting a body belong to that body's area (RR_P3_LEO is Bloom's area, and so on).
_MOONS = {"hurston": ["Arial", "Aberdeen", "Magda", "Ita"], "crusader": ["Cellin", "Daymar", "Yela"],
          "arccorp": ["Lyria", "Wala"], "microtech": ["Calliope", "Clio", "Euterpe"],
          "pyro5": ["Adir", "Fairo", "Fuego", "Ignis", "Vatra", "Vuur"]}
_STATIONS = [("Everus Harbor", "hurston"), ("Seraphim Station", "crusader"), ("Grim HEX", "crusader"),
             ("Baijini Point", "arccorp"), ("Port Tressler", "microtech"),
             ("Checkmate", "pyro2"), ("Orbituary", "pyro3"), ("Rat's Nest", "pyro5"), ("Ruin Station", "pyro6")]
_CITIES = [("Lorville", "hurston"), ("Orison", "crusader"), ("Area18", "arccorp"), ("New Babbage", "microtech")]
_LAGRANGE = {"HUR": "hurston", "CRU": "crusader", "ARC": "arccorp", "MIC": "microtech"}


def report_places():
    """Every place in REPORT order: [{name, type, area, system}]."""
    out = []
    planet = lambda key: AREAS[key][1]
    for key, (sysname, name, _) in AREAS.items():
        if key.endswith("-space"):
            continue
        if key.startswith("gate-"):
            out.append({"name": name, "type": "jump point", "area": key, "system": sysname})
        else:
            out.append({"name": name, "type": "planet" if sysname == "stanton" else f"planet, {SYSTEMS[sysname]}",
                        "area": key, "system": sysname})
    for key, moons in _MOONS.items():
        out += [{"name": m, "type": f"moon of {planet(key)}", "area": key, "system": AREAS[key][0]} for m in moons]
    for name, key in _STATIONS:
        sysname = AREAS[key][0]
        out.append({"name": name, "type": f"station, {planet(key) if sysname == 'stanton' else SYSTEMS[sysname]}",
                    "area": key, "system": sysname})
    for name, key in _CITIES:
        out.append({"name": name, "type": f"city, {planet(key)}", "area": key, "system": "stanton"})
    for short, key in _LAGRANGE.items():
        out += [{"name": f"{short}-L{n}", "type": "Lagrange point", "area": key, "system": "stanton"} for n in range(1, 6)]
    return out


def suggest_places(q, systems, limit=7):
    """Places whose name holds q, in the given systems; names that start with q first."""
    q = (q or "").strip().lower()
    rows = [p for p in _in(systems) if not q or q in p["name"].lower()]
    if q:
        rank = lambda t: 0 if t.startswith("planet") else 1 if t.startswith("moon") else 3 if t == "jump point" \
            else 4 if t == "Lagrange point" else 2
        rows.sort(key=lambda p: (not p["name"].lower().startswith(q), rank(p["type"]), p["name"].lower()))
    return rows[:limit]


def _in(systems):
    """Places in these systems; a jump point only when the system at its far end is on the shard too."""
    return [p for p in report_places() if p["system"] in systems
            and (not p["area"].startswith("gate-") or p["area"].split("-")[2] in systems)]


def find_place(name, systems):
    """The place with exactly this name (any case) in the given systems, or None."""
    n = (name or "").strip().lower()
    return next((p for p in _in(systems) if p["name"].lower() == n), None)
