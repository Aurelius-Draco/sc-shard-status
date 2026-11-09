"""1.6 (9 Nov, Ray: "not accurate on location and tasks, sometimes not using the common names"): the Now tab says
where you are and what you're tracking the way players say it."""
import threading
import time
from types import SimpleNamespace

from scstatus import app as appmod
from scstatus import issues
from scstatus.locations import Places

BOUNTY = "Verified Bounty: Augustus Emerson | MRT (Small Craft, Avg. Support) [500/1000/2000/8000/16000 Rep]"


def test_mission_is_the_contract_title_when_there_is_one():
    assert appmod.mission_label("BountyHuntersGuild_Bounty_Stanton_Medium_2", [{"name": BOUNTY}]) == \
        "Verified Bounty: Augustus Emerson | MRT (Small Craft, Avg. Support)"
    # two or none: the internal name, readable
    two = [{"name": BOUNTY}, {"name": "Delivery: Cargo to Orison"}]
    assert appmod.mission_label("BountyHuntersGuild_Bounty_Stanton_Medium_2", two) == \
        "Bounty Hunters Guild Bounty Stanton Medium"
    assert appmod.mission_label(None, [{"name": BOUNTY}]) is None


def test_places_by_their_common_names():
    p = Places()
    assert appmod._plain("RR_MIC_L3", p) == "MIC-L3 Endless Odyssey Station"
    assert appmod._plain("Microtech", p) == "microTech"
    assert appmod._plain("RR_CRU_L4", p) == "CRU-L4 Shallow Fields Station"
    assert appmod._plain("", p) is None


def _app(snap):
    return SimpleNamespace(lock=threading.Lock(), snaps=[snap], places=Places(), library=issues.Library())


def test_the_overlays_planet_line_is_left_out_when_the_location_is_known():
    # 9 Nov: at MIC-L3 the game's own Planet line said Crusader
    now = time.time()
    snap = {"ok": True, "ts": now - 5, "zone": "rs_habs_002_occu_001", "planet": "Crusader", "location": "RR_MIC_L3",
            "mission": "BountyHuntersGuild_Bounty_Stanton_Medium_2"}
    y = appmod.App.you_state(_app(snap), now, contracts=[{"name": BOUNTY}])
    assert y["planet"] is None and y["in_room"] and y["mission"].startswith("Verified Bounty: Augustus Emerson")
    # no location: the planet line, by its common name
    y = appmod.App.you_state(_app(dict(snap, location=None, planet="Microtech")), now)
    assert y["planet"] == "microTech"
