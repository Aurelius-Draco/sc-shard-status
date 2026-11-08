"""Pick lists for the pilot card (8 Nov): ships to pick with type-ahead, and places for "Favourite place".

Places come from the app's own place list (library/places.json, read from the game's files for the location
features). Ships are a hand-made list of flyable ships, in the names players use; it isn't read from the game, so a
new ship can be typed in by hand until the list is updated.
"""

import json
from pathlib import Path

# Most important first in the place picker: where players live, then the bodies, then everything else
PLACE_ORDER = ["landing zone", "city", "station", "rest stop", "distribution centre", "trading post", "settlement",
               "planet", "moon", "jump point", "Lagrange point", "asteroid base", "outpost", "facility", "comm array",
               "asteroid field", "landmark", "contested zone", "cave", "wreck"]

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

_places = None


def places():
    global _places
    if _places is None:
        try:
            data = json.loads((Path(__file__).parent / "library" / "places.json").read_text(encoding="utf-8"))
            rows = data.get("places") or []
        except (OSError, ValueError):
            rows = []
        def kind(p):
            lab = (p.get("label") or "").split(",")[0].strip()
            return "moon" if lab.startswith("moon of") else lab
        rank = {k: i for i, k in enumerate(PLACE_ORDER)}
        seen, out = set(), []
        for p in sorted(rows, key=lambda p: (rank.get(kind(p), len(PLACE_ORDER)), p.get("name") or "")):
            n = p.get("name")
            if n and n not in seen:
                seen.add(n)
                out.append({"name": n, "label": p.get("label") or ""})
        _places = out
    return _places


def lists():
    return {"ships": SHIPS, "places": places()}
