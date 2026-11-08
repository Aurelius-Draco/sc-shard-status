"""1.5.2: your game settings, saved. Made-up settings files in a made-up StarCitizen folder."""
import json
from pathlib import Path

import pytest

from scstatus import gamesettings as gsm
from scstatus.gamesettings import GameSettings

ATTRS = {"FOV": "70.5", "AudioSfxVolume": "0.33", "AudioMasterVolume": "1", "FilmGrain": "0", "SysSpec": "4",
         "SysSpec_ShadowMaps": "3", "SysSpec_Fog": "4", "LookAheadStrengthForward": "0", "LookAheadStrengthRoll": "0",
         "MouseSensitivity": "6.4", "selectedShipURN": "urn:sc:made-up", "PreferredAudioInputDeviceHash": "123"}
BINDS = """<ActionMaps><ActionProfiles profileName="default">
 <actionmap name="spaceship_general"><action name="v_close_all_doors"><rebind input="kb1_comma"/></action></actionmap>
 <actionmap name="player"><action name="pc_sprint"><rebind input="kb1_mouse5"/></action></actionmap>
</ActionProfiles></ActionMaps>"""


def _copy(root, name, attrs=None, binds=BINDS, case="user"):
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "Game.log").write_text("")
    if attrs is not None:
        p = d / case / "client" / "0" / "Profiles" / "default"
        p.mkdir(parents=True)
        gsm.write_attrs(p / "attributes.xml", attrs, "35")
        if binds:
            (p / "actionmaps.xml").write_text(binds)
    return d


@pytest.fixture
def setup(tmp_path):
    root = tmp_path / "StarCitizen"
    live = _copy(root, "LIVE", ATTRS)
    running = {"on": False}
    g = GameSettings(tmp_path / "data", live, running=lambda: running["on"], documents=lambda: tmp_path / "Documents")
    return g, root, running, tmp_path


def _copies(st):
    return {c["name"]: c for c in st["copies"]}


def test_nothing_saved_yet_shows_what_would_be_saved(setup):
    g, root, _, _ = setup
    st = g.state()
    assert st["saved"] is None
    c = _copies(st)
    assert c["LIVE"]["state"] == "unsaved" and c["PTU"]["state"] == "never" and c["Tech Preview"]["state"] == "never"
    rows = {r["name"]: r for grp in st["changed"] for r in grp["settings"]}
    assert rows["Field of view"] == {"name": "Field of view", "value": "70.5", "default": "55"}
    assert rows["SFX volume"]["value"] == "33%" and rows["Film grain"]["value"] == "Off"
    assert rows["Shadows"] == {"name": "Shadows", "value": "High", "default": "Very high"}   # follows the preset
    assert rows["Look ahead"]["value"] == "Off" and rows["Look ahead"]["default"] == "On"     # one row, not one per axis
    assert "Mouse sensitivity" not in rows           # its default isn't known for certain, so it's never "changed"
    assert "Fog" not in rows and "Master volume" not in rows
    assert not any("selectedShip" in r["name"] for r in rows.values())
    assert st["binds"]["count"] == 2
    assert {"action": "Sprint", "key": "Mouse button 5"} in st["binds"]["list"]


def test_saved_and_everything_matches(setup):
    g, root, _, _ = setup
    _copy(root, "PTU", ATTRS, case="USER")             # the game uses both cases
    meta = g.save()
    assert meta["binds"] == 2 and meta["changed"] >= 5
    c = _copies(g.state())
    assert c["LIVE"]["state"] == "match" and c["PTU"]["state"] == "match"
    with pytest.raises(ValueError, match="already have a save"):
        g.save()
    g.save(replace=True)
    assert (g.folder / "previous" / "attributes.xml").exists()


def test_one_copy_differs_and_says_how(setup):
    g, root, _, _ = setup
    # A fresh PTU: FOV and SFX at their defaults, film grain missing (so at its default), one bind missing
    ptu = dict(ATTRS, FOV="55", AudioSfxVolume="1")
    del ptu["FilmGrain"]
    _copy(root, "PTU", ptu, binds=BINDS.replace('<rebind input="kb1_comma"/>', ""))
    g.save()
    c = _copies(g.state())["PTU"]
    assert c["state"] == "differs"
    by = {d["name"]: d for d in c["diff"]}
    assert by["Field of view"]["saved"] == "70.5" and by["Field of view"]["now"] == "55"
    assert by["SFX volume"]["now"] == "100%"
    assert by["Film grain"] == {"key": "FilmGrain", "name": "Film grain", "group": "Graphics", "saved": "Off", "now": "On"}
    assert by["Close all doors"]["group"] == "Key binds" and by["Close all doors"]["now"] == "Game default"
    assert c["differs"] == 4


def test_game_running_blocks_putting_them_back(setup):
    g, root, running, tmp = setup
    _copy(root, "PTU", dict(ATTRS, FOV="55"))
    g.save()
    running["on"] = True
    assert g.state()["game_running"] is True
    with pytest.raises(ValueError, match="Star Citizen is running"):
        g.restore("PTU")
    assert not (tmp / "Documents").exists()            # nothing touched


def test_never_launched_copy_cant_take_them(setup):
    g, root, _, _ = setup
    _copy(root, "TECH-PREVIEW")                        # installed, never launched: no settings folder
    g.save()
    c = _copies(g.state())["Tech Preview"]
    assert c["state"] == "never" and c["launched"] is False
    with pytest.raises(ValueError, match="never been launched"):
        g.restore("TECH-PREVIEW")


def test_put_back_backs_up_first_and_keeps_the_copys_other_settings(setup):
    g, root, _, tmp = setup
    ptu = _copy(root, "PTU", {"FOV": "55", "AudioSfxVolume": "1", "Width": "2560", "QRCode": "1"}, binds=None)
    g.save()
    out = g.restore("PTU")
    backup = Path(out["backup"])
    assert backup.parent == tmp / "Documents" / "Verse Shards" / "Settings backups"
    assert backup.name.startswith("PTU ")
    before, _ = gsm.read_attrs(backup / "attributes.xml")
    assert before["FOV"] == "55"                       # what was there is kept
    now, ver = gsm.read_attrs(ptu / "user/client/0/Profiles/default/attributes.xml")
    assert now["FOV"] == "70.5" and now["AudioSfxVolume"] == "0.33" and ver == "35"
    assert now["Width"] == "2560" and now["QRCode"] == "1"          # the copy's own settings stay
    assert "selectedShipURN" not in now and "PreferredAudioInputDeviceHash" not in now   # never carried across
    assert (ptu / "user/client/0/Profiles/default/actionmaps.xml").read_text() == BINDS
    assert _copies(g.state())["PTU"]["state"] == "match"
    # a second put back the same minute doesn't overwrite the first backup
    out2 = g.restore("PTU")
    assert out2["backup"] != out["backup"]


def test_flag_on_now_once_per_launch(setup):
    g, root, _, _ = setup
    ptu = _copy(root, "PTU", dict(ATTRS, FOV="55"))
    assert g.flag(ptu, 1000.0, None) is None          # nothing saved: no flag
    g.save()
    f = g.flag(ptu, 1000.0, None)
    assert f["copy"] == "PTU" and f["differs"] == 1 and f["examples"] == ["Field of view"]
    assert g.flag(ptu, 1000.0, "1000.0") is None       # "Not now" on this launch
    assert g.flag(ptu, 2000.0, "1000.0")["copy"] == "PTU"   # the next launch shows it again
    assert g.flag(root / "LIVE", 1000.0, None) is None     # LIVE matches


def test_key_names_read_like_the_game():
    assert gsm.key_name("kb1_lalt+c") == "Left Alt+C"
    assert gsm.key_name("kb1_np_1") == "Numpad 1"
    assert gsm.key_name("js1_button3") == "Joystick 1 button 3"
    assert gsm.key_name("kb1_ ") == "Unbound"


def test_dashboard_routes(setup, monkeypatch):
    from scstatus import dashboard
    g, root, _, _ = setup
    app = type("A", (), {})()
    app.gamesettings = g
    app.gamesettings_dismiss = lambda: {"ok": True}
    assert dashboard.handle_post(app, "/api/gamesettings/save", {})["binds"] == 2
    with pytest.raises(ValueError):
        dashboard.handle_post(app, "/api/gamesettings/save", {})
    assert dashboard.handle_post(app, "/api/gamesettings/save", {"replace": True})
    with pytest.raises(ValueError):
        dashboard.handle_post(app, "/api/gamesettings/restore", {"copy": "PTU"})   # never launched
    json.dumps(g.state())                              # the GET answer is plain JSON
