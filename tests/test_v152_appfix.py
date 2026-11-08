"""1.5.2 fixes from Ray's TEST run (8 Nov): places by the names players use (picker and logbook), pictures made small on
this PC instead of "That's too big", the pilot-only Set up header, the main ship panel, and the brag buttons."""
import base64
import re
import time

import pytest

from scstatus import app as appmod, config, dashboard, pilotlists, profile

HTML = (dashboard.STATIC / "index.html").read_text(encoding="utf-8")


# -- places
def test_common_places_come_first_and_by_their_common_names():
    L = pilotlists.places()
    names = [x["name"] for x in L]
    head = names[:len(pilotlists.HEADLINE)]
    assert head == pilotlists.HEADLINE                      # every headline place is real (in places.json)
    for n in ("Orison", "Lorville", "Area18", "New Babbage", "Port Tressler", "Everus Harbor", "Baijini Point",
              "Seraphim Station", "Grim HEX", "Ruin Station", "Orbituary", "Checkmate", "Starlight Service Station",
              "Gaslight", "Patch City"):
        assert n in head
    assert names.index("ARC-L1 Wide Forest Station") < names.index("HDMS-Edmond")   # rest stops before outposts
    assert names.index("HDMS-Edmond") < names.index("RMB-ALME")                       # coded mining bases last
    assert not any(n.upper().startswith("PYAM-") for n in names[:300])
    assert len(names) == len(set(names))


def test_internal_names_are_found_but_never_shown():
    L = {x["name"]: x for x in pilotlists.places()}
    assert "PYAM-EXHANG-0-1" not in L and "PYAM-EXHANG-0-1" in L["Executive Hangar"]["also"]
    assert "PYAM-FARSTAT-1-2" in L["PYR1 L2"]["also"]
    assert "PYAM-FARSTAT-2-4" in L["Checkmate"]["also"]


@pytest.mark.parametrize("given,common", [
    ("Stanton2_Orison", "Orison"), ("Stanton1_Lorville", "Lorville"), ("Stanton3_Area18", "Area18"),
    ("Stanton4_NewBabbage", "New Babbage"), ("RR_CRU_LEO", "Seraphim Station"), ("RR_HUR_LEO", "Everus Harbor"),
    ("RR_ARC_LEO", "Baijini Point"), ("RR_MIC_LEO", "Port Tressler"), ("RR_ARC_L1", "ARC-L1 Wide Forest Station"),
    ("RR_MIC_L1", "MIC-L1 Shallow Frontier Station"), ("RR_P2_L4", "Checkmate"), ("RR_P3_L1", "Starlight Service Station"),
    ("PYAM-FARSTAT-1-2", "PYR1 L2"), ("PYAM-EXHANG-0-1", "Executive Hangar"), ("grim hex", "Grim HEX"),
    ("Area 18", "Area18"), ("Pyro3", "Bloom"), ("Stanton2", "Crusader"),
])
def test_common_name(given, common):
    assert pilotlists.common_name(given) == common


def test_unknown_places_are_left_alone_not_made_up():
    assert pilotlists.common_name("ori") is None
    assert pilotlists.common_name("Somewhere New 9") is None
    assert pilotlists.place_name("INVALID_LOCATION_ID") == "Not known"
    assert pilotlists.place_name("") == "Not known"


def test_favourite_place_is_saved_by_its_common_name(tmp_path):
    p = profile.Profiles(tmp_path)
    assert p.save({"handle": "Demo_Pilot", "fav": "PYAM-EXHANG-0-1"})["fav"] == "Executive Hangar"
    assert p.save({"handle": "Demo_Pilot", "fav": "grim hex"})["fav"] == "Grim HEX"
    assert p.save({"handle": "Demo_Pilot", "fav": "My mate's hangar"})["fav"] == "My mate's hangar"


def test_picker_is_a_ranked_type_ahead_not_a_datalist():
    assert 'list="pfPlaces"' not in HTML and "<datalist id=\"pfPlaces\"" not in HTML
    assert "data-pf-fav" in HTML and "function placeMatches(" in HTML and "function placeCommon(" in HTML
    assert "also called" in HTML


# -- the logbook
def _app(tmp_path, monkeypatch):
    for mod in (appmod, config):
        monkeypatch.setattr(mod, "DATA", tmp_path / "data")
    monkeypatch.setattr(config, "save_setting", lambda k, v: None)
    cfg = dict(config.DEFAULT_CONFIG, game_dir=str(tmp_path / "nogame"), open_browser=False)
    return appmod.App(cfg)


def test_most_visited_places_use_common_names_and_merge(tmp_path, monkeypatch):
    a = _app(tmp_path, monkeypatch)
    now = time.time()
    snap = lambda loc, fps: {"ts": now, "ok": True, "client_fps": fps, "location": loc}
    a.snaps.extend([snap("Stanton2_Orison", 40), snap("Stanton2_Orison", 44), snap("Orison", 60),
                    snap("RR_CRU_LEO", 70), snap("INVALID_LOCATION_ID", 30), snap(None, 31)])
    rows = {r["location"]: r for r in a.pc()["by_location"]}
    assert rows["Orison"]["readings"] == 3 and rows["Orison"]["client_fps"] == 44
    assert rows["Seraphim Station"]["readings"] == 1
    assert rows["Not known"]["readings"] == 2
    assert not any(re.search(r"Stanton\d|RR_|_", k) for k in rows)


# -- the picture
def _big_png():
    import cv2
    import numpy as np
    rng = np.random.default_rng(7)
    img = rng.integers(0, 255, (1400, 1800, 3), dtype=np.uint8)        # noise: a PNG well over 900 KB
    ok, buf = cv2.imencode(".png", img)
    assert ok and len(buf) > profile.PIC_MAX
    return "data:image/png;base64," + base64.b64encode(bytes(buf)).decode()


def test_a_big_picture_is_made_small_on_this_pc(tmp_path):
    import cv2
    import numpy as np
    p = profile.Profiles(tmp_path)
    got = p.save({"handle": "Demo_Pilot", "pic": _big_png()})
    assert got["pic"].startswith("data:image/jpeg;base64,")
    f = tmp_path / "profile.jpg"
    assert f.is_file() and f.stat().st_size <= profile.PIC_MAX
    img = cv2.imdecode(np.frombuffer(f.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    assert max(img.shape[:2]) == profile.PIC_SIDE


def test_the_page_shrinks_pictures_and_never_blocks_set_up_on_one():
    assert "function pilotShrink(" in HTML and "512 / Math.max" in HTML and '"image/webp", 0.85' in HTML
    assert "data-pf-picmsg" in HTML and "The rest of your card saves without it." in HTML
    done = HTML[HTML.index('$("wzDone").onclick'):]
    done = done[:done.index("\n  };")]
    assert "pic: \"\"" in done and "/api/setup" in done
    assert done.index("/api/profile") < done.index("/api/setup")
    assert "That picture is too big to save. Pick a smaller one." in (dashboard.STATIC.parent / "dashboard.py").read_text(encoding="utf-8")


# -- Set up
def test_pilot_only_set_up_says_what_it_is_and_set_up_can_run_again():
    assert ("You've done Set up before. This version adds one step: your pilot card. Your other answers are kept, "
            "and you can run the whole Set up again any time from the Set up tab.") in HTML
    assert 'id="redoWiz">Run Set up again</button>' in HTML
    assert '$("redoWiz").onclick = () => openWizard(true);' in HTML


# -- the main ship panel
def test_ship_pictures_are_bundled_and_the_m80_gets_a_name_panel():
    pics = pilotlists.lists()["ship_pics"]
    assert len(pics) == 13 and "Origin M80" not in pics
    for ship, url in pics.items():
        assert ship in pilotlists.SHIPS
        assert (dashboard.STATIC / url.lstrip("/")).is_file()
        assert re.fullmatch(r"/img/ship-[a-z0-9-]+\.webp", url)          # served by the dashboard's /img/ route
    assert pilotlists.ship_pic("cutlass black") == "/img/ship-drake-cutlass-black.webp"
    assert pilotlists.ship_pic("Origin M80") is None
    body = HTML[HTML.index("function shipPanel("):]
    body = body[:body.index("\n}\n")]
    assert "Ship render from the Star Citizen Fankit" in body and 'class="shot is-name"' in body
    rule = re.search(r"\.pc-main \.shot \{([^}]*)\}", HTML).group(1)
    assert "repeating-linear-gradient" not in rule                                # the striped empty box is gone


# -- brag buttons
def test_every_brag_spot_is_the_amber_make_a_brag_card_button():
    lab = re.search(r"const LABEL = (\{[^}]*\})", HTML).group(1)
    for k in ("session", "week", "blueprints", "blueprint", "licence"):
        assert re.search(k + r': "Make a brag card"', lab), k
    assert 'class="btn brag-cta" data-brag="${esc(k)}"' in HTML
    assert 'class="vr-btn is-sm brag-btn"' not in HTML
    for spot in ('data-brag-spot="session"', 'data-brag-spot="blueprints"', 'data-brag-spot="licence"',
                 'data-brag-spot="blueprint"'):
        assert spot in HTML
