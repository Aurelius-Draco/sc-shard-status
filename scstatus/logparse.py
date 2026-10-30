"""Reading Game.log.

The game writes a plain-text log every session (older ones go to the logbackups
folder). This module turns its lines into events: which shard you joined, how
you left (or crashed), contracts and objectives, freight elevator cycles, your
PC's hardware, and every error line.

Formats here were checked against 76 real logs (Sep-Oct 2026, builds 12572603,
12660092 and 12913470 = 4.10.2); see docs/log-findings.md.

Your character name and account numbers are in many lines. Events keep the raw
line only for the player's own use on this PC; redact.py strips identifiers
before anything is shared.
"""

import codecs
import datetime as dt
import re
import time
from pathlib import Path

LINE = re.compile(r"^<(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?)Z>\s?(?:\[SPAM \d+\])?(?:\[(\w+)\] )?"
                  r"(?:<((?:[^<>]|<[^<>]*>){1,160})> ?)?(.*)$", re.S)
TEAMS = re.compile(r"\s*\[Team_[^\]]*\](?:\[[A-Za-z0-9_ ]+\])*\s*$")

# Header lines (no level, no tag)
BUILD = re.compile(r'BackupNameAttachment=" Build\((\d+)\)')
FILEVER = re.compile(r"^FileVersion: ([\d.]+)")
CPU = re.compile(r"^Host CPU: (.+)$")
THREADS = re.compile(r"^Logical CPU Count: (\d+)")
RAM = re.compile(r"^(\d+)MB physical memory installed")
VRAM = re.compile(r"^\s*- Dedicated video memory: (\d+) MB")
GPU_BENCH = re.compile(r"^GPU benchmark: ([\d.]+) ms")
CPU_BENCH = re.compile(r"^CPU benchmark: ([\d.]+) ms \(int\+mem\), ([\d.]+) ms")
GPU_NAME = re.compile(r"^VulkanMetric - Device \(([^)]+)\) \[GPU \(Discrete\)\]")

# Tagged events
JOIN_PU = re.compile(r"address\[([^\]]*)\] port\[(\d+)\] shard\[([^\]]+)\]")
DISCONNECT = re.compile(r'cause=(\d+) reason="([^"]*)".*?isRemote=(\d)(?: viewState=(\w+))?')
NOTIFY = re.compile(r'Added notification "(.*?)" \[\d+\] to queue.*?MissionId: \[([0-9a-f-]+)\]'
                    r'(?:, ObjectiveId: \[([^\]]*)\])?', re.S)
QUIT = re.compile(r"cause=(\d+), reason=([^,]*), exitCode=(-?\d+)")
END_MISSION = re.compile(r"MissionId\[([0-9a-f-]{36})\].*?CompletionType\[(\w+)\] Reason\[([^\]]*)\]")
MISSION_ENDED = re.compile(r"mission_id ([0-9a-f-]{36}) - mission_state (MISSION_STATE_\w+)")
OBJECTIVE_UPSERT = re.compile(r"mission_id ([0-9a-f-]{36}) - objective_id (\S+) - state (MISSION_OBJECTIVE_STATE_\w+)")
PLAYER_LEFT = re.compile(r"mission_id ([0-9a-f-]{36})")
PU_LOADED = re.compile(r'establisher="CReplicationModel" runningTime=([\d.]+) map="[^"]*" gamerules="([^"]*)"')
PLATFORM = re.compile(r"Loading Platform Manager \[([^\]]+)\] Platform state changed to (\w+)")
UNSTOW = re.compile(r"Processed bindings into transfer request - Entities: (\d+)")
LOGIN = re.compile(r"Handle\[([^\]]+)\]")
# Travel and places (the player's own ship is named before its [entity id]; AI ships have _AI_ in the name)
QT_TARGET = re.compile(r"\|\s*([A-Za-z][A-Za-z0-9_]*?)_\d+\[\d+\]\|CSCItemNavigation::OnPlayerSelectedQuantumTarget\|"
                       r"Player has selected point (\S+) as their destination")
QT_ARRIVED = re.compile(r"\|\s*([A-Za-z][A-Za-z0-9_]*?)_\d+\[\d+\]\|CSCItemNavigation::OnQuantumDriveArrived")
LOCATION = re.compile(r"requested inventory for Location\[([^\]]+)\]")
ATC_SHIP = re.compile(r"ATC '([A-Za-z][A-Za-z0-9_]*?)_ShipATCDataManager")
ARMISTICE = re.compile(r"^(Entering|Leaving) Armistice Zone", re.I)

# Crash block: written without timestamps after the last line
CRASH_START = re.compile(r"^Cloud Imperium Games public crash handler taking over")
CRASH_EXC = re.compile(r"^Exception (\w+)\((0x[0-9A-Fa-f]+)\) addr=0x[0-9A-Fa-f]+ digest=([0-9a-f]+)")
CRASH_FLAG = re.compile(r"^Is (fatal error|GPU crash|Timeout|out of system memory|out of video memory): (Yes|No)")
CRASH_MEM = re.compile(r"^Process Memory Status: (\d+)MB working set size, (\d+)MB commit size \((\d+)MB peak\), "
                       r"(-?\d+)MB left to commit")

SHUTDOWN_MARKS = ("CCIGBroker::FastShutdown", "Shutting down all force feedback")
ZERO_GUID = "00000000-0000-0000-0000-000000000000"


def parse_ts(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc).timestamp()


def region_of(shard_id):
    """'pub_apse2a_12881860_090' -> 'apse2'."""
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

_HANDLE_SUBS = [
    (re.compile(r"(on entity|owned by) '[^']+'"), r"\1 '<name>'"),
    (re.compile(r"\b(Player|User|player|user):? ?\[?[A-Za-z0-9_-]{3,40}\]?(?=[ ,\[]|$)"), r"\1 <player>"),
    (re.compile(r"^[A-Za-z0-9_-]{3,40}\[\d+\] - "), "<player>[N] - "),
    (re.compile(r'entityName="[^"]*"'), 'entityName="<name>"'),
    (re.compile(r'nickname="[^"]*"'), 'nickname="<name>"'),
]
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


def signature(tag, msg, handles=()):
    """Normalise an error line so the same problem always gives the same key, with no names in it."""
    s = TEAMS.sub("", msg or "")
    for h in handles:
        if h:
            s = s.replace(h, "<me>")
    for rx, rep in _HANDLE_SUBS + _SIG_SUBS:
        s = rx.sub(rep, s)
    return f"{tag or '-'}| {s.strip()[:160]}"


# --------------------------------------------------------------------------
# Reading lines
# --------------------------------------------------------------------------

def records(lines):
    """Raw log lines -> records, joining multi-line notifications.

    A notification whose text has a line break is written as several lines, each with its own timestamp; the
    continuation lines have no level and no tag. Lines without any timestamp (the crash handler's block at the end)
    come through on their own.
    """
    pending, extra = None, 0
    for line in lines:
        line = line.rstrip("\r\n")
        m = LINE.match(line)
        if pending is not None:
            if m and m.group(2) is None and m.group(3) is None and not re.match(r'^\s+"', m.group(4)) and extra < 8:
                pending += "\n" + m.group(4).strip()
                extra += 1
                if NOTIFY.search(pending):
                    yield pending
                    pending = None
                continue
            yield pending
            pending = None
        if m and m.group(3) == "SHUDEvent_OnNotification" and "Added notification" in line and not NOTIFY.search(line):
            pending, extra = line, 0
            continue
        if line:
            yield line
    if pending is not None:
        yield pending


# kept for older callers
_joined_lines = records


# --------------------------------------------------------------------------
# Record -> event
# --------------------------------------------------------------------------

def parse_line(raw):
    """One record -> event dict, or None for lines we don't use."""
    m = LINE.match(raw)
    if not m:
        return _untimed(raw)
    ts_s, level, tag, msg = m.groups()
    ts = parse_ts(ts_s)
    msg = msg.rstrip()
    if level is None and tag is None:
        return _header(ts, msg)
    if tag == "SHUDEvent_OnNotification" and (n := NOTIFY.search(msg)):
        return _notification(ts, n.group(1), n.group(2), n.group(3))
    if level == "Error" or level == "Warning":
        return {"ts": ts, "kind": "error", "level": level, "tag": tag or "", "text": TEAMS.sub("", msg),
                "sig": signature(tag, msg)}
    if tag == "Join PU" and (j := JOIN_PU.search(msg)):
        sid = j.group(3)
        return {"ts": ts, "kind": "join_pu", "shard_id": sid, "region": region_of(sid),
                "address": j.group(1), "port": int(j.group(2))}
    if tag == "Update Shard Id" and (u := re.search(r"New Shard Id: (\S+)", msg)):
        return {"ts": ts, "kind": "shard_id", "shard_id": u.group(1)}
    if tag == "Channel Disconnected" and (d := DISCONNECT.search(msg)):
        return {"ts": ts, "kind": "disconnect", "cause": int(d.group(1)), "reason": d.group(2),
                "remote": d.group(3) == "1", "view_state": d.group(4), "frontend": 'gamerules="SC_Frontend"' in msg}
    if tag == "SystemQuit" and (q := QUIT.search(msg)):
        return {"ts": ts, "kind": "quit", "cause": int(q.group(1)), "reason": q.group(2).strip(),
                "exit_code": int(q.group(3))}
    if tag == "Context Establisher Done" and (p := PU_LOADED.search(msg)):
        if p.group(2) != "SC_Frontend":
            return {"ts": ts, "kind": "pu_loaded", "seconds": float(p.group(1)), "gamerules": p.group(2)}
        return None
    if tag == "EndMission" and (e := END_MISSION.search(msg)):
        return {"ts": ts, "kind": "mission_end", "mission_id": e.group(1), "result": e.group(2).lower(),
                "reason": e.group(3)}
    if tag == "MissionEnded" and (e := MISSION_ENDED.search(msg)):
        return {"ts": ts, "kind": "mission_state", "mission_id": e.group(1),
                "result": e.group(2).replace("MISSION_STATE_", "").lower()}
    if tag == "ObjectiveUpserted" and (o := OBJECTIVE_UPSERT.search(msg)):
        return {"ts": ts, "kind": "objective_state", "mission_id": o.group(1), "objective_id": o.group(2),
                "state": o.group(3).replace("MISSION_OBJECTIVE_STATE_", "").lower()}
    if tag == "PlayerLeft" and (p := PLAYER_LEFT.search(msg)):
        return {"ts": ts, "kind": "player_left", "mission_id": p.group(1)}
    if tag == "CSCLoadingPlatformManager::OnLoadingPlatformStateChanged" and (p := PLATFORM.search(msg)):
        if "FreightElevator" in p.group(1):
            return {"ts": ts, "kind": "freight_state", "manager": p.group(1), "state": p.group(2)}
        return None
    if tag == "CEntityComponentFreightElevatorUIProvider::FillUnstowRequest" and (u := UNSTOW.search(msg)):
        return {"ts": ts, "kind": "freight_unstow", "entities": int(u.group(1))}
    if tag == "Player Selected Quantum Target - Local" and (q := QT_TARGET.search(msg)):
        return {"ts": ts, "kind": "qt_target", "ship": q.group(1), "dest": q.group(2)}
    if tag and tag.startswith("Quantum Drive Arrived") and (q := QT_ARRIVED.search(msg)):
        if "_AI_" in q.group(1):
            return None                          # an AI ship arriving nearby, not the player
        return {"ts": ts, "kind": "qt_arrived", "ship": q.group(1)}
    if tag == "RequestLocationInventory" and (loc := LOCATION.search(msg)):
        return {"ts": ts, "kind": "location", "code": loc.group(1)}
    if tag == "CEntityComponentShipListProvider::SetVehicleSpawningInformations":
        return {"ts": ts, "kind": "ship_retrieved", "ship": None}
    if tag == "ATC_Reset_VehiclesBeingStoredCleared" and (a := ATC_SHIP.search(msg)):
        return {"ts": ts, "kind": "atc_ship", "ship": a.group(1)}
    if tag == "Legacy login response" and (h := LOGIN.search(msg)):
        return {"ts": ts, "kind": "login", "handle": h.group(1)}
    if (tag and "FastShutdown" in tag) or any(k in msg for k in SHUTDOWN_MARKS):
        return {"ts": ts, "kind": "shutdown"}
    return None


def _untimed(raw):
    if CRASH_START.match(raw):
        return {"ts": None, "kind": "crash"}
    if m := CRASH_EXC.match(raw):
        return {"ts": None, "kind": "crash_info", "exception": m.group(1), "code": m.group(2), "digest": m.group(3)}
    if m := CRASH_FLAG.match(raw):
        return {"ts": None, "kind": "crash_info", "flag": m.group(1), "value": m.group(2) == "Yes"}
    if m := CRASH_MEM.match(raw):
        return {"ts": None, "kind": "crash_info", "working_mb": int(m.group(1)), "commit_mb": int(m.group(2)),
                "left_mb": int(m.group(4))}
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
    (re.compile(r"^Contract Accepted:\s*(.+?)\s*:?\s*$", re.S), "contract_accepted"),
    (re.compile(r"^Contract Complete(?:d)?:\s*(.+?)\s*:?\s*$", re.S), "contract_complete"),
    (re.compile(r"^Contract Failed:\s*(.+?)\s*:?\s*$", re.S), "contract_failed"),
    (re.compile(r"^Contract Shared:\s*(.+?)\s*:?\s*$", re.S), "contract_shared"),
    (re.compile(r"^New Objective:\s*(.+?)\s*:?\s*$", re.S), "objective_new"),
    (re.compile(r"^Objective Complete:\s*(.+?)\s*:?\s*$", re.S), "objective_complete"),
    (re.compile(r"^Objective Failed:\s*(.+?)\s*:?\s*$", re.S), "objective_failed"),
    (re.compile(r"^Objective Withdrawn:\s*(.+?)\s*:?\s*$", re.S), "objective_withdrawn"),
]


def _notification(ts, text, mission_id, objective_id=None):
    text = re.sub(r"<[^>]+>", "", text).strip()
    mid = None if mission_id == ZERO_GUID else mission_id
    if a := ARMISTICE.match(text):
        return {"ts": ts, "kind": "armistice", "on": a.group(1).lower() == "entering"}
    for rx, kind in NOTE_KINDS:
        if m := rx.match(text):
            name = re.sub(r"\s*\n\s*", " ", m.group(1)).strip(" :")
            return {"ts": ts, "kind": kind, "name": name, "mission_id": mid, "objective_id": objective_id or None}
    return {"ts": ts, "kind": "notification", "text": re.sub(r"\s*\n\s*", " ", text).rstrip(": "), "mission_id": mid}


# --------------------------------------------------------------------------
# Sessions
# --------------------------------------------------------------------------

# Disconnect causes that are part of normal play. A 30016 while still spawning is not; the library flags it.
NORMAL_CAUSES = {30010, 30016}


class Session:
    """Everything one Game.log says, built up event by event."""

    def __init__(self, name=""):
        self.name = name
        self.start = None
        self.end = None
        self.build = None
        self.version = None
        self.hardware = {}
        self.handles = []
        self.joins = []
        self.loads = []
        self.disconnects = []
        self.contracts = {}     # mission id -> contract dict
        self.errors = []
        self.notifications = []
        self.freight_cycles = []    # times the freight elevator finished going down (items handed over)
        self.travel = []            # quantum jumps, places, armistice zones, ships retrieved (for the timeline)
        self.quit = None
        self.clean_exit = False
        self.crash = None
        self.events = []
        self._last_platform = {}

    TRAVEL_KINDS = ("qt_target", "qt_arrived", "location", "armistice", "ship_retrieved")

    def add(self, ev):
        if ev is None:
            return
        if ev["kind"] == "atc_ship":
            # ATC lines name ships all the time; one just after a retrieval names the ship that was retrieved
            last = self.travel[-1] if self.travel else None
            if last and last["kind"] == "ship_retrieved" and last["ship"] is None and ev["ts"] - last["ts"] <= 15:
                last["ship"] = ev["ship"]
            return
        self.events.append(ev)
        ts = ev["ts"]
        if ts is not None:
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
        elif k == "login":
            if ev["handle"] not in self.handles:
                self.handles.append(ev["handle"])
        elif k == "join_pu":
            self.joins.append(ev)
        elif k == "pu_loaded":
            self.loads.append(ev)
        elif k == "disconnect":
            self.disconnects.append(ev)
        elif k == "quit":
            self.quit = ev
            self.clean_exit = True
        elif k == "shutdown":
            self.clean_exit = True
        elif k == "crash":
            self.crash = self.crash or {"ts": self.end}
            self.clean_exit = False
        elif k == "crash_info" and self.crash is not None:
            self.crash.update({x: y for x, y in ev.items() if x not in ("ts", "kind", "flag", "value")})
            if "flag" in ev:
                self.crash.setdefault("flags", {})[ev["flag"]] = ev["value"]
        elif k == "error":
            self.errors.append(ev)
        elif k == "freight_state":
            prev = self._last_platform.get(ev["manager"])
            self._last_platform[ev["manager"]] = ev["state"]
            if ev["state"] == "ClosedIdle" and prev == "LoweringPlatform":
                self.freight_cycles.append(ts)
        elif k in ("contract_accepted", "contract_complete", "contract_failed", "contract_shared",
                   "objective_new", "objective_complete", "objective_failed", "objective_withdrawn",
                   "mission_end", "mission_state", "objective_state", "player_left"):
            self._contract(ev)
        elif k == "notification":
            self.notifications.append(ev)
        elif k in self.TRAVEL_KINDS:
            if k == "location":
                prev = next((e for e in reversed(self.travel) if e["kind"] == "location"), None)
                if prev and prev["code"].lower() == ev["code"].lower():
                    return
            if k == "qt_arrived":
                dest = next((e for e in reversed(self.travel) if e["kind"] == "qt_target"), None)
                ev["dest"] = dest["dest"] if dest else None
            self.travel.append(ev)

    def _new_contract(self, mid, name, ts=None):
        c = {"mission_id": mid, "name": name, "accepted": ts, "objectives": {}, "result": "active",
             "ended": None, "end_reason": None, "progress": 0, "shared": False}
        self.contracts[mid] = c
        return c

    def _contract(self, ev):
        k = ev["kind"]
        mid = ev.get("mission_id") or f"name:{ev.get('name')}"
        c = self.contracts.get(mid)
        if k in ("contract_accepted", "contract_shared"):
            if c is None or c["result"] != "active":
                c = self._new_contract(mid, ev["name"], ev["ts"])
            c["shared"] = c["shared"] or k == "contract_shared"
            return
        if c is None:
            if k in ("contract_complete", "contract_failed"):
                c = self._new_contract(mid, ev["name"])
            else:
                return
        if k.startswith("objective_") and k != "objective_state":
            key = ev.get("objective_id") or re.sub(r"^\w+ \d+/(\d+)", r"\1", ev["name"])
            state = k.split("_", 1)[1]
            o = c["objectives"].setdefault(key, {"text": ev["name"], "state": "open", "ts": ev["ts"]})
            if state == "new":
                o["text"] = ev["name"]
            else:
                o["state"] = state
                o["ts"] = ev["ts"]
                c["progress"] += 1
        elif k == "objective_state":
            c["progress"] += 1
            o = c["objectives"].get(ev["objective_id"])
            if o is not None and ev["state"] in ("completed", "failed"):
                o["state"] = "complete" if ev["state"] == "completed" else "failed"
        elif k in ("contract_complete", "contract_failed"):
            c["result"] = "complete" if k == "contract_complete" else "failed"
            c["ended"] = ev["ts"]
        elif k in ("mission_end", "mission_state"):
            res = {"complete": "complete", "completed": "complete", "fail": "failed", "failed": "failed",
                   "abandon": "abandoned", "abandoned": "abandoned"}.get(ev["result"], ev["result"])
            if c["result"] == "active" or res != c["result"]:
                c["result"] = res
                c["ended"] = ev["ts"]
                c["end_reason"] = ev.get("reason") or c["end_reason"]
        elif k == "player_left" and c["result"] == "active":
            c["result"] = "dropped"
            c["ended"] = ev["ts"]
            c["end_reason"] = "Left the server"

    @property
    def shard_id(self):
        return self.joins[-1]["shard_id"] if self.joins else None

    def load_seconds(self):
        if self.loads:
            return round(self.loads[0]["seconds"])
        if self.start and self.joins:
            return round(self.joins[0]["ts"] - self.start)
        return None

    def summary(self):
        bad = [d for d in self.disconnects if d["cause"] not in NORMAL_CAUSES
               or (d["cause"] == 30016 and d.get("view_state") not in (None, "eCVS_InGame") and not d["frontend"])]
        return {
            "name": self.name, "start": self.start, "end": self.end, "build": self.build, "version": self.version,
            "shard_id": self.shard_id, "region": region_of(self.shard_id), "joins": len(self.joins),
            "shards": list(dict.fromkeys(j["shard_id"] for j in self.joins)),
            "load_s": self.load_seconds(), "minutes": round((self.end - self.start) / 60, 1) if self.start else 0,
            "disconnects": [{"cause": d["cause"], "reason": d["reason"], "ts": d["ts"], "view_state": d.get("view_state")}
                            for d in self.disconnects],
            "bad_disconnects": len(bad), "errors": len(self.errors), "clean_exit": self.clean_exit,
            "crash": self.crash, "quit": self.quit,
            "contracts": list(self.contracts.values()), "hardware": self.hardware,
            "freight_cycles": len(self.freight_cycles),
        }


def parse_file(path, name=None):
    s = Session(name or Path(path).name)
    with open(path, encoding="utf-8", errors="replace") as f:
        for raw in records(f):
            s.add(parse_line(raw))
    return s


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
        self.buffer = []
        self.buffer_since = None
        self.decoder = None
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
        same = ident == self.ident or bool(self.ident and ident and ident.startswith(self.ident))
        if same and ident:
            self.ident = ident
        if not same or size < self.pos or self.session is None:
            self.ident = ident
            self.pos = 0
            self.partial = ""
            self.buffer = []
            self.buffer_since = None
            self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
            self.session = Session(self.path.name)
            if self.on_new_session:
                self.on_new_session(self.session)
        if size == self.pos:
            # A held-back notification gets a few seconds for its second line before it's read as it is
            if self.buffer and time.time() - (self.buffer_since or 0) > 3:
                self._feed(self.buffer, final=True)
                self.buffer = []
            return 0
        with open(self.path, "rb") as f:
            f.seek(self.pos)
            data = f.read(size - self.pos)
        self.pos = size
        text = self.partial + self.decoder.decode(data)
        lines = text.split("\n")
        self.partial = lines.pop()
        # Hold back the last few lines: a notification may still be waiting for its continuation
        lines = self.buffer + lines
        keep = 0
        for i in range(len(lines) - 1, max(-1, len(lines) - 10), -1):
            if "SHUDEvent_OnNotification" in lines[i] and not NOTIFY.search(lines[i]):
                first = next(records(lines[i:]), "")
                if not NOTIFY.search(first):          # its second line hasn't arrived yet
                    keep = len(lines) - i
                break
        self.buffer = lines[len(lines) - keep:] if keep else []
        self.buffer_since = time.time() if keep else None
        self._feed(lines[:len(lines) - keep] if keep else lines)
        return len(lines)

    def _feed(self, lines, final=False):
        if not lines:
            return
        for rec in records(lines):
            ev = parse_line(rec)
            if ev:
                if ev["ts"] is None:
                    ev["ts"] = self.session.end
                self.session.add(ev)
                if self.on_event:
                    self.on_event(ev, rec)

    def run(self, stop, every=1.0):
        while not stop.is_set():
            try:
                self.poll()
            except Exception:
                pass
            stop.wait(every)
