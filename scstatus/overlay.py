"""Reading the game's debug overlay (r_displayinfo 3) with OCR.

parse_lines(lines)      OCR text lines -> Snapshot dict (pure, no OCR needed)
OverlayReader().read()  finds the overlay block in the top right of a frame,
                        reads only the lines we use, and parses them.

The "Session: <guid>" line is never read in full, never parsed and never kept.
"""

import re
import threading
import time
import unicodedata

import cv2
import numpy as np

# --------------------------------------------------------------------------
# Snapshot fields
# --------------------------------------------------------------------------

FIELDS = (
    "shard_id", "server_name",
    "server_fps", "server_fps_min", "server_fps_max",
    "server_ms", "server_ms_min", "server_ms_max",
    "hitches", "restarts", "pop_shard", "pop_srv",
    "ping_ms", "loss_pct", "bw_in_kbps", "bw_out_kbps",
    "rl_entities", "rl_tick_ms", "rl_mtsync_ms",
    "client_fps", "client_fps_min", "client_fps_max", "client_ms",
    "vram_used_mb", "vram_total_mb",
    "location", "server_time",
    # 1.5.0: what else the overlay shows. The zone you're in (a ship's class, or a room), the planet, the tracked
    # mission's internal name, and how long the CPU and GPU take per frame. Never positions, entity numbers or the
    # mission's id: the parsers keep the name only.
    "zone", "planet", "mission", "render_mt_ms", "render_rt_ms", "render_gpu_ms",
)

INT_FIELDS = {"hitches", "restarts", "pop_shard", "pop_srv", "rl_entities",
              "vram_used_mb", "vram_total_mb"}

# Plausible ranges; anything outside is treated as a misread and dropped.
LIMITS = {
    "server_fps": (0.1, 1000), "server_fps_min": (0, 1000), "server_fps_max": (0, 1000),
    "server_ms": (0.1, 60000), "server_ms_min": (0, 60000), "server_ms_max": (0, 60000),
    "hitches": (0, 10_000_000), "restarts": (0, 100_000),
    # a shard holds hundreds, a game server well under 600: past that it's a misread (4,517 for 451)
    "pop_shard": (0, 1_500), "pop_srv": (0, 600),
    "ping_ms": (0, 60000), "loss_pct": (0, 100),
    "bw_in_kbps": (0, 10_000_000), "bw_out_kbps": (0, 10_000_000),
    "rl_entities": (0, 100_000_000), "rl_tick_ms": (0, 100_000), "rl_mtsync_ms": (0, 100_000),
    "client_fps": (0.1, 5000), "client_fps_min": (0, 5000), "client_fps_max": (0, 5000),
    "client_ms": (0.01, 60000),
    "vram_used_mb": (0, 1_000_000), "vram_total_mb": (1, 1_000_000),
    "render_mt_ms": (0, 5000), "render_rt_ms": (0, 5000), "render_gpu_ms": (0, 5000),
}
TEXT_FIELDS = {"zone", "planet", "mission"}

# --------------------------------------------------------------------------
# Line labels. Matched at the start of a line, case-insensitive, tolerant of
# the usual OCR slips (e/3, I/l/1, missing or doubled spaces, odd punctuation).
# --------------------------------------------------------------------------

_SERVER = r"[s5]\s?[e3c]\s?r\s?v\s?[e3c]\s?r"
LABELS = [
    ("session", r"[s5]\s?[e3c]\s?[s5]\s?[s5]?\s?[i1l|!]\s?[o0]\s?n\b\s*[:;.,]?"),
    ("shard", r"[s5]\s?h\s?a\s?r\s?d\s?[i1l|!]\s?[dD]\s*[:;.,]?"),
    ("server_fps", _SERVER + r"\s*f\s?p\s?[s5]"),
    ("server_time", _SERVER + r"\s*t\s?[i1l|!]\s?[mn]\s?[e3c]\s*[:;.,]?"),
    ("server", _SERVER + r"(?:\s*[:;.,]|\s+(?=p[uv]b|ptu|eptu|tech))"),
    ("net", r"n\s?[e3c]\s?t\s*(?:[:;.,]|(?=p\s?[i1l|]\s?n))"),
    ("rl", r"r\s?[l1i|]\s*(?:[:;.,]\s*|\s+)(?=[e3c]\s?n)"),
    ("vram", r"v\s?r\s?a\s?m\s*[(\[{<]?\s*m\s?b\s*[)\]}>]?\s*[:;.,]?"),
    # "Current player location :" (the search only sees "Current pla...")
    ("location", r"(?:c\s?u\s?r\s?r?\s?[e3c]?\s?n\s?t\s*p\s?[l1i|]\s?a"
                 r"(?:\s?y\s?[e3c]?\s?r\s*(?:[l1i|]\s?[o0]\s?c\s?a\s?t\s?[i1l|]\s?[o0]\s?n)?)?"
                 r"|p\s?[l1i|]\s?a\s?y\s?[e3c]\s?r\s*[l1i|]\s?[o0]\s?c\s?a\s?t\s?[i1l|]\s?[o0]\s?n)"
                 r"\s*[:;.,]?"),
    ("fps", r"f\s?p\s?[s5](?=\s*[\dOo])"),
    # 1.5.0 lines: "Render: MT: 12.7ms RT: 3.9ms GPU: 15.4ms", "Tracked mission : InterSec_Bounty_Nyx_Intro [<id>]",
    # "Zone: RSI_Constellation_Mk5_Centaurus 8748... Pos: ...", "No Current Planet" or "Planet:<name> ..."
    ("render", r"r\s?[e3c]\s?n\s?d\s?[e3c]\s?r\s*[:;.,]"),
    ("mission", r"t\s?r\s?a\s?c\s?k\s?[e3c]\s?d\s*m\s?[i1l|]\s?[s5]\s?[s5]\s?[i1l|]\s?[o0]\s?n\s*[:;.,]?"),
    ("zone", r"z\s?[o0]\s?n\s?[e3c]\s*[:;.,]"),
    ("no_planet", r"n\s?[o0]\s*c\s?u\s?r\s?r\s?[e3c]\s?n\s?t\s*p\s?[l1i|]\s?a\s?n\s?[e3c]\s?t"),
    ("planet", r"p\s?[l1i|]\s?a\s?n\s?[e3c]\s?t\s*[:;.,]"),
]
LABELS = [(k, re.compile(r"^[^A-Za-z0-9]{0,3}" + p, re.I)) for k, p in LABELS]

GUID_RE = re.compile(r"[0-9A-Fa-f]{8}(?:-[0-9A-Fa-f]{4}){3}-[0-9A-Fa-f]{12}")

_PUNCT = str.maketrans({
    "…": "..", "‥": "..", "【": "[", "】": "]", "「": "[", "」": "]", "〔": "[", "〕": "]",
    "—": "-", "–": "-", "−": "-", "‐": "-", "·": ".", "。": ".", "、": ",",
})


def classify(text):
    """Which overlay line this is: (key, rest of line) or (None, text)."""
    t = _clean(text)
    for key, rx in LABELS:
        m = rx.match(t)
        if m:
            return key, t[m.end():]
    return None, t


def _clean(text):
    t = unicodedata.normalize("NFKC", str(text)).translate(_PUNCT)
    return GUID_RE.sub(" ", t).strip()


# --------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------

_CONF0 = "OoDQ"
_CONF1 = "Il|!"
_NUMISH = re.compile(r"(?<![A-Za-z])[0-9OoDQIl|!][0-9OoDQIl|!.,]*")


_SPLIT_DEC = re.compile(r"(\d)\.\s+(\d+\s*(?:ms|%))")      # "110. 9ms": a space read after the point
_SPLIT_DEC2 = re.compile(r"(\d)\s+\.\s?(\d)")              # "113 . 2ms", "113 .2ms"


def fix_digits(s):
    """Turn O/o/D/Q into 0 and I/l/|/! into 1 where they sit in a number, and close up a decimal point the OCR
    split with a space."""
    s = _SPLIT_DEC2.sub(r"\1.\2", _SPLIT_DEC.sub(r"\1.\2", s))
    def repl(m):
        tok = m.group(0)
        core = tok.rstrip(".,")
        nxt = s[m.start() + len(core):m.start() + len(core) + 1]
        if any(c.isdigit() for c in core):
            pass
        elif core and all(c in "Oo0.," for c in core) and not nxt.isalpha():
            pass                                    # "O", "O.O" standing alone = zero
        elif core and all(c in "Il|!" for c in core) and len(core) <= 2 and not nxt.isalpha():
            pass                                    # "l" standing alone = one
        else:
            return tok
        out = []
        for c in tok:
            if c in _CONF0:
                out.append("0")
            elif c in _CONF1:
                out.append("1")
            else:
                out.append(c)
        return "".join(out)
    return _NUMISH.sub(repl, s)


_TOK = re.compile(r"\d+(?:[.,]\d+)?")


def num_tokens(s):
    return _TOK.findall(fix_digits(s))


def _conv(tok, dp):
    """Convert one numeric token, knowing how many decimals the game prints."""
    tok = tok.replace(",", ".")
    whole, _, frac = tok.partition(".")
    if dp == 0:
        return int(whole) if whole else None
    if not frac:
        if len(whole) <= dp:                        # dot lost: "218" -> 21.8
            return None
        whole, frac = whole[:-dp], whole[-dp:]
    elif len(frac) == dp + 1 and frac.endswith("1"):
        frac = frac[:-1]                            # "]" read as "1": 22.31 -> 22.3
    return float(f"{whole or '0'}.{frac}")


def fit_numbers(tokens, dps):
    """Assign numeric tokens to slots in order. When there are fewer tokens
    than slots, a token like '72.144' in an integer slot is a range whose '..'
    was read as '.', so it is split."""
    toks = list(tokens)
    out = [None] * len(dps)
    i = j = 0
    while i < len(toks) and j < len(dps):
        t, d = toks[i], dps[j]
        if d == 0 and re.search(r"[.,]", t) and (len(toks) - i) < (len(dps) - j):
            a, b = re.split(r"[.,]", t, maxsplit=1)
            out[j] = int(a) if a else None
            toks[i] = b
            j += 1
            continue
        try:
            out[j] = _conv(t, d)
        except ValueError:
            out[j] = None
        i += 1
        j += 1
    exact = len(toks) == len(dps) or (i == len(toks) and j == len(dps))
    return out, exact


def _kw_number(s, kw, dp):
    m = re.search(kw + r"[^0-9]{0,6}?(\d+(?:[.,]\d+)?)", fix_digits(s), re.I)
    if not m:
        return None
    try:
        return _conv(m.group(1), dp)
    except ValueError:
        return None


def _assign(out, rest, slots):
    """slots: list of (field, decimals, keyword regex or None)."""
    vals, exact = fit_numbers(num_tokens(rest), [d for _, d, _ in slots])
    for (field, dp, kw), v in zip(slots, vals):
        if not exact and kw:
            v = _kw_number(rest, kw, dp)     # positions can't be trusted; go by the keyword
        if field and out.get(field) is None:
            out[field] = v


# --------------------------------------------------------------------------
# Per-line parsers
# --------------------------------------------------------------------------

def _p_fps(out, rest):
    # "106.3 [72..144], - 10.3ms [7.1ms]"
    _assign(out, rest, [("client_fps", 1, None), ("client_fps_min", 0, None),
                        ("client_fps_max", 0, None), ("client_ms", 1, None), (None, 1, None)])


def _p_server_fps(out, rest):
    # "21.8 [21.2..22.3] - 45.9ms [44.8..47.3], Hitches: 0"
    _assign(out, rest, [("server_fps", 1, None), ("server_fps_min", 1, None),
                        ("server_fps_max", 1, None), ("server_ms", 1, None),
                        ("server_ms_min", 1, None), ("server_ms_max", 1, None),
                        ("hitches", 0, r"h\w{1,5}s\b")])


def _p_net(out, rest):
    # "ping 24.4ms, loss 0.0% BwIn 222.221kbps, BwOut 50.556kbps"
    _assign(out, rest, [("ping_ms", 1, r"p\s?[i1l|]\s?n\s?[gq9]"),
                        ("loss_pct", 1, r"[l1|I]\s?[o0]\s?s\s?s"),
                        ("bw_in_kbps", 3, r"b\s?w\s?[i1l|]\s?n"),
                        ("bw_out_kbps", 3, r"b\s?w\s?[o0]\s?u?\s?t")])


def _p_rl(out, rest):
    # "entities: 17295, tick: 0.26ms, MTSync: 0.97ms"
    _assign(out, rest, [("rl_entities", 0, r"[e3]\s?n\s?t\w*"),
                        ("rl_tick_ms", 2, r"t\s?[i1l|]\s?c\s?k"),
                        ("rl_mtsync_ms", 2, r"s\s?y\s?n\s?c")])


def _p_vram(out, rest):
    # "9250 / 15423"
    _assign(out, rest, [("vram_used_mb", 0, None), ("vram_total_mb", 0, None)])


_RESTARTS = re.compile(r"[,;.]?\s*r\s?[e3]\s?s\s?t\s?a\s?r\s?t", re.I)


def _p_server(out, rest):
    # "pub-apse2a-sc-alpha-4102-12974691-game-07, restarts 0, pop. [shard 435, srv 34]"
    m = _RESTARTS.search(rest)
    if m:
        name, tail = rest[:m.start()], rest[m.start():]
    else:
        parts = rest.strip().split(None, 1)
        name, tail = (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else "")
    if not out.get("server_name"):
        out["server_name"] = norm_server_name(name)
        out["_server_unsure"] = bool(out["server_name"]) and not server_name_sure(name)
    _assign(out, tail, [("restarts", 0, r"r\s?[e3]\s?s\s?t\w*"),
                        ("pop_shard", 0, r"s\s?h\s?a\s?r\s?d"),
                        ("pop_srv", 0, r"s\s?r\s?v")])


_NAME_WORDS = ("pub", "ptu", "eptu", "tech", "alpha", "game", "hub")


def norm_server_name(s):
    s = re.sub(r"\s+", "", s.translate(_PUNCT)).strip(",.;:[]()").replace("_", "-").lower()
    s = re.sub(r"-{2,}", "-", s)
    segs = []
    for seg in s.split("-"):
        if sum(c.isdigit() for c in seg) * 2 >= len(seg):      # mostly digits: fix O/l
            seg = seg.translate(str.maketrans("oDdqil|!", "00001111"))
        elif seg not in _NAME_WORDS:                            # "gane" -> "game"
            for w in _NAME_WORDS:
                if len(w) == len(seg) >= 3 and sum(x != y for x, y in zip(w, seg)) == 1:
                    seg = w
                    break
        # The region is letters, one digit, a letter ("use1b", "apse2a"): a 1 read as l or i there ("uselb", PTU 7 Nov)
        if len(segs) == 1 and (r := re.fullmatch(r"([a-z]{2,5})[li|!]([a-z])", seg)):
            seg = f"{r.group(1)}1{r.group(2)}"
        segs.append(seg)
    # The last part is the game server's number: "game190" is "game-190"; letters there ("13y", "alerver") mean a misread
    if segs and re.fullmatch(r"game\d{1,4}", segs[-1]):
        segs[-1:] = ["game", segs[-1][4:]]
    s = "-".join(segs)
    if "alph" in s and not _SERVER_CAN.fullmatch(s):
        # The usual shape (env-region-sc-alpha-version-build-game-N) with a dash dropped or misread, or a stray
        # letter ("alphal4102", "scalpha", "sg-alpha", "13132336game-09"): put back in shape, or None when it can't be
        m = _SERVER_TOL.fullmatch(s)
        if not m:
            return None
        env, a, d, b, ver, build, node = m.groups()
        return f"{env}-{a}{d if d.isdigit() else '1'}{b}-sc-alpha-{ver}-{build}-game-{node}"
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+){3,}", s) or not re.fullmatch(r"\d{1,4}", segs[-1]):
        return None
    return s


_SERVER_CAN = re.compile(r"[a-z]{2,5}-[a-z]{2,6}\d[a-z]?-sc-alpha-\d{3,4}-\d{7,8}-game-\d{1,4}")
_SERVER_TOL = re.compile(r"([a-z]{2,5})-([a-z]{2,6})([0-9li|!])([a-z]?)[a-z]?-?s?[cgo]?[a-z]?-?alpha[a-z]?-?(\d{3,4})-?"
                         r"(\d{7,8})\d?-?gam+e[a-z]?-?(\d{1,4})")


def server_name_sure(raw):
    """False when the region's digit had to be guessed from a letter with the segments run together
    ("uselpsc-alpha": use1b or use1p?). Such a name is only kept when the shard id's region agrees."""
    s = re.sub(r"\s+", "", raw.translate(_PUNCT)).strip(",.;:[]()").replace("_", "-").lower()
    segs = re.sub(r"-{2,}", "-", s).split("-")
    if len(segs) > 2 and re.fullmatch(r"[a-z]{2,6}\d[a-z]?|[a-z]{2,5}[li|!][a-z]", segs[1]) and segs[2] in ("sc", "sg", "so"):
        return True
    m = _SERVER_TOL.fullmatch(re.sub(r"-{2,}", "-", s))
    return bool(m) and m.group(3).isdigit()


def node_of(server_name):
    """The game server's number from its name ("pub-apse2a-...-game-07" -> "07"), or None when it isn't digits."""
    last = str(server_name or "").rsplit("-", 1)[-1].strip()
    m = re.fullmatch(r"(?:game)?(\d{1,4})", last)
    return m.group(1) if m else None


_ENVS = r"(?:pub|ptu|eptu|tech\w*|evo\w*|[a-z]{2,6})"
# The build part is 7 or 8 digits: pub_apse2a_12881_860 is a misread, not a shard
_SHARD_RE = re.compile(r"(" + _ENVS + r")_?([a-z]{2,8}\d{1,2}[a-z]?)_?(\d{7,8})_?(\d{3})")


def norm_shard_id(s):
    """'pub apse2a 12881860 090' (any mix of spaces, underscores, dashes,
    or none at all) -> 'pub_apse2a_12881860_090'."""
    t = s.translate(_PUNCT).strip().lower()
    t = re.sub(r"[\s_\-.,:;]+", "_", t).strip("_")
    parts = t.split("_")
    if len(parts) >= 4:
        env, reg = parts[0], parts[1]
        if r := re.fullmatch(r"([a-z]{2,5})[li|!]([a-z])", reg):      # "uselb": the region's digit read as l
            reg = f"{r.group(1)}1{r.group(2)}"
        rest = "_".join(parts[2:]).translate(str.maketrans("oDdqil|!", "00001111"))
        t = f"{env}_{reg}_{rest}"
    else:
        # fix digits only in the numeric tail so 'apse2a' stays intact
        m = re.search(r"[0-9oil|!]{6,}$", t)
        if m:
            t = t[:m.start()] + m.group(0).translate(str.maketrans("oil|!", "01111"))
    m = _SHARD_RE.match(t)
    if not m:
        return None
    return "_".join(m.groups())


_DOW = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MON = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_TIME_RE = re.compile(
    r"([A-Za-z0-9]{3})\W*([A-Za-z0-9]{3})\W*(\d{1,2})\s*(\d{1,2})\s*[:;.]\s*(\d{2})\s*[:;.]\s*(\d{2})\s*(\d{4})")


def _closest(word, choices):
    w = word.translate(str.maketrans("015", "OlS")).lower()
    best, score = None, 0
    for c in choices:
        sc = sum(a == b for a, b in zip(w, c.lower()))
        if sc > score:
            best, score = c, sc
    return best if score >= 2 else None


def norm_server_time(s):
    t = s.translate(_PUNCT).strip()
    # digits only after the month name, so 'Oct' isn't touched
    m = re.match(r"\s*([A-Za-z0-9]{3})\W*([A-Za-z0-9]{3})(.*)$", t)
    if not m:
        return None
    t = f"{m.group(1)} {m.group(2)} {fix_digits(m.group(3))}"
    m = _TIME_RE.search(t)
    if not m:
        return None
    dow, mon = _closest(m.group(1), _DOW), _closest(m.group(2), _MON)
    day, hh, mm, ss, yr = (int(m.group(i)) for i in range(3, 8))
    if not (dow and mon and 1 <= day <= 31 and hh < 24 and mm < 60 and ss < 61 and 2000 < yr < 2100):
        return None
    return f"{dow} {mon} {day} {hh:02d}:{mm:02d}:{ss:02d} {yr}"


def _p_location(out, rest):
    # "RR_CRU_L4  (LZ : RR_CRU_L4)"
    main, _, lz = rest.partition("(")
    if not lz:
        mm = re.search(r"\bL\s?Z\s*[:;]", main)
        if mm:
            main, lz = main[:mm.start()], main[mm.start():]

    def name(x):
        x = re.sub(r"^\W*(?:L\s?Z\s*[:;.,]?)?", "", x.strip())
        x = re.sub(r"\s+", "_", x.strip(" :;.,)]"))
        x = re.sub(r"[^A-Za-z0-9_\-]", "", x)
        return x or None
    out["location"] = out.get("location") or name(main) or name(lz)


def _p_shard(out, rest):
    out["shard_id"] = out.get("shard_id") or norm_shard_id(rest)


def _p_server_time(out, rest):
    out["server_time"] = out.get("server_time") or norm_server_time(rest)


_NAME_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{2,80}")


def _name(rest):
    """The name at the start of a line (letters, digits, underscores), stopping at an id (5 or more digits), a
    bracket or "Pos": never an id or a position. OCR often reads underscores as spaces, so parts are joined back."""
    parts = []
    text = re.split(r"[\[({<]", _clean(rest), maxsplit=1)[0]          # nothing from a bracket on (ids)
    for tok in text.replace(" _", "_").replace("_ ", "_").split():
        tok = tok.strip(":;,.")
        if not tok:
            if parts:
                break
            continue
        if re.fullmatch(r"\d{5,}", tok) or re.match(r"p[o0]s\b", tok, re.I):
            break
        if not re.fullmatch(r"[A-Za-z0-9_\-]+", tok):
            break
        parts.append(tok)
        if len(parts) >= 8:
            break
    name = re.sub(r"_\d{5,}$", "", "_".join(parts)).strip("_-")      # DRAK_Corsair_874827277606: no entity id
    return name if _NAME_TOKEN.fullmatch(name or "") else None


def _p_zone(out, rest):
    # The first Zone line is where you are (a ship's class or a room); the SolarSystem and Root ones are positions
    if out.get("zone") is not None or re.match(r"\W*(?:s\s?[o0]\s?[l1i|]\s?a\s?r|r\s?[o0]\s?[o0]\s?t)", rest, re.I):
        return
    out["zone"] = _name(rest)


def _p_mission(out, rest):
    out["mission"] = out.get("mission") or _name(GUID_RE.sub("", rest))


def _p_planet(out, rest):
    # "Planet:<name> <type> (<zone>)": the first word is the planet's name. On 4.10.3 it's the object container's
    # id ("Planet:OOC_Stanton_3_ArcCorp  (Load Complete)", OOC often read as 00C): the planet is its last part
    text = re.split(r"[\[({<]", _clean(rest), maxsplit=1)[0].strip(" :;,.")
    m = re.match(r"[O0o][O0o]C[\s_]+(.+)$", text)
    if m:
        name = _name(m.group(1))
        name = name.split("_")[-1] if name else None
    else:
        name = _name((text.split() or [""])[0])
    out["planet"] = out.get("planet") or name


def _p_no_planet(out, rest):
    if out.get("planet") is None:
        out["planet"] = ""          # read, and not on a planet


def _p_render(out, rest):
    _assign(out, rest, [("render_mt_ms", 1, r"m\s?t"), ("render_rt_ms", 1, r"r\s?t"), ("render_gpu_ms", 1, r"g\s?p\s?u")])


PARSERS = {
    "fps": _p_fps, "shard": _p_shard, "server_fps": _p_server_fps,
    "server": _p_server, "net": _p_net, "rl": _p_rl, "server_time": _p_server_time,
    "vram": _p_vram, "location": _p_location,
    "zone": _p_zone, "mission": _p_mission, "planet": _p_planet, "no_planet": _p_no_planet, "render": _p_render,
}


def _fps_agrees(fps, ms):
    """Server fps and its frame time are the same number two ways (30 fps is 33.3 ms), to the rounding."""
    if fps is None or ms is None or fps <= 0 or ms <= 0:
        return False
    return abs(1000.0 / fps - ms) <= max(0.6, 0.03 * ms)


def _within(v, lo, hi):
    return v is not None and (lo is None or v >= lo - 0.05) and (hi is None or v <= hi + 0.05) and (lo is not None or hi is not None)


def _fps_ms_check(out):
    """When the server fps and its frame time disagree, one was misread (LAB, 7 Nov: 57 of 1,845 readings, e.g.
    50.0 fps with 33.3 ms, or 30.0 fps with 3.3 ms). Keep the half that fits its own range and work the other out
    from it; if neither can be trusted, drop both rather than show a wrong number."""
    fps, ms = out.get("server_fps"), out.get("server_ms")
    if fps is None or ms is None or _fps_agrees(fps, ms):
        return
    ms_ok = _within(ms, out.get("server_ms_min"), out.get("server_ms_max"))
    fps_ok = _within(fps, out.get("server_fps_min"), out.get("server_fps_max"))
    from_ms = round(1000.0 / ms, 1)
    from_fps = round(1000.0 / fps, 1)
    if ms_ok and (not fps_ok or _within(from_ms, out.get("server_fps_min"), out.get("server_fps_max"))):
        out["server_fps"] = from_ms
    elif fps_ok and _within(from_fps, out.get("server_ms_min"), out.get("server_ms_max")):
        out["server_ms"] = from_fps
    elif fps_ok and not ms_ok:
        out["server_ms"] = from_fps
    else:
        out["server_fps"] = out["server_ms"] = None


def _sanity(out):
    # A game server is part of its shard, so fewer on the shard than on the server is a misread shard count
    # (a pop-up over "shard 427" read as 3, LIVE 8 Nov)
    if out.get("pop_shard") is not None and out.get("pop_srv") is not None and out["pop_shard"] < out["pop_srv"]:
        out["pop_shard"] = None
    # A server name whose region had to be guessed stays only when the shard id's region agrees
    if out.pop("_server_unsure", False) and out.get("server_name"):
        sh = out.get("shard_id") or ""
        if sh.split("_")[1:2] != out["server_name"].split("-")[1:2]:
            out["server_name"] = None
    for f, (lo, hi) in LIMITS.items():
        v = out.get(f)
        if v is not None and not (lo <= v <= hi):
            out[f] = None

    def fix_range(v_key, lo_key, hi_key):
        v, lo, hi = out.get(v_key), out.get(lo_key), out.get(hi_key)
        if v is None:
            return
        # "[" read as "1": 121.2 for 21.2
        if lo is not None and lo > v:
            s = repr(lo) if isinstance(lo, float) else str(lo)
            if s.startswith("1") and len(s) > 1:
                try:
                    cand = type(lo)(s[1:])
                except ValueError:
                    cand = None
                out[lo_key] = cand if cand is not None and cand <= v else None
            else:
                out[lo_key] = None
        if hi is not None and hi < v:
            out[hi_key] = None
        if (out.get(lo_key) is not None and out.get(hi_key) is not None
                and out[lo_key] > out[hi_key]):
            out[lo_key] = out[hi_key] = None

    fix_range("server_fps", "server_fps_min", "server_fps_max")
    fix_range("server_ms", "server_ms_min", "server_ms_max")
    fix_range("client_fps", "client_fps_min", "client_fps_max")
    _fps_ms_check(out)
    u, t = out.get("vram_used_mb"), out.get("vram_total_mb")
    if u is not None and t is not None and u > t:
        out["vram_used_mb"] = out["vram_total_mb"] = None
    for f in INT_FIELDS:
        if out.get(f) is not None:
            out[f] = int(out[f])


def _parse(lines):
    out = dict.fromkeys(FIELDS)
    seen = set()
    for line in lines:
        if not line:
            continue
        key, rest = classify(line)
        if key is None or key == "session":
            continue                    # never parse or keep the Session line
        before = sum(v is not None for v in out.values())
        try:
            PARSERS[key](out, rest)
        except Exception:
            continue
        if sum(v is not None for v in out.values()) > before:
            seen.add(key)               # the line gave us at least one value
    _sanity(out)
    out["ok"] = bool(out["server_fps"] is not None and (
        out["pop_shard"] is not None or out["pop_srv"] is not None or out["ping_ms"] is not None))
    return out, seen


def parse_lines(lines):
    """Parse overlay text lines (as OCR gives them) into a Snapshot dict
    without 'ts'. Fields that can't be read are None. 'ok' is True when at
    least server FPS and one of population or ping were read."""
    return _parse(lines)[0]


# --------------------------------------------------------------------------
# Finding and reading the block on screen
# --------------------------------------------------------------------------

REF_H = 2160            # sizes below are measured on a 4K frame
REF_PITCH = 19.3        # overlay line pitch at 4K, px
DET_SCALE = 0.6         # detector runs at this scale of a 4K frame (text ~10 px high)
# For a game drawing at 4K (overlay line pitch near REF_PITCH), the detector runs a quarter finer. The LAB (Nov 2026)
# found it found the block 99% of the time on 4.10.3 against 85%, in half the time, and was never worse on 4.10.2.
# Below 4K the evidence is thin, so smaller text keeps the old scale.
DET_SCALE_4K = 0.75


ALT_COARSER = 0.75      # when the block isn't found, one more try with the detector at this share of the scale...
ALT_FINER = 1.25        # ...or finer, whichever the first try wasn't (LAB, 4.10.3 PTU: 79% to 98% of readable frames)
ALT_RECENT_FAILS = 3    # the second try runs while the overlay was there a few readings ago, and now and then


def det_scale(game_h):
    """The detector scale for a game drawn at this height."""
    return DET_SCALE_4K if (game_h or 0) >= 1900 else DET_SCALE
WANTED = ("fps", "shard", "server_fps", "server", "net", "rl", "server_time", "vram", "location")
# 1.5.0 extras: read now and then from around the block, best effort. They never decide where the block is or
# whether a reading worked (a mission line comes and goes, the planet line changes), so the core reading is untouched.
EXTRA_KEYS = ("zone", "render", "mission", "planet", "no_planet")
EXTRA_FIELDS = ("zone", "planet", "mission", "render_mt_ms", "render_rt_ms", "render_gpu_ms")
EXTRA_EVERY = 6          # read the extras every this many good readings
EXTRA_KEEP_S = 90        # and keep the last ones this long
EXTRA_RESCAN = 10        # look for where the extra lines are every this many extra reads
ANCHORS = set(WANTED) | {"session"}
# What each core line gives, to see when a line was read but came out short (a banner or pop-up across it)
ROW_FIELDS = {"fps": ("client_fps",), "shard": ("shard_id",), "server_fps": ("server_fps", "server_ms", "hitches"),
              "server": ("server_name", "pop_shard", "pop_srv"), "net": ("ping_ms", "loss_pct"), "rl": (),
              "server_time": ("server_time",), "vram": ("vram_used_mb",), "location": ("location",)}
# The values a second look may fill in (see OverlayReader._ink_look)
# Not the shard id: a pop-up glyph over its last part reads as another valid-looking shard (LAB 8 Nov: 010 as 610);
# the session QR code and Game.log give it instead
INK_FIELDS = {"fps": ("client_fps",), "server_fps": ("server_fps", "server_ms"),
              "server": ("server_name", "pop_shard", "pop_srv"), "net": ("ping_ms", "loss_pct"),
              "server_time": ("server_time",), "vram": ("vram_used_mb",)}


def _this_year(t):
    m = re.search(r"(\d{4})\s*$", t or "")
    return bool(m) and abs(int(m.group(1)) - time.gmtime().tm_year) <= 1


# The overlay draws its text untinted in white, yellow and orange (red for bad numbers), each glyph with a black drop
# shadow a pixel or two right of and below it. The ship name banner, mission pop-ups, name tags and the HUD are tinted
# (cyan, blue, green) and have no such shadow, so keeping only overlay-coloured pixels with a shadow drops them out.
INK_COLOURS = ((1.0, 1.0, 1.0), (1.0, 0.966, 0.586), (1.0, 0.645, 0.0))     # r, g, b as shares of the brightest


def ink_mask(bgr, strict=False):
    """Pixels that look like the overlay's own text: an overlay colour at some brightness, with a dark pixel 1 to 3
    px down and to the right (the drop shadow). strict narrows the colours, for when the first look wasn't enough."""
    a = bgr.astype(np.float32)
    b, g, r = a[..., 0], a[..., 1], a[..., 2]
    mx = np.maximum(np.maximum(r, g), b)
    ok = np.zeros(mx.shape, bool)
    for k, (cr, cg, cb) in enumerate(INK_COLOURS):
        if k == 0:
            t = 2 + 0.03 * mx if strict else 6 + 0.06 * mx
        else:
            t = 5 + 0.06 * mx if strict else 10 + 0.12 * mx
        ok |= (np.abs(r - mx * cr) <= t) & (np.abs(g - mx * cg) <= t) & (np.abs(b - mx * cb) <= t)
    ok |= (r >= 120) & (g <= 0.35 * r) & (b <= 0.35 * r)
    ok &= mx >= (130 if strict else 100)
    dark = mx < 70
    near = np.zeros_like(ok)
    for d in (1, 2, 3):
        near[:-d, :-d] |= dark[d:, d:]
    return ok & near


def ink_only(bgr, strict=False):
    """bgr with everything but the overlay's own text blacked out."""
    # grow the glyphs' cores by a pixel so their soft edges come along (OCR reads anti-aliased text better)
    m = cv2.dilate(ink_mask(bgr, strict).astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    out = np.zeros_like(bgr)
    out[m] = bgr[m]
    return out
REUSE_MAX = 10          # re-read an unchanged line at least every this many reads
LINE_SQUEEZE = 0.85      # horizontal squeeze of line crops before OCR


def _box_rects(boxes, scale, ox, oy):
    out = []
    if boxes is None:
        return out
    for b in boxes:
        b = np.asarray(b, dtype=np.float32)
        out.append((b[:, 0].min() / scale + ox, b[:, 1].min() / scale + oy,
                    b[:, 0].max() / scale + ox, b[:, 1].max() / scale + oy))
    return out


def _segments(rects, pitch):
    """Group detector boxes into text rows (by vertical centre), then split
    each row where there is a wide horizontal gap (e.g. text vs the session
    QR code). Returns [(x0, y0, x1, y1)] sorted top to bottom."""
    if not rects:
        return []
    rs = sorted(rects, key=lambda r: (r[1] + r[3]) / 2)
    rows, prev = [], None
    for r in rs:
        cy = (r[1] + r[3]) / 2
        if prev is None or cy - prev > 0.42 * pitch:
            rows.append([])
        rows[-1].append(r)
        prev = cy
    segs = []
    for row in rows:
        row.sort(key=lambda r: r[0])
        cy = float(np.median([(r[1] + r[3]) / 2 for r in row]))
        cur = [row[0][0], row[0][2]]
        for r in row[1:]:
            if r[0] - cur[1] < 6 * pitch:
                cur[1] = max(cur[1], r[2])
            else:
                segs.append((cur[0], cy - pitch / 2, cur[1], cy + pitch / 2))
                cur = [r[0], r[2]]
        segs.append((cur[0], cy - pitch / 2, cur[1], cy + pitch / 2))
    return segs


def _pitch(segs, default):
    cys = sorted((s[1] + s[3]) / 2 for s in segs)
    d = [b - a for a, b in zip(cys, cys[1:]) if 0.6 * default < b - a < 1.5 * default]
    return float(np.median(d)) if len(d) >= 3 else default


class OverlayReader:
    """Reads the r_displayinfo block from full screen frames (BGR numpy arrays).

    The first read searches the top right of the screen; later reads reuse
    the block's last position and only search again when that stops working.
    Lines whose pixels haven't changed since the last read are not OCR'd again.
    """

    def __init__(self, engine=None, threads=None, wide_search_every=15.0):
        self._eng = engine
        self._threads = threads
        self._lock = threading.Lock()
        self._cache = None
        self._seen = {}              # key -> (mask, text, reuse count); never holds Session
        self._fails = 0
        self._last_wide = 0.0
        self.wide_search_every = wide_search_every
        self.last_path = None        # "fast", "search", "wide", "ink" or None (diagnostics)
        self.last_ink = []           # lines the last look at only the overlay's own text fixed (diagnostics)
        self._game_h = None          # the height the game draws at, once found (None: the screen's)
        self._extras = ({}, 0.0)     # the 1.5.0 extra lines (fields, when read)
        self._extra_n = 0
        self._last_alt = time.monotonic()     # smaller game sizes are first tried a little after start
        self._last_altscale = 0.0
        self.last_ms = None

    # ---- OCR engine -------------------------------------------------------

    def _engine(self):
        if self._eng is None:
            import logging
            logging.getLogger("RapidOCR").setLevel(logging.ERROR)
            from rapidocr import RapidOCR
            params = {
                "Global.log_level": "error",
                "Global.use_cls": False,
                "Global.use_preprocess_img": False,     # we choose the scale ourselves
                "Global.use_vertical_padding": False,
                "Det.limit_type": "max",
                "Det.limit_side_len": 4096,
                "Rec.rec_batch_num": 1,                 # no padding waste; faster on CPU
            }
            if self._threads:
                params["EngineConfig.onnxruntime.intra_op_num_threads"] = int(self._threads)
            self._eng = RapidOCR(params=params)
        return self._eng

    def _det(self, img, scale, ox=0, oy=0):
        if img.size == 0:
            return []
        small = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) \
            if abs(scale - 1) > 1e-3 else img
        try:
            r = self._engine()(small, use_det=True, use_cls=False, use_rec=False)
        except Exception:
            return []
        return _box_rects(getattr(r, "boxes", None), scale, ox, oy)

    def _rec(self, crops):
        if not crops:
            return []
        eng = self._engine()
        try:
            from rapidocr.ch_ppocr_rec import TextRecInput
            res = eng._load_rec_model()(TextRecInput(img=list(crops)))
            return [str(t).strip() for t in res.txts]
        except Exception:
            out = []
            for c in crops:
                try:
                    r = eng(c, use_det=False, use_cls=False, use_rec=True)
                    out.append((r.txts[0] if r.txts else "").strip())
                except Exception:
                    out.append("")
            return out

    @staticmethod
    def _line_crop(img, x0, cy, x1, pitch):
        """One overlay line, ready for the recogniser. The monospaced font is
        wide, so the crop is squeezed a little sideways: the recogniser's cost
        grows with width and it reads this font just as well (measured)."""
        H, W = img.shape[:2]
        c = img[max(0, int(cy - 0.7 * pitch)):min(H, int(np.ceil(cy + 0.7 * pitch))),
                max(0, int(x0 - 0.4 * pitch)):min(W, int(np.ceil(x1)))]
        if c.size == 0:
            return c
        f = min(3.0, 24.0 / pitch) if pitch < 16 else 1.0     # small text (1080p): upscale
        return cv2.resize(c, None, fx=f * LINE_SQUEEZE, fy=f,
                          interpolation=cv2.INTER_CUBIC if f > 1 else cv2.INTER_AREA)

    # ---- search -----------------------------------------------------------

    def _search(self, img, wide=False, game_h=None, alt=False):
        """Find the block: detect text in the top right, read the first few
        characters of each line and look for the overlay's line labels.

        game_h is the height the game draws at, when that's smaller than the
        screen (a 1440p game on a 4K monitor draws 1440p-sized text): the text
        size, and so the detection scale, follow the game, not the screen."""
        H, W = img.shape[:2]
        s_screen = H / REF_H
        s = (game_h or H) / REF_H
        if wide:
            rw, rh = int(W * 0.6), int(H * 0.7)
        else:
            rw, rh = int(min(W, 1500 * s_screen)), int(min(H, 800 * s_screen))
        ox = W - rw
        ds = float(np.clip(det_scale(game_h or H) / s, 0.25, 2.0))
        if alt:
            # the other text size: smaller frames whose text stays large read better coarser, and the reverse
            ds = float(np.clip(ds * (ALT_COARSER if ds > 0.7 else ALT_FINER), 0.25, 2.0))
        rects = self._det(img[0:rh, ox:W], ds, ox, 0)
        if len(rects) < 3:
            return None
        pitch0 = REF_PITCH * s
        segs = _segments(rects, pitch0)
        pitch = _pitch(segs, pitch0)
        if abs(pitch - pitch0) > 0.15 * pitch0:
            segs = _segments(rects, pitch)
        segs = [g for g in segs if g[2] - g[0] > 2.5 * pitch]
        found, keys = [], set()
        for g in segs:                         # top to bottom; stop once all are found
            cy = (g[1] + g[3]) / 2
            text = self._rec([self._line_crop(img, g[0], cy, min(g[2], g[0] + 7.5 * pitch), pitch)])[0]
            key, _ = classify(text)
            del text
            if key in ANCHORS and key not in keys:
                found.append((key, g))
                keys.add(key)
                if keys >= ANCHORS:
                    break
        if len(keys) < 3:
            return None
        # the block is right aligned: keep lines ending at the common right edge
        right = float(np.median([g[2] for _, g in found]))
        found = [(k, g) for k, g in found if abs(g[2] - right) < 2.0 * pitch]
        keys = {k for k, _ in found}
        if "server" not in keys and ox > 0 and len(keys) >= 3:
            g = self._left_strip(img, segs, found, right, pitch, ox, ds)
            if g is not None:
                found.append(("server", g))
                keys.add("server")
        if len(keys) < 3 or not (keys & {"server_fps", "net", "server"}):
            return None
        ys = [g[1] for _, g in found] + [g[3] for _, g in found]
        if max(ys) - min(ys) > 30 * pitch:
            return None
        rows = [(k, g[0], (g[1] + g[3]) / 2) for k, g in found if k in WANTED]   # drops Session
        x0 = min(r[1] for r in rows) - 5 * pitch
        rect = (max(0.0, x0), max(0.0, min(ys) - 1.2 * pitch),
                min(float(W), right + 1.5 * pitch), min(float(H), max(ys) + 1.2 * pitch))
        return {
            "shape": img.shape[:2], "rect": rect, "right": right, "pitch": pitch,
            "ds": float(np.clip(det_scale(REF_H * pitch / REF_PITCH) * REF_PITCH / pitch, 0.25, 2.0)),
            "rows": rows,
        }

    def _left_strip(self, img, segs, found, right, pitch, ox, ds):
        """The Server line can start left of the search area: on the 4.10.3 PTU at 1440p the overlay's text stays
        near its 4K size and the server name is long ("ptu-use1b-sc-alpha-4100-13132336-game-09"), so the line was
        cut off at the area's left edge and its label never read (7 Nov: all 46 of Ray's Print Screens). Widening
        the whole search cost good reads, so only the rows that run off the left edge, inside the block, get a
        second look at a strip to their left. Returns the Server row's segment, or None."""
        cys = [(g[1] + g[3]) / 2 for _, g in found]
        lo, hi = min(cys), max(cys)
        used = {id(g) for _, g in found}
        cands = [g for g in segs if id(g) not in used and abs(g[2] - right) < 2.0 * pitch
                 and g[0] <= ox + 1.0 * pitch and lo < (g[1] + g[3]) / 2 < hi][:3]
        H = img.shape[0]
        for g in cands:
            cy = (g[1] + g[3]) / 2
            y0, y1 = max(0, int(cy - 1.5 * pitch)), min(H, int(np.ceil(cy + 1.5 * pitch)))
            x0 = max(0, int(ox - 40 * pitch))
            rects = self._det(img[y0:y1, x0:int(ox + 3 * pitch)], ds, x0, y0)
            row = [r for r in _segments(rects, pitch)
                   if abs((r[1] + r[3]) / 2 - cy) < 0.45 * pitch and r[2] >= ox - 1.0 * pitch]
            if not row:
                continue
            start = min(r[0] for r in row)
            if start >= g[0] - 0.5 * pitch:
                continue
            text = self._rec([self._line_crop(img, start, cy, min(g[2], start + 7.5 * pitch), pitch)])[0]
            if classify(text)[0] == "server":
                return (start, g[1], g[2], g[3])
        return None

    # ---- reading lines ----------------------------------------------------

    def _mask(self, img, blk, cy):
        """Bright-pixel mask of a line at a fixed position, to spot lines that
        haven't changed since the last read."""
        p = blk["pitch"]
        x0 = blk["rect"][0]
        c = img[max(0, int(cy - 0.55 * p)):int(cy + 0.55 * p),
                int(x0):int(blk["right"] + 0.5 * p)]
        if c.size == 0:
            return None
        m = c.max(axis=2) > 150
        fill = m.mean()
        return m if 0.01 < fill < 0.45 else None

    def _read_rows(self, img, blk, rows):
        """rows: [(key, x0, cy)]. OCR each line (or reuse the last text if its
        pixels are unchanged) and parse. Returns (snapshot, every line OCR'd
        this time still starts with the label expected at its position)."""
        p, right = blk["pitch"], blk["right"]
        texts, todo, masks = {}, [], {}
        for key, x0, cy in rows:
            m = self._mask(img, blk, cy)
            masks[key] = m
            old = self._seen.get(key)
            if (m is not None and old is not None and old[0] is not None and old[0].shape == m.shape
                    and old[2] < REUSE_MAX
                    and np.count_nonzero(old[0] != m) <= max(1, int(0.1 * p))):
                texts[key] = old[1]
                self._seen[key] = (old[0], old[1], old[2] + 1)
            else:
                todo.append((key, x0, cy))
        got = self._rec([self._line_crop(img, x0, cy, right + 0.6 * p, p) for _, x0, cy in todo])
        labels_ok = True
        for (key, _, _), t in zip(todo, got):
            texts[key] = t
            labels_ok = labels_ok and classify(t)[0] == key
        snap, seen = _parse([texts[k] for k, _, _ in rows])
        fixed = self._ink_look(img, blk, rows, texts, snap)
        self.last_ink = sorted(fixed)
        for key, _, _ in todo:
            if key in seen:
                self._seen[key] = (masks[key], texts[key], 0)
            else:
                self._seen.pop(key, None)
        return snap, labels_ok

    def _ink_look(self, img, blk, rows, texts, snap):
        """Values a line should have given but didn't (a banner or pop-up across it) get a second look with only the
        overlay's own text kept (ink_only), then a stricter third. Only missing values are filled, never ones already
        read, and only when they check out: server fps with its frame time, the server time in this year. Hitches and
        the location aren't taken this way (a pop-up across them reads as a wrong number or place, not a blank).
        Returns the keys that gave something. Costs nothing when every line read fully."""
        def gaps(k):
            return [f for f in INK_FIELDS.get(k, ()) if snap.get(f) is None]
        p, right = blk["pitch"], blk["right"]
        need = [r for r in rows if gaps(r[0])]
        # A banner across the Server FPS line can hide its label from the search too; it's the line right above Server
        by = {r[0]: r for r in rows}
        if "server_fps" not in by and "server" in by:
            need.append(("server_fps", blk["rect"][0] + p, by["server"][2] - p))
        if not need:
            return set()
        x0, y0, x1, y1 = (int(v) for v in blk["rect"])
        fixed = set()
        for strict in (False, True):
            if not need:
                break
            clean = np.zeros_like(img)
            clean[y0:y1 + 1, x0:x1 + 1] = ink_only(img[y0:y1 + 1, x0:x1 + 1], strict)
            got = self._rec([self._line_crop(clean, lx, cy, right + 0.6 * p, p) for _, lx, cy in need])
            still = []
            for (k, lx, cy), t in zip(need, got):
                if classify(t)[0] == k:
                    new, _ = _parse([t])
                    if k == "server_fps" and not _fps_agrees(new.get("server_fps"), new.get("server_ms")):
                        new = {}
                    if k == "server_time" and not _this_year(new.get("server_time")):
                        new = {}
                    for f in gaps(k):
                        if new.get(f) is not None:
                            snap[f] = new[f]
                            fixed.add(k)
                if gaps(k):
                    still.append((k, lx, cy))
            need = still
        if fixed:
            snap["ok"] = bool(snap.get("server_fps") is not None and (
                snap.get("pop_shard") is not None or snap.get("pop_srv") is not None or snap.get("ping_ms") is not None))
        return fixed

    def _merge_extras(self, img, snap):
        """Add the 1.5.0 extra lines (zone, render split, tracked mission, planet) to a good reading. Read every
        EXTRA_EVERY readings from just around the block; anything that goes wrong just leaves them out."""
        blk = self._cache
        self._extra_n += 1
        if blk and (self._extra_n % EXTRA_EVERY == 1 or not self._extras[0]):
            try:
                self._extras = (self._read_extras(img, blk), time.monotonic())
            except Exception:
                self._extras = ({}, time.monotonic())
        # The session QR code (when it's on screen) carries the shard id: use it when the ShardId line wasn't read
        if snap.get("shard_id") is None:
            qs, qat = getattr(self, "_qr_shard", (None, 0.0))
            if (self._extra_n % EXTRA_EVERY == 1 or qs is None) and time.monotonic() - getattr(self, "_qr_tried", 0.0) > 4:
                self._qr_tried = time.monotonic()
                got = qr_shard(img)
                if got:
                    qs, qat = got, time.monotonic()
                    self._qr_shard = (qs, qat)
            if qs and time.monotonic() - qat <= EXTRA_KEEP_S:
                snap["shard_id"] = qs
                snap["shard_from_qr"] = True
        fields, at = self._extras
        if time.monotonic() - at <= EXTRA_KEEP_S:
            for k in EXTRA_FIELDS:
                if snap.get(k) is None and fields.get(k) is not None:
                    snap[k] = fields[k]

    def _read_extras(self, img, blk):
        """The extra lines. Where they sit is found once (a detector pass around the block, then the start of each
        line); after that only those lines are read, and the full look happens again every EXTRA_RESCAN reads or
        when one of them isn't what it was (a mission line came or went)."""
        p, right = blk["pitch"], blk["right"]
        rows = self._extra_rows if getattr(self, "_extra_blk", None) is blk else None
        self._extra_scans = getattr(self, "_extra_scans", 0) + 1
        if not rows or self._extra_scans % EXTRA_RESCAN == 0:
            rows = self._find_extras(img, blk)
            self._extra_rows, self._extra_blk = rows, blk
        if not rows:
            return {}
        texts = self._rec([self._line_crop(img, x0, cy, right + 0.6 * p, p) for _, x0, cy in rows])
        out = dict.fromkeys(EXTRA_FIELDS)
        for (want, _, _), t in zip(rows, texts):
            key, rest = classify(t)
            if key not in EXTRA_KEYS:
                self._extra_rows = None          # the lines moved: look again next time
                continue
            if key != want and {key, want} != {"planet", "no_planet"}:
                self._extra_rows = None
            try:
                PARSERS[key](out, rest)
            except Exception:
                pass
        _sanity(out)
        return {k: out[k] for k in EXTRA_FIELDS if out.get(k) is not None}

    def _find_extras(self, img, blk):
        p, right = blk["pitch"], blk["right"]
        x0, y0, x1, y1 = blk["rect"]
        H, W = img.shape[:2]
        ey0, ey1 = max(0, int(y0 - 8 * p)), min(H, int(np.ceil(y1 + 6 * p)))
        ex0 = max(0, int(min(x0, right - 60 * p)))           # a Tracked mission line can be 55 pitches long
        crop = img[ey0:ey1, ex0:int(np.ceil(min(W, x1)))]
        segs = _segments(self._det(crop, blk["ds"], ex0, ey0), p)
        core = [cy for _, _, cy in blk["rows"]]
        todo = [g for g in segs if abs(g[2] - right) < 2.0 * p and g[2] - g[0] > 2.5 * p
                and all(abs((g[1] + g[3]) / 2 - cy) > 0.45 * p for cy in core)][:26]      # the lines below the block come last
        if not todo:
            return []
        heads = self._rec([self._line_crop(img, g[0], (g[1] + g[3]) / 2, min(g[2], g[0] + 11 * p), p) for g in todo])
        rows, keys = [], set()
        for g, t in zip(todo, heads):
            k = classify(t)[0]
            if k in EXTRA_KEYS and k not in keys:
                rows.append((k, g[0], (g[1] + g[3]) / 2))
                keys.add(k)
        return rows[:6]

    def _fast(self, img, blk):
        p = blk["pitch"]
        x0, y0, x1, y1 = blk["rect"]
        crop = img[int(y0):int(np.ceil(y1)), int(x0):int(np.ceil(x1))]
        segs = _segments(self._det(crop, blk["ds"], int(x0), int(y0)), p)
        use = []
        for key, _, cy in blk["rows"]:
            best = None
            for g in segs:
                if abs((g[1] + g[3]) / 2 - cy) < 0.45 * p and abs(g[2] - blk["right"]) < 2.0 * p:
                    best = g
                    break
            if best is None:
                return None
            # a line cut off at the edge of the crop means the block has moved
            if best[0] < x0 + 0.6 * p or (x1 < img.shape[1] - 1 and best[2] > x1 - 0.4 * p):
                return None
            use.append((key, best[0], cy))
        snap, labels_ok = self._read_rows(img, blk, use)
        # Every line must still be the line we expect there; if not, the block
        # has changed shape and we search again. A line that is in place but
        # misread this time just leaves its fields empty.
        if not labels_ok or not snap["ok"]:
            return None
        return snap

    def find_block(self, img_bgr):
        """Search for the overlay block. Returns (x0, y0, x1, y1) or None."""
        with self._lock:
            blk = self._search(img_bgr)
            if blk:
                self._cache = blk
            return tuple(int(v) for v in blk["rect"]) if blk else None

    def reset(self):
        with self._lock:
            self._cache = None
            self._seen = {}

    def read(self, img_bgr, ts=None):
        """Read one frame. Returns a Snapshot dict (with 'ts')."""
        t0 = time.perf_counter()
        if img_bgr is not None and getattr(img_bgr, "ndim", 0) == 3 and img_bgr.shape[2] == 4:
            img_bgr = cv2.cvtColor(img_bgr, cv2.COLOR_BGRA2BGR)      # mss / dxcam give BGRA
        with self._lock:
            snap, path = None, None
            if img_bgr is not None and getattr(img_bgr, "ndim", 0) == 3 and img_bgr.shape[0] >= 200:
                blk = self._cache
                if blk and blk["shape"] == img_bgr.shape[:2]:
                    snap = self._fast(img_bgr, blk)
                    path = "fast" if snap else None
                if snap is None:
                    self._cache = None
                    self._seen = {}
                    H = img_bgr.shape[0]
                    # The game may draw smaller than the screen (rendering at 1440p on a 4K monitor). Try the
                    # height that worked last, then the screen's own, then the common smaller ones; the extra
                    # heights cost a search each, so only while the overlay was recently there or now and then.
                    heights = [h for h in (self._game_h, H) if h and h <= H]     # never taller than the screen
                    if time.monotonic() - self._last_alt >= self.wide_search_every:
                        self._last_alt = time.monotonic()
                        heights += [h for h in (1440, 1080) if h < 0.9 * H]
                    heights = list(dict.fromkeys(heights))
                    for wide in (False, True):
                        if wide:
                            # a wider search costs more, so only now and then
                            if self._fails < 2 or time.monotonic() - self._last_wide < self.wide_search_every:
                                break
                            self._last_wide = time.monotonic()
                        tries = [(gh, False) for gh in heights]
                        if not wide and (self._fails < ALT_RECENT_FAILS or time.monotonic() - self._last_altscale >= self.wide_search_every):
                            self._last_altscale = time.monotonic()
                            tries += [(heights[0], True)] if heights else []
                        for gh, alt in tries:
                            blk = self._search(img_bgr, wide=wide, game_h=None if gh == H else gh, alt=alt)
                            if blk:
                                snap, _ = self._read_rows(img_bgr, blk, blk["rows"])
                                if snap["ok"]:
                                    self._cache = blk
                                    self._game_h = gh
                                    path = "wide" if wide else "search"
                                    break
                                snap = None
                                self._seen = {}
                        if snap is not None:
                            break
            if snap is None and img_bgr is not None and getattr(img_bgr, "ndim", 0) == 3 and img_bgr.shape[0] >= 200 \
                    and self._fails < ALT_RECENT_FAILS:
                # A banner or pop-up across the block can hide enough labels that it isn't found: look for it once
                # more in a copy with only the overlay's own text (top right only, so it stays cheap)
                H, W = img_bgr.shape[:2]
                gh = self._game_h or H
                rw, rh = int(min(W, 1500 * H / REF_H)), int(min(H, 800 * H / REF_H))
                clean = np.zeros_like(img_bgr)
                clean[0:rh, W - rw:W] = ink_only(img_bgr[0:rh, W - rw:W])
                blk = self._search(clean, game_h=None if gh == H else gh)
                if blk:
                    snap, _ = self._read_rows(img_bgr, blk, blk["rows"])
                    if snap["ok"]:
                        # Found only through the banner: the lines it covers can read as a wrong place, count or
                        # shard, so those aren't taken from this reading (LAB 8 Nov: "locatigh__NyxStart"); the
                        # session QR code and Game.log still give the shard
                        snap["location"] = snap["hitches"] = snap["shard_id"] = None
                        self._cache = blk
                        path = "ink"
                    else:
                        snap = None
                        self._seen = {}
            if snap is None:
                self._fails += 1
                snap = dict.fromkeys(FIELDS)
                snap["ok"] = False
            else:
                self._fails = 0
                self._merge_extras(img_bgr, snap)
            self.last_path = path
            self.last_ms = (time.perf_counter() - t0) * 1000
        snap["ts"] = time.time() if ts is None else ts
        return snap


def qr_shard(img):
    """The shard id from the game's session QR code in the top right, when it's showing (r_DisplaySessionInfo, and
    always on the PTU). The code holds "<session id> <shard id> <unix time> <build>"; only the shard id is kept,
    never the session id. None when there's no code or it doesn't read."""
    try:
        H, W = img.shape[:2]
        crop = img[0:int(H * 0.25), int(W * 0.8):W]
        text, _, _ = cv2.QRCodeDetector().detectAndDecode(crop)
    except Exception:
        return None
    for tok in (text or "").split():
        sid = norm_shard_id(tok)
        if sid:
            return sid
    return None


_default = None


def _reader():
    global _default
    if _default is None:
        _default = OverlayReader()
    return _default


def find_block(img_bgr):
    return _reader().find_block(img_bgr)


def read(img_bgr, ts=None):
    return _reader().read(img_bgr, ts)
