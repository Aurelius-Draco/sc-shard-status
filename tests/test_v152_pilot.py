"""1.5.2 pilot card: verify on RSI with a bio code (a fake RSI page, never the real site), the pick lists, the
saved brag image's file name and PNG words, and the pop-up's close button."""
import json
import re
import shutil
import struct
import subprocess
import zlib

import pytest

from scstatus import dashboard, pilotlists, profile

HTML = (dashboard.STATIC / "index.html").read_text(encoding="utf-8")


def _page(bio):
    return ('<html><div class="profile-content"><div class="entry bio"><span class="label">Bio</span>'
            f'<div class="value">{bio}</div></div></div></html>')


def _fake(status=200, page=""):
    calls = []

    def fetch(url):
        calls.append(url)
        if isinstance(status, Exception):
            raise status
        return status, page
    fetch.calls = calls
    return fetch


def test_verify_finds_the_code_in_the_bio_and_marks_the_card(tmp_path):
    p = profile.Profiles(tmp_path)
    with pytest.raises(ValueError, match="handle first"):
        p.verify_start(now=1000)
    p.save({"handle": "Demo_Pilot", "org": "Test Wing"})
    v = p.verify_start(now=1000)
    assert re.fullmatch(r"VS-[A-HJ-NP-Z2-9]{4}-[A-HJ-NP-Z2-9]{4}", v["code"])
    assert v["url"] == "https://robertsspaceindustries.com/citizens/Demo_Pilot" and v["expires"] == 1000 + 1800
    assert p.verify_start(now=1200)["code"] == v["code"]                 # the same code while it's still good
    fetch = _fake(page=_page(f"Hauler.<br>Code: {v['code'].lower()} thanks"))
    r = p.verify_check(now=1300, fetch=fetch)
    assert fetch.calls == ["https://robertsspaceindustries.com/citizens/Demo_Pilot"]
    assert r["verified"] == {"handle": "Demo_Pilot", "at": 1300}
    got = p.get()
    assert got["verified"]["handle"] == "Demo_Pilot" and "verify" not in got
    # Saving the card again with the same handle (any case) keeps the tick; a new handle takes it off
    assert p.save({"handle": "demo_pilot", "org": "Other"})["verified"]["at"] == 1300
    assert "verified" not in p.save({"handle": "Other_Pilot"})


@pytest.mark.parametrize("status,page,msg", [
    (200, _page("Just a hauler"), "isn't in your bio yet"),
    (200, "<html>no bio box here</html>", "Couldn't find a bio"),
    (404, "", "no citizen called Demo_Pilot"),
    (503, "", "didn't answer properly"),
    (OSError("offline"), "", "Couldn't reach robertsspaceindustries.com"),
])
def test_verify_says_plainly_what_went_wrong(tmp_path, status, page, msg):
    p = profile.Profiles(tmp_path)
    p.save({"handle": "Demo_Pilot"})
    p.verify_start(now=1000)
    with pytest.raises(ValueError, match=msg):
        p.verify_check(now=1100, fetch=_fake(status, page))
    assert "verified" not in p.get()


def test_verify_codes_run_out_and_can_be_cancelled(tmp_path):
    p = profile.Profiles(tmp_path)
    p.save({"handle": "Demo_Pilot"})
    with pytest.raises(ValueError, match="Get a code first"):
        p.verify_check(now=1000, fetch=_fake())
    v = p.verify_start(now=1000)
    with pytest.raises(ValueError, match="run out"):
        p.verify_check(now=1000 + 1801, fetch=_fake(page=_page(v["code"])))
    assert p.verify_start(now=5000)["code"]                              # a fresh code after it ran out
    p.save({"handle": "New_Handle"})                                     # a new handle drops a code in progress
    assert "verify" not in p.get()
    p.verify_start(now=6000)
    assert p.verify_cancel() == {"ok": True} and "verify" not in p.get()


def test_bio_reader_matches_the_site():
    assert profile.bio_from(_page("Line one<br/>Line &amp; two")) == "Line one\nLine & two"
    assert profile.bio_from("<html></html>") is None


def test_nothing_about_verify_goes_to_verseshards():
    src = (dashboard.STATIC.parent / "profile.py").read_text(encoding="utf-8")
    code = "\n".join(line for line in src.splitlines() if not line.lstrip().startswith("#"))
    assert "verseshards" not in code.lower()                            # only a comment names the site
    assert "https://robertsspaceindustries.com" in src


def test_pick_lists_are_real_data():
    L = pilotlists.lists()
    assert len(L["ships"]) >= 140 and len(set(L["ships"])) == len(L["ships"])
    for s in ("C2 Hercules", "Origin M80", "Constellation Mk V Centaurus", "Carrack", "Cutlass Black"):
        assert s in L["ships"]
    names = [x["name"] for x in L["places"]]
    assert len(names) > 500 and "Orison" in names and "Area18" in names
    assert all(set(x) == {"name", "label", "also", "tier"} and x["name"] for x in L["places"])


def test_setup_asks_for_the_pilot_card_once():
    from scstatus.app import App
    assert App.QUESTIONS["pilot"] == max(App.QUESTIONS.values())
    assert 'data-q="pilot"' in HTML and "Skip for now" in HTML and "Save my pilot card" in HTML


def test_pilot_card_button_is_up_top_with_its_line():
    assert 'class="pc-brag"' in HTML and 'data-brag="pilot"' in HTML
    assert "A picture of your pilot logbook to post where your mates are. Made on this PC, nothing uploaded." in HTML
    assert 'data-brag-spot="pilot"' not in HTML                          # the small one in the logbook head is gone


def test_only_log_lines_and_codes_are_mono_on_my_pilot():
    for sel in (".pc-id h2", ".pc-main .shot .sn", ".pc-main .shot .sl"):
        rule = re.search(re.escape(sel) + r" \{([^}]*)\}", HTML).group(1)
        assert "--mono" not in rule, sel


def test_pop_up_close_button_esc_and_backdrop_all_close():
    body = HTML[HTML.index("function dlg("):]
    body = body[:body.index("\n  }") + 4]
    assert '.vr-close' in body and "e.target === d" in body
    assert re.search(r'key(?:down)?.*Escape', HTML)


# ---- the saved brag image: file name and the words inside the PNG, run in Node when it's there
NODE = shutil.which("node")


def _js(name_from, name_to):
    a = HTML.index(name_from)
    return HTML[a:HTML.index(name_to, a)]


def _png():
    def chunk(t, b):
        return struct.pack(">I", len(b)) + t + b + struct.pack(">I", zlib.crc32(t + b) & 0xffffffff)
    raw = b"\x00\x00\x00\x00"
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def _chunks(data):
    i, out = 8, []
    while i < len(data):
        n, = struct.unpack(">I", data[i:i + 4])
        t, body, crc = data[i + 4:i + 8], data[i + 8:i + 8 + n], data[i + 8 + n:i + 12 + n]
        assert struct.unpack(">I", crc)[0] == zlib.crc32(t + body) & 0xffffffff, t
        out.append((t.decode(), body))
        i += 12 + n
    return out


@pytest.mark.skipif(not NODE, reason="needs Node")
def test_saved_png_carries_the_words_and_a_safe_file_name(tmp_path):
    src = tmp_path / "png.mjs"
    (tmp_path / "in.png").write_bytes(_png())
    src.write_text("""
import { readFileSync, writeFileSync } from "fs";
const esc = s => String(s);
let D = { handle: "Demo_Pilot" };
""" + _js("  const FILE_KIND =", "  const plain =") + _js("  const CRC =", "  async function drawToSave") + """
const meta = { Title: "Verse Shards Pilot card", Software: "Verse Shards for PC 1.5.2", Source: "https://verseshards.com",
  Description: "Pilot: 12 sessions. Made with Verse Shards for PC.", Copyright: "Unofficial fan-made card. Not affiliated with Cloud Imperium Games.", Author: "Demo_Pilot" };
const out = await withMeta(new Blob([readFileSync(process.argv[2])]), meta);
writeFileSync(process.argv[3], Buffer.from(await out.arrayBuffer()));
const names = [fileName({ kind: "pilot", handle: true }), fileName({ kind: "week", handle: false })];
D = { handle: 'Bad:Name*?' }; names.push(fileName({ kind: "session", handle: true }));
D = { handle: "" }; names.push(fileName({ kind: "licence", handle: true }));
console.log(JSON.stringify(names));
""", encoding="utf-8")
    r = subprocess.run([NODE, str(src), str(tmp_path / "in.png"), str(tmp_path / "out.png")], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    names = json.loads(r.stdout.strip().splitlines()[-1])
    day = r"\d{4}-\d{2}-\d{2}"
    assert re.fullmatch(rf"Demo_Pilot - Verse Shards Pilot card {day}\.png", names[0])
    assert re.fullmatch(rf"Verse Shards Week card {day}\.png", names[1])
    assert re.fullmatch(rf"BadName - Verse Shards Session card {day}\.png", names[2])
    assert re.fullmatch(rf"Verse Shards Licence card {day}\.png", names[3])
    ch = _chunks((tmp_path / "out.png").read_bytes())
    assert [t for t, _ in ch][0] == "IHDR" and ch[-1][0] == "IEND"
    words = {}
    for t, body in ch:
        if t == "iTXt":
            k, rest = body.split(b"\0", 1)
            assert rest[:4] == b"\0\0\0\0"                               # not compressed, no language
            words[k.decode()] = rest[4:].decode()
    assert words["Title"] == "Verse Shards Pilot card" and words["Source"] == "https://verseshards.com"
    assert words["Software"].startswith("Verse Shards for PC") and words["Author"] == "Demo_Pilot"
    assert words["Copyright"] == "Unofficial fan-made card. Not affiliated with Cloud Imperium Games."
