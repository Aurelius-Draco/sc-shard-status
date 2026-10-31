"""1.4: Verse Shards for PC. Your own post card, the shown name, and the page pieces the new layout relies on."""
import re
import time
from pathlib import Path

from scstatus import config, dashboard, groups, report
from test_v13 import _App, _Comm

PAGE = (Path(__file__).resolve().parent.parent / "scstatus" / "static" / "index.html").read_text(encoding="utf-8")


def test_your_post_card_has_what_the_site_shows():
    app, comm = _App(), _Comm()
    g = groups.Groups(app, comm)
    g.post("recruit", "Mining", "bring a pick", "3", "")
    p = g.mine()[0]
    assert p["shard"] == "AU-90" and p["server"] == "37" and p["area_name"] == "Hurston"
    assert p["spots"] == 3 and p["note"] == "bring a pick" and p["handle"] is None
    assert p["keen"] == 0 and time.time() - p["created"] < 5
    g.tick(now=time.time())
    assert g.mine()[0]["keen"] == 1                     # one player pressed I'm interested


def test_name_shown_is_verse_shards_but_install_name_stays():
    assert config.APP_NAME == "SC Shard Status"         # folders, shortcuts and data never move
    assert config.DISPLAY_NAME == "Verse Shards for PC"
    assert "compiled by Verse Shards for PC v" in report.DISCLAIMER
    assert "<h1>Verse Shards</h1>" in PAGE and "<title>Verse Shards for PC</title>" in PAGE
    # An older copy already running is still found by the text it looks for
    assert 'content="SC Shard Status v__VERSION__"' in PAGE
    assert b"SC Shard Status v" in Path(dashboard.__file__).read_bytes()


def test_header_status_is_not_a_button_and_inventory_link_left_the_header():
    head = PAGE.split('<header class="top">')[1].split("</header>")[0]
    assert 'class="stat" id="shardPill"' in head and 'class="stat" id="ovPill"' in head
    assert "sc-inventory-tracker" not in head
    assert head.count("pill") == 1                       # only the update notice is still a pill


def test_now_tab_is_the_cockpit_hud_with_the_next_step_in_the_situation_panel():
    js = PAGE.split("async function renderNow()")[1].split("\n}\n")[0]
    hud, hop, acts = (js.index(x) for x in ('class="hud', 'class="hhop"', 'class="hacts"'))
    assert hud < hop < acts
    assert 'id="goCheck">What\'s gone wrong?' in js
    assert "Live numbers" not in js                          # the HUD gauges replace the old readout grid


def test_copy_for_chat_has_the_source_as_its_own_line_and_the_new_toast():
    assert "Copied. In game press Enter, then Ctrl+V." in PAGE
    assert '<div class="chatline src"><span>Found this on Verse Shards: verseshards.com</span>' in PAGE
    assert "function chatText(line) { return line; }"  in PAGE    # nothing appended to line 1 any more
    assert "Paste it into chat in game" not in PAGE


def test_groups_composer_uses_chips_and_a_stepper():
    js = PAGE.split("async function renderGroups()")[1].split("\n}\n")[0]
    assert "<select" not in js and 'class="achip"' in js and 'class="stepper"' in js
    assert "Add your handle if you'd rather people message you directly." in js
    assert "Report pirates ${c.area_name ? \"near \"" in js
    assert "Your post, as others see it" in js
