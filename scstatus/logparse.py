"""Reading Game.log.

The game writes a plain-text log every session (older ones go to the logbackups
folder). This module turns its lines into events: which shard you joined, how
you left, contracts and objectives, your PC's hardware, and every error line.

Your character name and account numbers are in many lines. Events keep the raw
line only for the player's own use on this PC; redact.py strips identifiers
before anything is shared.
"""

import datetime as dt
import re
import time
from pathlib import Path

LINE = re.compile(r"^<(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?)Z>\s?(?:\[(\w+)\] )?(?:<((?:[^<>]|<[^<>]*>){1,160})> ?)?(.*)$")
TEAMS = re.compile(r"\s*\[Team_[^\]]*\](?:\[[A-Za-z0-9_ ]+\])*\s*$")

# Header lines
BUILD = re.compile(r'BackupNameAttachment=" Build\((\d+)\)')
FILEVER = re.compile(r"FileVersion: ([\d.]+)")
CPU = re.compile(r"^Host CPU: (.+)$")
THREADS = re.compile(r"^Logical CPU Count: (\d+)")
RAM = re.compile(r"^(\d+)MB physical memory installed")
VRAM = re.compile(r"^\s*- Dedicated video memory: (\d+) MB")
GPU_BENCH = re.compile(r"^GPU benchmark: ([\d.]+) ms")
CPU_BENCH = re.compile(r"^CPU benchmark: ([\d.]+) ms \(int\+mem\), ([\d.]+) ms")
GPU_NAME = re.compile(r"^VulkanMetric - Device \(([^)]+)\) \[GPU \(Discrete\)\]")
GPU_NAME_DX = re.compile(r"^\s*- Description: (.+)$")

# Events
JOIN_PU = re.compile(r"address\[([^\]]*)\] port\[(\d+)\] shard\[([^\]]+)\]")
DISCONNECT = re.compile(r'cause=(\d+) reason="([^"]*)".*?isRemote=(\d)')
NOTIFY = re.compile(r'Added notification "(.*?)" \[\d+\] to queue.*?MissionId: \[([0-9a-f-]+)\]', re.S)
SHUTDOWN_MARKS = ("CCIGBroker::FastShutdown", "Shutting down all force feedback")

ZERO_GUID = "00000000-0000-0000-0000-000000000000"


def parse_ts(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp()


def region_of(shard_id):
    """'pub_apse2a_12881860_090' -> 'apse2'. Server regions use AWS/GCP-style codes."""
    m = re.match(r"^[a-z]+_([a-z]+\d)[a-z]?_", shard_id or "")
    return m.group(1) if m else None


REGION_NAMES = {
    # Codes as they appear in shard ids. Names are the game launcher's broad regions, not exact cities.
    "apse2": "Australia", "apse1": "Asia", "ape1": "Asia", "apne1": "Asia",
    "use1": "US East", "use2": "US East", "usw1": "US West", "usw2": "US West",
    "euw1": "Europe", "euw2": "Europe", "euc1": "Europe", "eun1": "Europe",
}


def region_name(code):
    return REGION_NAMES.get(code or "", (code or "unknown").upper())


# --------------------------------------------------------------------------
# Signatures: one error, many lines -> one key
# --------------------------------------------------------------------------

_SIG_SUBS = [
    (re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"), "<guid>"),
    (re.compile(r"\b[0-9a-f]{32}\b"), "<hex>"),
    (re.compile(r"0x[0-9a-fA-F]+"), "<hex>"),
    (re.compile(r"'[^']{1,40}'\s*\[\d+\]"), "'<name>'[N]"),
    (re.compile(r"\b(Player|player|Owner|owner)\[[^\]]+\]"), r"\1[<player>]"),
    (re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b"), "<ip>"),
    (re.compile(r"(?<=[A-Za-z_])_\d+\b"), "_N"),
    (re.compile(r"\d+(?:\.\d+)?"), "N"),
    (re.compile(r"\s+"), " "),
]


def signature(tag, msg):
    """Normalise an error line so the same problem always gives the same key."""
    s = TEAMS.sub("", msg or "")
    for rx, rep in _SIG_SUBS:
        s = rx.sub(rep, s)
    s = s.strip()[:160]
    return f"{tag or '-'}| {s}"


# --------------------------------------------------------------------------
# Line -> event
# --------------------------------------------------------------------------

def parse_line(raw):
    """One log line -> event dict, or None for lines we don't use."""
    m = LINE.match(raw)
    if not m:
        return None
    ts_s, level, tag, msg = m.groups()
    ts = parse_ts(ts_s)
    msg = msg.rstrip()
    if level is None and tag is None:
        return _header(ts, msg)
    if tag == "Join PU" and (j := JOIN_PU.search(msg)):
        sid = j.group(3)
        return {"ts": ts, "kind": "join_pu", "shard_id": sid, "region": region_of(sid),
                "address": j.group(1), "port": int(j.group(2))}
    if tag == "Channel Disconnected" and (d := DISCONNECT.search(msg)):
        return {"ts": ts, "kind": "disconnect", "cause": int(d.group(1)), "reason": d.group(2),
                "remote": d.group(3) == "1", "frontend": 'gamerules="SC_Frontend"' in msg}
    if tag == "SHUDEvent_OnNotification" and (n := NOTIFY.search(msg)):
        return _notification(ts, n.group(1), n.group(2))
    if level in ("Error", "Warning"):
        return {"ts": ts, "kind": "error", "level": level, "tag": tag or "", "text": TEAMS.sub("", msg),
                "sig": signature(tag, msg)}
    if tag and any(k in tag for k in SHUTDOWN_MARKS) or any(k in msg for k in SHUTDOWN_MARKS):
        return {"ts": ts, "kind": "shutdown"}
    return None


def _header(ts, msg):
    if m := BUILD.search(msg):
        return {"ts": ts, "kind": "log_start", "build": m.group(1)}
    if m := FILEVER.search(msg):
        return {"ts": ts, "kind": "version", "version": m.group(1)}
    for rx, key, conv in ((CPU, "cpu", str), (THREADS, "threads", int), (RAM, "ram_mb", int),
                          (VRAM, "vram_mb", int), (GPU_BENCH, "gpu_bench_ms", float), (GPU_NAME, "gpu", str)):
        if m := rx.search(msg):
            return {"ts": ts, "kind": "hardware", key: conv(m.group(1).strip())}
    if m := CPU_BENCH.search(msg):
        return {"ts": ts, "kind": "hardware", "cpu_bench_ms": float(m.group(1)), "cpu_bench_fp_ms": float(m.group(2))}
    if any(k in msg for k in SHUTDOWN_MARKS):
        return {"ts": ts, "kind": "shutdown"}
    return None


NOTE_KINDS = [
    (re.compile(r"^Contract Accepted:\s*(.+?):?\s*$"), "contract_accepted"),
    (re.compile(r"^Contract (?:Complete|Completed):\s*(.+?):?\s*$"), "contract_complete"),
    (re.compile(r"^Contract Failed:\s*(.+?):?\s*$"), "contract_failed"),
    (re.compile(r"^Contract (?:Abandoned|Withdrawn|Cancelled|Canceled):\s*(.+?):?\s*$"), "contract_abandoned"),
    (re.compile(r"^Contract Shared:\s*(.+?):?\s*$"), "contract_shared"),
    (re.compile(r"^New Objective:\s*(.+?):?\s*$"), "objective_new"),
    (re.compile(r"^Objective Complete:\s*(.+?):?\s*$"), "objective_complete"),
    (re.compile(r"^Objective Failed:\s*(.+?):?\s*$"), "objective_failed"),
    (re.compile(r"^Objective Withdrawn:\s*(.+?):?\s*$"), "objective_withdrawn"),
]


def _notification(ts, text, mission_id):
    text = re.sub(r"<[^>]+>", "", text).strip()
    mid = None if mission_id == ZERO_GUID else mission_id
    for rx, kind in NOTE_KINDS:
        if m := rx.match(text):
            return {"ts": ts, "kind": kind, "name": m.group(1).strip(" :"), "mission_id": mid}
    return {"ts": ts, "kind": "notification", "text": text.rstrip(": "), "mission_id": mid}


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------

class Session:
    """Everything one Game.log says, built up event by event."""

    def __init__(self, name=""):
        self.name = name
        self.start = None
        self.end = None
        self.build = None
        self.version = None
        self.hardware = {}
        self.joins = []
        self.disconnects = []
        self.contracts = {}     # mission id -> {name, accepted, objectives{text: state}, result, ended}
        self.errors = []
        self.notifications = []
        self.clean_exit = False
        self.events = []

    def add(self, ev):
        if ev is None:
            return
        self.events.append(ev)
        ts = ev["ts"]
        self.start = self.start or ts
        self.end = ts
        k = ev["kind"]
        if k == "log_start":
            self.build = ev["build"]
        elif k == "version":
            self.version = self.version or ev["version"]
        elif k == "hardware":
            for key, v in ev.items():
                if key not in ("ts", "kind"):
                    self.hardware.setdefault(key, v)
        elif k == "join_pu":
            self.joins.append(ev)
        elif k == "disconnect":
            self.disconnects.append(ev)
        elif k == "shutdown":
            self.clean_exit = True
        elif k == "error":
            self.errors.append(ev)
        elif k.startswith("contract_") or k.startswith("objective_"):
            self._contract(ev)
        elif k == "notification":
            self.notifications.append(ev)

    def _contract(self, ev):
        mid = ev.get("mission_id") or f"name:{ev['name']}"
        k = ev["kind"]
        if k == "contract_accepted":
            self.contracts[mid] = {"mission_id": ev.get("mission_id"), "name": ev["name"], "accepted": ev["ts"],
                                   "objectives": {}, "result": "active", "ended": None}
            return
        c = self.contracts.get(mid)
        if c is None:
            if k.startswith("contract_"):
                c = self.contracts[mid] = {"mission_id": ev.get("mission_id"), "name": ev["name"], "accepted": None,
                                           "objectives": {}, "result": "active", "ended": None}
            else:
                return
        if k.startswith("objective_"):
            state = k.split("_", 1)[1]
            text = ev["name"]
            # "Need 0/1 of X" -> "Need 1/1 of X" when it progresses: key on the part after the count
            key = re.sub(r"^\w+ \d+/(\d+)", r"\1", text)
            c["objectives"][key] = {"text": text, "state": state if state != "new" else "open", "ts": ev["ts"]}
        else:
            c["result"] = k.split("_", 1)[1]
            c["ended"] = ev["ts"]

    @property
    def shard_id(self):
        return self.joins[-1]["shard_id"] if self.joins else None

    def load_seconds(self):
        if self.start and self.joins:
            return round(self.joins[0]["ts"] - self.start)
        return None

    def summary(self):
        bad = [d for d in self.disconnects if d["cause"] not in NORMAL_CAUSES]
        return {
            "name": self.name, "start": self.start, "end": self.end, "build": self.build, "version": self.version,
            "shard_id": self.shard_id, "region": region_of(self.shard_id), "joins": len(self.joins),
            "load_s": self.load_seconds(), "minutes": round((self.end - self.start) / 60, 1) if self.start else 0,
            "disconnects": [{"cause": d["cause"], "reason": d["reason"], "ts": d["ts"]} for d in self.disconnects],
            "bad_disconnects": len(bad), "errors": len(self.errors), "clean_exit": self.clean_exit,
            "contracts": list(self.contracts.values()), "hardware": self.hardware,
        }


# Disconnect causes that are part of normal play
NORMAL_CAUSES = {30010, 30016}


def parse_file(path, name=None):
    s = Session(name or Path(path).name)
    with open(path, encoding="utf-8", errors="replace") as f:
        for raw in _joined_lines(f):
            s.add(parse_line(raw))
    return s


def _joined_lines(f):
    """Some messages run over several lines; join continuation lines (no timestamp) to the line before."""
    buf = None
    for line in f:
        line = line.rstrip("\r\n")
        if line.startswith("<") and LINE.match(line):
            if buf is not None:
                yield buf
            buf = line
        elif buf is not None and len(buf) < 20000:
            buf += " " + line.strip()
    if buf is not None:
        yield buf


# --------------------------------------------------------------------------
# Following the live log
# --------------------------------------------------------------------------

class LogTail:
    """Follows Game.log while you play. Starts a new Session when the game starts a new log."""

    def __init__(self, path, on_event=None, on_new_session=None):
        self.path = Path(path)
        self.on_event = on_event
        self.on_new_session = on_new_session
        self.pos = 0
        self.ident = None
        self.partial = ""
        self.pending = None
        self.session = None

    def _identity(self):
        try:
            with open(self.path, "rb") as f:
                return f.read(200)
        except OSError:
            return None

    def poll(self):
        """Read whatever's new. Returns the number of lines read."""
        try:
            size = self.path.stat().st_size
        except OSError:
            return 0
        ident = self._identity()
        if ident != self.ident or size < self.pos:
            self.ident = ident
            self.pos = 0
            self.partial = ""
            self.pending = None
            self.session = Session(self.path.name)
            if self.on_new_session:
                self.on_new_session(self.session)
        if size == self.pos:
            self._flush_pending(idle=True)
            return 0
        with open(self.path, "rb") as f:
            f.seek(self.pos)
            data = f.read(size - self.pos)
        self.pos = size
        text = self.partial + data.decode("utf-8", errors="replace")
        lines = text.split("\n")
        self.partial = lines.pop()
        n = 0
        for line in lines:
            line = line.rstrip("\r")
            if line.startswith("<") and LINE.match(line):
                self._flush_pending()
                self.pending = line
            elif self.pending is not None and len(self.pending) < 20000:
                self.pending += " " + line.strip()
            n += 1
        return n

    def _flush_pending(self, idle=False):
        if self.pending is None:
            return
        line, self.pending = self.pending, None
        ev = parse_line(line)
        if ev:
            self.session.add(ev)
            if self.on_event:
                self.on_event(ev, line)

    def run(self, stop, every=1.0):
        while not stop.is_set():
            try:
                self.poll()
            except Exception:
                pass
            stop.wait(every)
