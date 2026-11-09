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


def test_my_pilot_is_the_design_and_doesnt_restyle_the_app():
    css = (STATIC / "pilot" / "my-pilot.css").read_text(encoding="utf-8")
    js = (STATIC / "pilot" / "my-pilot.js").read_text(encoding="utf-8")
    assert "window.VSPilot" in js and "pilotLoad()" in PAGE and "VP.render(data)" in PAGE
    # names the app already uses are renamed in the port (the header is .top, small counts are .cnt, the old logbook lb-)
    import re
    body = css[css.index("/* ---------- head:"):]
    for name in ("top", "cnt", "lb-g", "lb-fig", "pc-sub"):
        assert not re.search(r"\." + re.escape(name) + r"(?![a-z0-9-])", body), name
    # the system pieces it brings stay inside the page
    sys_part = css[css.index("system pieces"):css.index("/* ---------- head:")]
    for line in sys_part.splitlines():
        if "{" in line and not line.lstrip().startswith(("/*", "@media")):
            assert line.lstrip().startswith(".mp "), line


def test_timeline_lives_in_history():
    assert 'data-tab="timeline"' not in PAGE and 'data-sub="timeline"' in PAGE
    assert 'data-tab="groups"' not in PAGE                      # no Groups tab for now (Ray, 9 Nov)
    order = [m for m in ("data-tab=\"now\"", "data-tab=\"check\"", "data-tab=\"pc\"", "data-tab=\"blueprints\"",
                         "data-tab=\"history\"", "data-tab=\"issues\"")]
    assert [PAGE.index(o) for o in order] == sorted(PAGE.index(o) for o in order)
