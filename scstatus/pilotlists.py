"""Pick lists for the pilot card (8 Nov): ships to pick with type-ahead, and places for "Favourite place".

Places come from the app's own place list (library/places.json, read from the game's files for the location
features). Ships are a hand-made list of flyable ships, in the names players use; it isn't read from the game, so a
new ship can be typed in by hand until the list is updated.
"""

import json
import re
from pathlib import Path

SHIPS = sorted(set("""
100i|125a|135c|300i|315p|325a|350r|400i|600i Explorer|600i Touring|85X|890 Jump|M50
A1 Spirit|C1 Spirit|A2 Hercules|C2 Hercules|M2 Hercules|Ares Inferno|Ares Ion|Intrepid|Mercury Star Runner
Zeus Mk II CL|Zeus Mk II ES|Zeus Mk II MR
Apollo Medivac|Apollo Triage|Aurora CL|Aurora ES|Aurora LN|Aurora LX|Aurora MR|Constellation Andromeda
Constellation Aquila|Constellation Phoenix|Constellation Taurus|Constellation Mk V Centaurus|Mantis|Polaris|Scorpius
Scorpius Antares
Avenger Stalker|Avenger Titan|Avenger Titan Renegade|Avenger Warlock|Eclipse|Gladius|Gladius Valiant|Hammerhead
Reclaimer|Redeemer|Retaliator|Sabre|Sabre Comet|Sabre Firebird|Sabre Peregrine|Vanguard Harbinger|Vanguard Hoplite
Vanguard Sentinel|Vanguard Warden
Arrow|Asgard|C8 Pisces|C8R Pisces Rescue|C8X Pisces Expedition|Carrack|Carrack Expedition|F7A Hornet Mk II
F7C Hornet Mk II|F7C-M Super Hornet Mk II|F7C-M Heartseeker Mk II|F7C-R Hornet Tracker Mk II|F7C-S Hornet Ghost Mk II
Gladiator|Hawk|Hurricane|Legionnaire|Lightning F8C|Paladin|Terrapin|Terrapin Medic|Valkyrie
MOLE|MPUV Cargo|MPUV Personnel|MPUV Tractor|RAFT|SRV|CSV-SM
Defender
Mustang Alpha|Mustang Beta|Mustang Delta|Mustang Gamma|Mustang Omega|Nomad
Buccaneer|Caterpillar|Corsair|Cutlass Black|Cutlass Blue|Cutlass Red|Cutlass Steel|Cutter|Cutter Rambler|Cutter Scout
Dragonfly Black|Dragonfly Yellowjacket|Golem|Herald|Ironclad|Ironclad Assault|Vulture
Blade|Glaive|Prowler|Prowler Utility|Talon|Talon Shrike
Railen|Syulen
P-52 Merlin|P-72 Archimedes|L-21 Wolf|L-22 Alpha Wolf
Expanse|Fortune|Freelancer|Freelancer DUR|Freelancer MAX|Freelancer MIS|Hull A|Hull C|Prospector|Razor|Razor EX
Razor LX|Reliant Kore|Reliant Mako|Reliant Sen|Reliant Tana|Starfarer|Starfarer Gemini|Starlancer MAX
Fury|Fury LX|Fury MX|Guardian|Guardian MX|Guardian QI
Nox|Khartu-al|San'tok.yai
Origin M80
""".replace("\n", "|").split("|")) - {""})

# Where players live and meet: the names everyone says, offered first when nothing is typed (all in places.json)
HEADLINE = ["Orison", "Lorville", "Area18", "New Babbage", "Levski", "Port Tressler", "Everus Harbor", "Baijini Point",
            "Seraphim Station", "Grim HEX", "Ruin Station", "Orbituary", "Checkmate", "Starlight Service Station",
            "Gaslight", "Patch City", "Rat's Nest", "Endgame", "Dudley & Daughters", "Megumi Refueling",
            "Rod's Fuel 'N Supplies"]

# Then by kind of place: stations and rest stops, then the bodies and the places a lot of people go, then the rest,
# and coded mining bases and asteroid clusters last
KIND_TIER = {"rest stop": 1, "station": 1, "landing zone": 1, "city": 1, "contested zone": 1, "trading post": 1,
             "distribution centre": 2, "settlement": 2, "planet": 2, "moon": 2, "jump point": 2, "Lagrange point": 2,
             "landmark": 2, "outpost": 3, "facility": 3, "comm array": 3, "cave": 3, "wreck": 3,
             "asteroid base": 4, "asteroid field": 4}

# The orbital station over each Stanton planet (RR_<planet>_LEO in the overlay and Game.log)
LEO = {"hur": "Everus Harbor", "cru": "Seraphim Station", "arc": "Baijini Point", "mic": "Port Tressler"}

_places = None
_index = None


def _kind(p):
    lab = (p.get("label") or "").split(",")[0].strip()
    return "moon" if lab.startswith("moon of") else lab


def _display(p):
    """The name players use. The game's internal PYAM-... codes show their Lagrange point (PYR1 L2) or, for the
    Executive Hangar, the name on it; every other place is already listed by the name players use."""
    name, aliases = p.get("name") or "", p.get("aliases") or []
    if name.upper().startswith("PYAM-") and aliases:
        return max(aliases, key=len)
    return name


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def places():
    """[{name, label, also, tier}]: name is what players call it (what's shown and saved), also holds its other
    names (the game's internal name among them) so typing either finds it. Sorted most-used first."""
    global _places
    if _places is None:
        try:
            data = json.loads((Path(__file__).parent / "library" / "places.json").read_text(encoding="utf-8"))
            rows = data.get("places") or []
        except (OSError, ValueError):
            rows = []
        head = {n: i for i, n in enumerate(HEADLINE)}

        def key(p):
            n = _display(p)
            tier = 0 if n in head else 4 if n.upper().startswith("PYAM-") else KIND_TIER.get(_kind(p), 3)
            return (tier, head.get(n, 0), bool(p.get("uncertain")), n.lower())
        seen, out = {}, []
        for p in sorted(rows, key=key):
            n = _display(p)
            if not n:
                continue
            also = [a for a in [p.get("name")] + list(p.get("aliases") or []) if a and a != n]
            if n in seen:                       # the same name in two systems (gateways): one entry, every other name
                e = seen[n]
                e["also"] += [a for a in also if a not in e["also"]]
                continue
            e = {"name": n, "label": p.get("label") or "", "also": also, "tier": key(p)[0]}
            seen[n] = e
            out.append(e)
        _places = out
    return _places


def _lookup():
    """Every name and other name (exact, any case, and letters-and-digits only) -> the common name."""
    global _index
    if _index is None:
        exact, loose = {}, {}
        for e in places():                      # most-used first, so a shared other name goes to the better place
            for n in [e["name"]] + e["also"]:
                exact.setdefault(n.lower(), e["name"])
                loose.setdefault(_norm(n), e["name"])
        _index = exact, loose
    return _index


def common_name(text):
    """The name players use for a place name, other name or location code, or None when it isn't one we know.

    Takes what the game writes (RR_CRU_LEO, RR_ARC_L1, RR_P3_L1, Stanton2_Orison, Stanton4_NewBabbage, Pyro3), the
    game's internal names (PYAM-FARSTAT-1-2) and the names players type (grim hex, area 18)."""
    t = (text or "").strip()
    if not t:
        return None
    exact, loose = _lookup()
    if hit := exact.get(t.lower()):
        return hit
    if m := re.fullmatch(r"(?i)rr_(hur|cru|arc|mic)_(leo|l[1-5])", t):
        planet, spot = m.group(1).lower(), m.group(2).upper()
        return LEO[planet] if spot == "LEO" else exact.get(f"{planet}-{spot}".lower())
    if m := re.fullmatch(r"(?i)rr_p([1-6])_l([1-5])", t):
        return exact.get(f"pyr{m.group(1)} l{m.group(2)}")
    if m := re.fullmatch(r"(?i)(stanton|pyro|nyx)(\d)([a-z])?_+(.+)", t):
        return loose.get(_norm(m.group(4))) if len(_norm(m.group(4))) >= 4 else None
    if m := re.fullmatch(r"(?i)(stanton|pyro|nyx)(\d)", t):
        from .locations import AREAS, area_of
        key = area_of(t)
        return exact.get(AREAS[key][1].lower()) if key in AREAS else None
    if len(_norm(t)) >= 4:
        return loose.get(_norm(t))
    return None


def place_name(code, names=None):
    """A place code or name as players say it: our common name, else the game's own text (names: a Places), else
    the code made readable. For the logbook's most-visited places."""
    if not (code or "").strip() or "invalid" in code.lower() or code.strip().lower() == "unknown":
        return "Not known"
    if hit := common_name(code):
        return hit
    said = names.place(code) if names is not None else ""
    if said:
        head = said.split(",")[0].strip()
        if hit := common_name(said) or common_name(head):
            return hit
        return said
    return re.sub(r"_+", " ", (code or "").strip()) or "Unknown"


# Ship pictures for the pilot card's main ship: the 13 flyable ships in CIG's official Fankit (Nov 2025), rendered
# from the Fankit's own models (Documents\\Verse Shards\\Design\\Share Cards\\Round 3 extras\\01 Ship renders), front left,
# 960 wide, untouched. The Fankit has no Origin M80, so it gets the styled name panel like every other ship.
SHIP_PICS = {
    "Sabre": "aegis-sabre", "F7C-M Super Hornet Mk II": "anvil-f7c-m-super-hornet", "Khartu-al": "aopoa-khartu-al",
    "MPUV Cargo": "argo-mpuv-cargo", "Defender": "banu-defender", "Mustang Alpha": "cnou-mustang-alpha",
    "Mercury Star Runner": "crusader-mercury-starrunner", "Cutlass Black": "drake-cutlass-black",
    "Blade": "esperia-blade", "P-52 Merlin": "kruger-p-52-merlin", "Freelancer MAX": "misc-freelancer-max",
    "600i Explorer": "origin-600i-explorer", "Constellation Aquila": "rsi-constellation-aquila",
}


def ship_pic(name):
    """The app's address for a ship's Fankit picture, or None."""
    slug = SHIP_PICS.get((name or "").strip()) or next(
        (v for k, v in SHIP_PICS.items() if k.lower() == (name or "").strip().lower()), None)
    return f"/img/ship-{slug}.webp" if slug else None


def lists():
    return {"ships": SHIPS, "places": places(), "ship_pics": {k: ship_pic(k) for k in SHIP_PICS}}
