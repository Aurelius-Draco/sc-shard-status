"""My pilot: your profile card. Kept in the data folder next to config.json and never sent anywhere.

profile.json holds the fields; the picture is saved beside it as profile.png, .jpg, .webp or .gif. The dashboard
hands the picture back to the page as a data URL, so nothing outside this PC ever sees it.
"""

import base64
import html as _html
import json
import re
import secrets
import time
import urllib.request

from .config import DATA

FIELDS_TEXT = {"handle": 30, "name": 30, "org": 40, "region": 20, "times": 40, "bio": 200, "fav": 60}
EXP = ("new", "regular", "veteran")
VOICE = ("voice", "text")
PIC_MAX = 900 * 1024            # about 900 KB once decoded
PIC_RX = re.compile(r"^data:image/(png|jpeg|webp|gif);base64,([A-Za-z0-9+/=\s]+)$")
EXT = {"png": "png", "jpeg": "jpg", "webp": "webp", "gif": "gif"}
MIME = {v: k for k, v in EXT.items()}


def _text(v, n):
    return " ".join(v.split())[:n] if isinstance(v, str) else ""


def _list(v, n, each=40):
    if not isinstance(v, list):
        return []
    out = []
    for x in v:
        if isinstance(x, str) and x.strip() and x.strip()[:each] not in out:
            out.append(x.strip()[:each])
    return out[:n]


def clean(p):
    """Only the known fields, trimmed to their limits. Returns (profile, picture bytes and type, or None)."""
    if not isinstance(p, dict):
        raise ValueError("Nothing to save.")
    out = {k: _text(p.get(k), n) for k, n in FIELDS_TEXT.items()}
    out["exp"] = p.get("exp") if p.get("exp") in EXP else ""
    out["voice"] = p.get("voice") if p.get("voice") in VOICE else ""
    out["ships"] = _list(p.get("ships"), 30)
    out["acts"] = _list(p.get("acts"), 12)
    out["main"] = p.get("main") if p.get("main") in out["ships"] else (out["ships"][0] if out["ships"] else "")
    if not out["handle"]:
        raise ValueError("Add your RSI handle first.")
    pic = p.get("pic")
    picture = None
    if isinstance(pic, str) and pic:
        m = PIC_RX.match(pic)
        if not m:
            raise ValueError("That picture isn't a PNG, JPEG, WebP or GIF.")
        try:
            data = base64.b64decode(re.sub(r"\s", "", m.group(2)), validate=True)
        except ValueError:
            raise ValueError("That picture couldn't be read.")
        if len(data) > PIC_MAX:
            raise ValueError("That picture is too big. Try one under about 900 KB.")
        picture = (data, EXT[m.group(1)])
    return out, picture


# Verifying the pilot card (8 Nov): the same check verseshards.com uses for org claims. The app shows a short code, the
# player puts it anywhere in their RSI bio, and the app reads their public citizen page from this PC. Nothing is sent to
# Verse Shards; the only request is the page RSI shows anyone.
RSI = "https://robertsspaceindustries.com"
HANDLE_RX = re.compile(r"^[A-Za-z0-9_-]{3,30}$")
CODE_ABC = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
CODE_S = 30 * 60                 # a code lasts 30 minutes, as on the site
UA = "Verse Shards for PC (pilot card check)"


def new_code():
    pick = lambda n: "".join(secrets.choice(CODE_ABC) for _ in range(n))
    return f"VS-{pick(4)}-{pick(4)}"


def bio_from(page):
    """The bio text from an RSI citizen page, or None when the page has no bio box (as the site's bioFrom)."""
    m = re.search(r'class="entry bio">[\s\S]*?class="value">([\s\S]*?)</div>', str(page or ""))
    if not m:
        return None
    t = re.sub(r"<br\s*/?>", "\n", m.group(1), flags=re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"[ \t]+", " ", _html.unescape(t)).strip()


def _fetch(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read(600_000).decode("utf-8", "replace")


class Profiles:
    def __init__(self, folder=None):
        self.folder = folder or DATA

    @property
    def path(self):
        return self.folder / "profile.json"

    def _pictures(self):
        return [self.folder / f"profile.{e}" for e in MIME]

    def get(self):
        try:
            p = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(p, dict):
            return None
        p["pic"] = ""
        for f in self._pictures():
            if f.is_file():
                p["pic"] = f"data:image/{MIME[f.suffix[1:]]};base64," + base64.b64encode(f.read_bytes()).decode()
                break
        return p

    def _raw(self):
        try:
            p = json.loads(self.path.read_text(encoding="utf-8"))
            return p if isinstance(p, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write(self, prof):
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(prof, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def save(self, raw):
        """Save the card. A missing or empty picture keeps none; "keep" leaves the saved one as it is. A verified tick
        and a code in progress stay only while the handle stays the same: a new handle has to be checked again."""
        keep = isinstance(raw, dict) and raw.get("pic") == "keep"
        if keep:
            raw = dict(raw, pic="")
        prof, picture = clean(raw)
        old = self._raw()
        same = (old.get("handle") or "").lower() == prof["handle"].lower()
        for k in ("verified", "verify"):
            if same and isinstance(old.get(k), dict):
                prof[k] = old[k]
        self._write(prof)
        if not keep:
            for f in self._pictures():
                if f.is_file():
                    f.unlink()
            if picture:
                (self.folder / f"profile.{picture[1]}").write_bytes(picture[0])
        return self.get()

    # -- verify on RSI
    def verify_start(self, now=None):
        """A code for the saved handle (the same one again while it's still valid)."""
        now = now or time.time()
        p = self._raw()
        h = p.get("handle") or ""
        if not HANDLE_RX.match(h):
            raise ValueError("Save your pilot card with your RSI handle first.")
        v = p.get("verify") if isinstance(p.get("verify"), dict) else None
        if not (v and v.get("handle", "").lower() == h.lower() and v.get("expires", 0) > now):
            v = {"handle": h, "code": new_code(), "expires": int(now + CODE_S)}
            p["verify"] = v
            self._write(p)
        return {"code": v["code"], "expires": v["expires"], "handle": h, "url": f"{RSI}/citizens/{h}"}

    def verify_check(self, now=None, fetch=_fetch):
        """Read the player's public RSI page and look for the code in the bio."""
        now = now or time.time()
        p = self._raw()
        v = p.get("verify") if isinstance(p.get("verify"), dict) else None
        if not v or v.get("handle", "").lower() != (p.get("handle") or "").lower():
            raise ValueError("Get a code first.")
        if v.get("expires", 0) <= now:
            raise ValueError("That code has run out (they last 30 minutes). Get a new one and swap it in your bio.")
        try:
            status, page = fetch(f"{RSI}/citizens/{urllib.request.quote(v['handle'])}")
        except Exception:  # noqa: BLE001 - any network failure gets the same plain answer
            raise ValueError("Couldn't reach robertsspaceindustries.com just now. Check your connection and try again.")
        if status == 404:
            raise ValueError(f"RSI has no citizen called {v['handle']}. Check the handle on your pilot card.")
        if status != 200:
            raise ValueError("RSI didn't answer properly just now. Try again in a minute.")
        bio = bio_from(page)
        if bio is None:
            raise ValueError("Couldn't find a bio on your RSI page. Add the code to your bio and save it on RSI first.")
        if v["code"] not in bio.upper():
            raise ValueError("The code isn't in your bio yet. RSI can take a minute to update after you save. Try Check again.")
        p["verified"] = {"handle": p["handle"], "at": int(now)}
        p.pop("verify", None)
        self._write(p)
        return {"verified": p["verified"]}

    def verify_cancel(self):
        p = self._raw()
        if p.pop("verify", None) is not None:
            self._write(p)
        return {"ok": True}
