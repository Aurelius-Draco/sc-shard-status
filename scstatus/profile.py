"""My pilot: your profile card. Kept in the data folder next to config.json and never sent anywhere.

profile.json holds the fields; the picture is saved beside it as profile.png, .jpg, .webp or .gif. The dashboard
hands the picture back to the page as a data URL, so nothing outside this PC ever sees it.
"""

import base64
import json
import re

from .config import DATA

FIELDS_TEXT = {"handle": 30, "org": 40, "region": 20, "times": 40, "bio": 200, "fav": 40}
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

    def save(self, raw):
        """Save the card. A missing or empty picture keeps none; "keep" leaves the saved one as it is."""
        keep = isinstance(raw, dict) and raw.get("pic") == "keep"
        if keep:
            raw = dict(raw, pic="")
        prof, picture = clean(raw)
        self.folder.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(prof, indent=1), encoding="utf-8")
        tmp.replace(self.path)
        if not keep:
            for f in self._pictures():
                if f.is_file():
                    f.unlink()
            if picture:
                (self.folder / f"profile.{picture[1]}").write_bytes(picture[0])
        return self.get()
