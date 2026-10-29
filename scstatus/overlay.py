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
)

INT_FIELDS = {"hitches", "restarts", "pop_shard", "pop_srv", "rl_entities",
              "vram_used_mb", "vram_total_mb"}

# Plausible ranges; anything outside is treated as a misread and dropped.
LIMITS = {
    "server_fps": (0.1, 1000), "server_fps_min": (0, 1000), "server_fps_max": (0, 1000),
    "server_ms": (0.1, 60000), "server_ms_min": (0, 60000), "server_ms_max": (0, 60000),
    "hitches": (0, 10_000_000), "restarts": (0, 100_000),
    "pop_shard": (0, 20_000), "pop_srv": (0, 5_000),
    "ping_ms": (0, 60000), "loss_pct": (0, 100),
    "bw_in_kbps": (0, 10_000_000), "bw_out_kbps": (0, 10_000_000),
    "rl_entities": (0, 100_000_000), "rl_tick_ms": (0, 100_000), "rl_mtsync_ms": (0, 100_000),
    "client_fps": (0.1, 5000), "client_fps_min": (0, 5000), "client_fps_max": (0, 5000),
    "client_ms": (0.01, 60000),
    "vram_used_mb": (0, 1_000_000), "vram_total_mb": (1, 1_000_000),
}

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


def fix_digits(s):
    """Turn O/o/D/Q into 0 and I/l/|/! into 1 where they sit in a number."""
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
    out["server_name"] = out.get("server_name") or norm_server_name(name)
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
        segs.append(seg)
    s = "-".join(segs)
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+){3,}", s):
        return None
    return s


_ENVS = r"(?:pub|ptu|eptu|tech\w*|evo\w*|[a-z]{2,6})"
_SHARD_RE = re.compile(r"(" + _ENVS + r")_?([a-z]{2,8}\d{1,2}[a-z]?)_?(\d{5,})_?(\d{3})")


def norm_shard_id(s):
    """'pub apse2a 12881860 090' (any mix of spaces, underscores, dashes,
    or none at all) -> 'pub_apse2a_12881860_090'."""
    t = s.translate(_PUNCT).strip().lower()
    t = re.sub(r"[\s_\-.,:;]+", "_", t).strip("_")
    parts = t.split("_")
    if len(parts) >= 4:
        env, reg = parts[0], parts[1]
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


PARSERS = {
    "fps": _p_fps, "shard": _p_shard, "server_fps": _p_server_fps,
    "server": _p_server, "net": _p_net, "rl": _p_rl, "server_time": _p_server_time,
    "vram": _p_vram, "location": _p_location,
}


def _sanity(out):
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
WANTED = ("fps", "shard", "server_fps", "server", "net", "rl", "server_time", "vram", "location")
ANCHORS = set(WANTED) | {"session"}
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
        self.last_path = None        # "fast", "search", "wide" or None (diagnostics)
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

    def _search(self, img, wide=False):
        """Find the block: detect text in the top right, read the first few
        characters of each line and look for the overlay's line labels."""
        H, W = img.shape[:2]
        s = H / REF_H
        if wide:
            rw, rh = int(W * 0.6), int(H * 0.7)
        else:
            rw, rh = int(min(W, 1500 * s)), int(min(H, 800 * s))
        ox = W - rw
        ds = float(np.clip(DET_SCALE / s, 0.25, 2.0))
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
            "ds": float(np.clip(DET_SCALE * REF_PITCH / pitch, 0.25, 2.0)),
            "rows": rows,
        }

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
        for key, _, _ in todo:
            if key in seen:
                self._seen[key] = (masks[key], texts[key], 0)
            else:
                self._seen.pop(key, None)
        return snap, labels_ok

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
                    for wide in (False, True):
                        if wide:
                            # a wider search costs more, so only now and then
                            if self._fails < 2 or time.monotonic() - self._last_wide < self.wide_search_every:
                                break
                            self._last_wide = time.monotonic()
                        blk = self._search(img_bgr, wide=wide)
                        if blk:
                            snap, _ = self._read_rows(img_bgr, blk, blk["rows"])
                            if snap["ok"]:
                                self._cache = blk
                                path = "wide" if wide else "search"
                                break
                            snap = None
                            self._seen = {}
            if snap is None:
                self._fails += 1
                snap = dict.fromkeys(FIELDS)
                snap["ok"] = False
            else:
                self._fails = 0
            self.last_path = path
            self.last_ms = (time.perf_counter() - t0) * 1000
        snap["ts"] = time.time() if ts is None else ts
        return snap


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
