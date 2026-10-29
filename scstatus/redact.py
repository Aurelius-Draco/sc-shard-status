"""Stripping identifiers before anything is shared.

Game.log lines carry your character name, account and entity numbers, session
ids, server addresses, and the names of friends and party members. Anything that
goes to the community service or the review queue passes through here first.

A report you send to CIG yourself (Issue Council) can include your own log in
full; that's you reporting to them. This module is for everything else.
"""

import re
from collections import Counter

GUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
HEX32 = re.compile(r"\b[0-9a-fA-F]{32}\b")
IP = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b")
LONG_NUM = re.compile(r"\b\d{6,}\b")
URL = re.compile(r"https?://\S+")
WIN_PATH = re.compile(r"[A-Za-z]:\\[^\s\"']+")

# Places a name sits in a log line
NAME_FORMS = [
    re.compile(r"'([A-Za-z0-9_\-]{3,32})'\s*\[\d+\]"),
    re.compile(r"\b(?:Player|player|Owner|owner|nickname|Nickname|Handle|handle|"
               r"AccountName|accountName)\s*[\[=:]\s*'?([A-Za-z0-9_\-]{3,32})"),
    re.compile(r"CommunicationFinished\[([A-Za-z0-9_\-]{3,32})\]"),
    re.compile(r"channel '[^':]*: ?([A-Za-z0-9_\-]{3,32})'"),
    re.compile(r"\bfrom ([A-Za-z0-9_\-]{3,32}) \["),
]
NOT_NAMES = {"NULL", "null", "INVALID", "None", "none", "Unknown", "unknown", "local", "Default", "Local"}
# Entity and system names that sit in the same spots as handles
NOT_NAME_RX = re.compile(r"(_\d{3,}$|^\d|^(Team_|ui_|PU_|ATC_|ORIG_|AEGS_|ANVL_|DRAK_|MISC_|RSI_|CRUS_|ARGO_|"
                         r"Shared_|Default_|Vehicle_|Loadout|Entity|Object|Item_|Inventory|Container|Location))", re.I)


def _is_name(n):
    return n not in NOT_NAMES and not NOT_NAME_RX.search(n) and not n.isdigit()


def find_handles(lines):
    """Names that look like player handles in these lines, most frequent first.
    The most frequent is almost always the player's own."""
    c = Counter()
    for line in lines:
        for rx in NAME_FORMS:
            for m in rx.finditer(line):
                n = m.group(1)
                if _is_name(n):
                    c[n] += 1
    return [n for n, _ in c.most_common()]


class Redactor:
    def __init__(self, handles=()):
        self.handles = [h for h in dict.fromkeys(handles) if h and len(h) >= 3]
        self.names = {}
        for i, h in enumerate(self.handles):
            self.names[h] = "<YOU>" if i == 0 else f"<PLAYER{i}>"
        self._rx = (re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(re.escape(h) for h in
                                                                 sorted(self.handles, key=len, reverse=True))
                               + r")(?![A-Za-z0-9_])") if self.handles else None)

    @classmethod
    def from_lines(cls, lines, own_handle=None):
        found = find_handles(lines)
        if own_handle:
            found = [own_handle] + [h for h in found if h != own_handle]
        return cls(found)

    def line(self, s):
        if not s:
            return s
        s = URL.sub("<URL>", s)
        s = WIN_PATH.sub("<PATH>", s)
        if self._rx:
            s = self._rx.sub(lambda m: self.names.get(m.group(1), "<PLAYER>"), s)
        for rx in NAME_FORMS:      # names not in the list (seen for the first time)
            s = rx.sub(lambda m: m.group(0).replace(m.group(1), "<PLAYER>")
                       if _is_name(m.group(1)) and not m.group(1).startswith("<") else m.group(0), s)
        s = GUID.sub("<GUID>", s)
        s = HEX32.sub("<HEX>", s)
        s = IP.sub("<IP>", s)
        s = LONG_NUM.sub("<ID>", s)
        return s

    def lines(self, lines):
        return [self.line(x) for x in lines]


def leaks(text, handles):
    """Anything identifying left in text (used by tests and as a last check before sharing)."""
    out = []
    for h in handles:
        if h and re.search(r"(?<![A-Za-z0-9_])" + re.escape(h) + r"(?![A-Za-z0-9_])", text):
            out.append(f"handle {h}")
    for rx, what in ((GUID, "guid"), (IP, "ip address"), (LONG_NUM, "long number")):
        if rx.search(text):
            out.append(what)
    return out
