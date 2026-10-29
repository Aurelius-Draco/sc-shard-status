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
IP = re.compile(r"\b(?!0\.0\.0\.0\b|127\.0\.0\.1\b)\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b")
IPV6 = re.compile(r"\[?\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{0,4}(?:%\w+)?\]?(?:/\d+)?")
LONG_NUM = re.compile(r"\b\d{6,}\b")
ENTITY_ID = re.compile(r"(?<=[A-Za-z_])\d{9,}(?=\b|_)")
URL = re.compile(r"https?://\S+")
WIN_PATH = re.compile(r"[A-Za-z]:[\\/][^\s\"']+")
USERS_DIR = re.compile(r"([\\/]Users[\\/])[^\\/\s\"']+", re.I)
HOSTNAME = re.compile(r"(<Hostname>\s*Name:\s*)[^,]+(,\s*Hostname:\s*)\S+")
WINUSER_FORMS = [re.compile(r"(for user ')[^']+(')"), re.compile(r"(\busername )\S+()")]
COMPUTER = re.compile(r"\b(Computer ?Name|Hostname|Machine ?Name|Host ?Name)(\s*[:=]\s*)\S+", re.I)

_N = r"([A-Za-z0-9_\-]{3,40})"
# Places a handle sits in a log line (own and other players'), from 76 real logs (docs/log-findings.md)
NAME_FORMS = [
    re.compile(r"'" + _N + r"'\s*\[\d+\]"),
    re.compile(r'nickname="' + _N + '"'),
    re.compile(r"\bHandle\[" + _N + r"\]"),
    re.compile(r"\b(?:Player|player|User|Owner|owner|AccountName|accountName)\s*[\[=:]\s*'?" + _N),
    re.compile(r"\b(?:Player|player) \[" + _N + r"\]"),
    re.compile(r"\bfor '" + _N + r"'"),
    re.compile(r"\bActor '" + _N + r"'"),
    re.compile(r"\bActor: " + _N + r" \(Non-Authoritative CLIENT: " + _N + r"\)"),
    re.compile(r"\blocalClient \[" + _N + r"\]"),
    re.compile(r"\b(?:on entity|owned by) '" + _N + r"'"),
    re.compile(r'entityName="' + _N + '"'),
    re.compile(r"^" + _N + r"\[\d+\] - CSCLocalPlayer"),
    re.compile(r"LandingArea: " + _N + r"'s"),
    re.compile(r"\bPlayer: " + _N + r" ?\["),
    re.compile(r"- name " + _N + r" - state"),
    re.compile(r"\bPlayer " + _N + r"\[\d+\] (?:entered|exited|triggered)"),
    re.compile(r"\b(?:User|Client): " + _N + r","),
    re.compile(r"CommunicationFinished\[" + _N + r"\]"),
    re.compile(r"channel '[^':]*: ?" + _N + r"'"),
    re.compile(r"\bfrom " + _N + r" \["),
    # notification text (other players)
    re.compile(r"New Member Joined\W+" + _N + r" has joined"),
    re.compile(r"Member Left\W+" + _N + r" has left"),
    re.compile(r"(?:^|\")\W*" + _N + r"\W+Party Invite Received", re.M),
    re.compile(r"(?:^|\")\W*" + _N + r"\W+Friend Request", re.M),
    re.compile(r"Crime Committed:[^\"]*?\bagainst\s+" + _N),
    re.compile(r"\bname = " + _N + r"\b"),
    re.compile(r"\b" + _N + r" is now party leader"),
    re.compile(r"Friend Added\W+" + _N),
    re.compile(r"New Party Leader\W+" + _N + r" is now party leader"),
    re.compile(r"Invitation Declined\W+" + _N + r" has declined"),
    re.compile(_N + r" wants to send you [\d,]+ UEC"),
    re.compile(_N + r" has sent you"),
    re.compile(r"You sent " + _N),
    re.compile(r"Quantum Travel Calibration (?:Started|Complete) By " + _N),
    re.compile(_N + r" has started to QT to your current location"),
]
NOT_NAMES = {"NULL", "null", "INVALID", "None", "none", "Unknown", "unknown", "local", "Default", "Local"}
# Entity and system names that sit in the same spots as handles
NOT_NAME_RX = re.compile(r"(_\d{6,}$|^\d|^(Team_|ui_|PU_|ATC_|ORIG_|AEGS_|ANVL_|DRAK_|MISC_|RSI_|CRUS_|ARGO_|"
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
                for n in m.groups():
                    if n and _is_name(n):
                        c[n] += 1
    return [n for n, _ in c.most_common()]


def _blank_names(m):
    out = m.group(0)
    for n in m.groups():
        if n and _is_name(n) and not n.startswith("<"):
            out = re.sub(r"(?<![A-Za-z0-9_<])" + re.escape(n) + r"(?![A-Za-z0-9_>])", "<PLAYER>", out)
    return out


class Redactor:
    def __init__(self, handles=()):
        self.handles = [h for h in dict.fromkeys(handles) if h and len(h) >= 3]
        self.names = {}
        for i, h in enumerate(self.handles):
            self.names[h] = "<YOU>" if i == 0 else f"<PLAYER{i}>"
        # The game sometimes writes a handle with spaces for underscores ("Some Pilot is now party leader")
        for h in list(self.handles):
            if "_" in h:
                spaced = h.replace("_", " ")
                self.names.setdefault(spaced, self.names[h])
                self.handles.append(spaced)
        self._rx = (re.compile(r"(?<![A-Za-z0-9_])(" + "|".join(re.escape(h) for h in
                                                                 sorted(self.handles, key=len, reverse=True))
                               + r")(?![A-Za-z0-9_])") if self.handles else None)

    @classmethod
    def from_lines(cls, lines, own_handle=None):
        """own_handle may be one name or a list (players can rename; the log keeps both)."""
        found = find_handles(lines)
        own = [own_handle] if isinstance(own_handle, str) else list(own_handle or [])
        if not own:
            own = [m.group(1) for line in lines for m in re.finditer(r"\bHandle\[([^\]]+)\]", line)]
        own = list(dict.fromkeys(own))
        rest = [h for h in found if h not in own]
        r = cls(own + rest)
        for h in own:
            r.names[h] = "<YOU>"
            r.names[h.replace("_", " ")] = "<YOU>"
        return r

    def line(self, s):
        if not s:
            return s
        s = URL.sub("<URL>", s)
        s = HOSTNAME.sub(r"\1<PC>\2<PC>", s)
        s = COMPUTER.sub(r"\1\2<PC>", s)
        s = USERS_DIR.sub(r"\1<WINUSER>", s)
        for rx in WINUSER_FORMS:
            s = rx.sub(r"\1<WINUSER>\2", s)
        s = WIN_PATH.sub("<PATH>", s)
        if self._rx:
            s = self._rx.sub(lambda m: self.names.get(m.group(1), "<PLAYER>"), s)
        for rx in NAME_FORMS:      # names not in the list (seen for the first time)
            s = rx.sub(_blank_names, s)
        s = GUID.sub("<GUID>", s)
        s = HEX32.sub("<HEX>", s)
        s = IPV6.sub("<IP>", s)
        s = IP.sub("<IP>", s)
        s = LONG_NUM.sub("<ID>", s)
        s = ENTITY_ID.sub("<ID>", s)
        return s

    def lines(self, lines):
        return [self.line(x) for x in lines]


def leaks(text, handles):
    """Anything identifying left in text (used by tests and as a last check before sharing)."""
    out = []
    for h in handles:
        if h and re.search(r"(?<![A-Za-z0-9_])" + re.escape(h) + r"(?![A-Za-z0-9_])", text):
            out.append(f"handle {h}")
    for rx, what in ((GUID, "guid"), (IP, "ip address"), (LONG_NUM, "long number"), (ENTITY_ID, "entity id"),
                     (USERS_DIR, "windows user")):
        if rx.search(text):
            out.append(what)
    return out
