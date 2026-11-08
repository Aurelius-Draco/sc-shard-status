"""1.6: the About tab is the site's own About (Ray, 8 Nov), drawn by the site's home page code bundled in static/site."""
from pathlib import Path

from scstatus import dashboard

STATIC = Path(dashboard.__file__).resolve().parent / "static"
PAGE = (STATIC / "index.html").read_text(encoding="utf-8")


def test_every_site_file_is_bundled():
    for path in dashboard.SITE_FILES:
        assert (STATIC / path.lstrip("/")).is_file(), path


def test_about_uses_the_site_parts():
    assert 'V.part("made")' in PAGE and 'V.part("trust")' in PAGE
    assert '"/api/about/site"' in PAGE
    # the demo switch says it isn't the player's own setting
    assert "your own setting is on the Set up tab" in PAGE


def test_the_board_pips_dont_clash_with_the_site_wrapper():
    # the site's page wrapper is .hp; the app's pips are .hpip
    assert '<i class="hp ' not in PAGE and "\n.hp {" not in PAGE


def test_site_numbers_only_with_board_or_updates_on():
    src = (STATIC.parent / "dashboard.py").read_text(encoding="utf-8")
    i = src.index('"/api/about/site"')
    assert 'community_board' in src[i:i + 500] and 'updater.enabled' in src[i:i + 500]


def test_fonts_point_at_the_bundled_copies():
    css = (STATIC / "site" / "holo-foil.css").read_text(encoding="utf-8")
    assert 'url("/fonts/' not in css and 'url("/brag/fonts/' in css
