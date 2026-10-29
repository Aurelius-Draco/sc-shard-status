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


class Library:
    def __init__(self, path=None):
        self.version = ""
        self.rules = []
        self.by_tag = defaultdict(list)
        self.untagged = []
        self.path = path or self._pick()
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as e:
            say(f"Couldn't load the known-issues library ({e}).")
            data = {"rules": []}
        self.version = data.get("version", "")
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
        local = DATA / "issues.json"
        if local.exists() and not LIBRARY.exists():
            return local
        if local.exists():
            try:
                lv = json.loads(local.read_text(encoding="utf-8")).get("version", "")
                sv = json.loads(LIBRARY.read_text(encoding="utf-8")).get("version", "")
                if lv >= sv:
                    return local
            except Exception:
                pass
        return LIBRARY

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
