"""The known-issues library: which log lines are noise, which are real problems,
and what to tell the player about each.

The library is data (library/issues.json), so new issues can be added without a
new release of the app. A newer copy in data\\issues.json (downloaded or edited by
hand) wins over the one shipped with the app.
"""

import json
import re
from collections import defaultdict

from .config import DATA, LIBRARY, say

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


class _Safe(dict):
    def __missing__(self, k):
        return "{" + k + "}"


class Rule:
    def __init__(self, d):
        self.d = d
        self.id = d["id"]
        self.kind = d.get("kind", "problem")
        self.severity = d.get("severity", "medium")
        self.area = d.get("area", "")
        m = d.get("match", {})
        self.tag = m.get("tag")
        self.level = m.get("level")
        self.rx = re.compile(m["regex"]) if m.get("regex") else None

    def match(self, level, tag, msg):
        if self.tag and tag != self.tag:
            return None
        if self.level and level != self.level:
            return None
        if self.rx:
            m = self.rx.search(msg)
            if not m:
                return None
            return {k: v for k, v in m.groupdict().items() if v is not None}
        return {}

    def text(self, key, fields):
        v = self.d.get(key)
        if isinstance(v, list):
            return [x.format_map(_Safe(fields)) for x in v]
        return v.format_map(_Safe(fields)) if isinstance(v, str) else v


def patch_tuple(v):
    """"4.10.3" -> (4, 10, 3); anything else -> None."""
    m = re.fullmatch(r"(\d+)\.(\d+)(?:\.(\d+))?", str(v or "").strip())
    return tuple(int(x or 0) for x in m.groups()) if m else None


def clean_fixes(items):
    """CIG's claimed fixes from the library (cig_fixes), keeping only well-formed entries."""
    out = []
    for f in items if isinstance(items, list) else []:
        if not isinstance(f, dict) or not f.get("id") or not patch_tuple(f.get("patch")) or not f.get("said"):
            continue
        out.append({"id": str(f["id"])[:40], "patch": str(f["patch"]), "said": str(f["said"])[:300],
                    "ptu": int(f["ptu"]) if str(f.get("ptu", "")).isdigit() else None,
                    "starc": str(f["starc"])[:20] if f.get("starc") else None,
                    "rules": [str(r) for r in f.get("rules") or [] if isinstance(r, str)][:10],
                    "how": "same" if f.get("how") == "same" else "related",
                    "measure": f.get("measure") if f.get("measure") in ("crashes", "restarts") else None,
                    "ask": bool(f.get("ask")),
                    "chip": str(f["chip"])[:60] if f.get("ask") and f.get("chip") else None,
                    "words": [str(w).lower()[:30] for w in f.get("words") or [] if isinstance(w, str)][:10] if f.get("ask") else [],
                    "ic_title": str(f["ic_title"])[:120] if f.get("ic_title") else None,
                    "explain": str(f["explain"])[:400] if f.get("explain") else None})
    return out


def has_fix(f, branch, build=None):
    """Is this player's game at or past the patch that listed fix f? By build number when there is one (they only
    go up, and the Branch line can't be trusted: the 4.10.3 PTU calls itself sc-alpha-4.10.0), else by patch."""
    b = str(build or "")
    if f.get("ptu") and b.isdigit():
        return int(b) >= f["ptu"]
    mine = patch_tuple(branch)
    return mine is not None and mine >= patch_tuple(f["patch"])


def clean_hints(items):
    """Contract titles that mean an activity (library activity_hints), lower-cased for matching."""
    out = []
    for h in items if isinstance(items, list) else []:
        if isinstance(h, dict) and isinstance(h.get("activity"), str) and isinstance(h.get("titles"), list):
            out.append({"activity": h["activity"][:40],
                        "titles": [t.lower().strip()[:80] for t in h["titles"] if isinstance(t, str) and t.strip()][:60]})
    return out


def activity_for(hints, contracts):
    """The activity an active contract points to (newest first), or None."""
    active = sorted((c for c in contracts or [] if c.get("result") == "active" and c.get("name")),
                    key=lambda c: c.get("accepted") or 0, reverse=True)
    for c in active:
        name = c["name"].lower().strip()
        for h in hints:
            if any(t == name or t in name for t in h["titles"]):
                return h["activity"]
    return None


def fix_for(fixes, rule_id, branch, build=None):
    """What CIG's notes say about this problem, for a player on this build (or patch `branch`):
    state "coming" when the fix is in a later patch than theirs, "listed" when their game has the patch that
    listed it and the problem still turned up. None when the notes don't mention it."""
    if not rule_id:
        return None
    for f in fixes:
        if rule_id not in f["rules"]:
            continue
        state = "listed" if has_fix(f, branch, build) else "coming"
        return {"id": f["id"], "patch": f["patch"], "said": f["said"], "starc": f["starc"], "how": f["how"],
                "ask": f["ask"], "state": state}
    return None


def asks_for(fixes, branch, build=None):
    """CIG's "tell us where it still happens" items (quick picks for a moment): from the build that listed the fix
    (PTU included) until a later patch (by the Branch line, when it names a later one)."""
    mine = patch_tuple(branch)
    return [f for f in fixes if f["ask"] and f["chip"] and has_fix(f, branch, build)
            and (mine is None or mine <= patch_tuple(f["patch"]))]


def ask_matching(fixes, branch, what, build=None):
    """The ask item a moment's description is about (its words appear in it), or None."""
    text = (what or "").lower()
    return next((f for f in asks_for(fixes, branch, build) if f["words"] and any(w in text for w in f["words"])), None)


class Library:
    def __init__(self, path=None):
        self.version = ""
        self.rules = []
        self.cig_fixes = []
        self.activity_hints = []
        self.by_tag = defaultdict(list)
        self.untagged = []
        self.path = path or self._pick()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:
            say(f"Couldn't load the known-issues library ({e}).")
            data = {"rules": []}
        self.version = data.get("version", "")
        self.cig_fixes = clean_fixes(data.get("cig_fixes"))
        self.activity_hints = clean_hints(data.get("activity_hints"))
        for d in data.get("rules", []):
            try:
                r = Rule(d)
            except (re.error, KeyError) as e:
                say(f"Skipped a broken library rule {d.get('id')}: {e}")
                continue
            self.rules.append(r)
            (self.by_tag[r.tag] if r.tag else self.untagged).append(r)

    @staticmethod
    def _pick():
        """The shipped library, unless data\\issues.json is a newer dated version (YYYY-MM-DD.n)."""
        local = DATA / "issues.json"
        if not local.exists():
            return LIBRARY
        if not LIBRARY.exists():
            return local

        def ver(p):
            try:
                v = json.loads(p.read_text(encoding="utf-8")).get("version", "")
            except Exception:
                return None
            m = re.fullmatch(r"(\d{4}-\d\d-\d\d)(?:\.(\d+))?", v or "")
            return (m.group(1), int(m.group(2) or 0)) if m else None
        lv, sv = ver(local), ver(LIBRARY)
        return local if lv and (not sv or lv > sv) else LIBRARY

    def match(self, level, tag, msg):
        """First rule that matches this line: (rule, fields) or (None, None)."""
        for r in self.by_tag.get(tag, ()):
            f = r.match(level, tag, msg)
            if f is not None:
                return r, f
        for r in self.untagged:
            f = r.match(level, tag, msg)
            if f is not None:
                return r, f
        return None, None

    def get(self, rule_id):
        return next((r for r in self.rules if r.id == rule_id), None)

    def listing(self):
        out = []
        for r in self.rules:
            if r.kind == "noise":
                continue
            out.append({"id": r.id, "kind": r.kind, "severity": r.severity, "area": r.area,
                        "title": r.d.get("title", r.id), "explain": r.d.get("explain", ""),
                        "fixes": r.d.get("fixes", []), "links": r.d.get("links", []),
                        "builds_seen": r.d.get("builds_seen", [])})
        out.sort(key=lambda x: (SEVERITY_ORDER.get(x["severity"], 3), x["area"], x["title"]))
        return out

    def counts(self):
        c = defaultdict(int)
        for r in self.rules:
            c[r.kind] += 1
        return dict(c)
