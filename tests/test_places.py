"""The places behind "Somewhere else" on a pirate report: real stations, outposts and settlements, each tied to the
board's area, named the way the site accepts."""
import json
import re

from scstatus import locations

SP = {"stanton", "pyro"}
NAME_RX = re.compile(r"^[\w ,.'&()-]{2,40}$")          # the site's NAME_RX for area_name


def test_every_place_has_a_known_area_and_a_name_the_site_takes():
    rows = json.loads(locations.PLACES_FILE.read_text(encoding="utf-8"))["places"]
    assert len(rows) > 800
    assert {r["system"] for r in rows} == {"stanton", "pyro", "nyx"}
    for r in rows:
        assert r["area"] in locations.AREAS, r
        assert NAME_RX.match(r["name"]) and "_" not in r["name"] and "#" not in r["name"], r
        assert locations.AREAS[r["area"]][0] == r["system"], r            # the area is in the place's own system
        assert len(r["label"]) <= 40, r


def test_real_spots_map_to_their_planet():
    find = lambda n: locations.find_place(n, SP | {"nyx"})
    assert find("Ashland") == {"name": "Ashland", "type": "trading post, Ignis (Pyro V)", "area": "pyro5", "system": "pyro"}
    assert find("Ruin Station")["area"] == "pyro6" and find("Ruin Station")["type"] == "contested zone, Pyro"
    assert find("Checkmate")["area"] == "pyro2" and find("Orbituary")["area"] == "pyro3" and find("Rat's Nest")["area"] == "pyro5"
    assert find("Grim HEX") == {"name": "Grim HEX", "type": "station, Yela (Crusader)", "area": "crusader", "system": "stanton"}
    assert find("HUR-L1 Green Glade Station")["type"] == "rest stop, Hurston"
    assert find("Ignis")["area"] == "pyro5" and find("Daymar")["area"] == "crusader"
    assert find("Levski")["area"] == "nyx-space"


def test_other_names_find_the_place():
    assert locations.find_place("Checkmate Station", SP)["name"] == "Checkmate"
    assert locations.find_place("grim hex", SP)["name"] == "Grim HEX"
    assert locations.find_place("Pyro Va", SP)["name"] == "Ignis"
    assert locations.find_place("Mining Base #01K-I43", SP)["name"] == "Mining Base 01K-I43"     # the # is dropped
    assert [p["name"] for p in locations.suggest_places("checkmate st", SP)] == ["Checkmate"]


def test_ranking():
    names = lambda q, **k: [p["name"] for p in locations.suggest_places(q, SP, **k)]
    assert names("cr")[0] == "Crusader" and names("cr")[1].startswith("CRU")      # the planet, then places named after it
    assert names("ashland") == ["Ashland"]
    assert names("orb")[0] == "Orbituary"                                         # in both sources, before a one-source wreck
    assert names("pyro")[:3] == ["Pyro I", "Pyro IV", "Pyro V"]                   # own names before other names
    assert len(names("ash")) <= 7 and "Ashland" in names("ash")
    # Rarely named sites only from 3 letters, and after everything else
    assert not any(n.startswith("Mining Base") for n in names("mi", limit=50))
    mb = names("min", limit=200)
    assert any(n.startswith("Mining Base") for n in mb)
    first_minor = next(i for i, n in enumerate(mb) if n.startswith("Mining Base"))
    assert all(n.startswith("Mining Base") or not locations.find_place(n, SP) or n in mb[:first_minor] for n in mb)


def test_only_systems_on_your_shard():
    assert locations.find_place("Ashland", {"stanton"}) is None
    assert locations.find_place("Levski", SP) is None
    gates = [p for p in locations.suggest_places("gateway", {"stanton"}, limit=20)]
    assert gates == []                                     # every Stanton gateway leads somewhere not on this shard
    assert [p["name"] for p in locations.suggest_places("pyro gateway", SP)] == ["Pyro Gateway"]
