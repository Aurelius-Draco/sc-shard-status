# Game.log findings for the parser (corpus analysis, 29 Oct 2026)

Corpus: 76 Game.log files from one player's PC, 117 hours of play.
Builds 12572603 (4 logs, 13-16 Sep), 12660092 (12 logs, 18 Sep - 3 Oct), 12913470 = 4.10.2 (60 logs incl. today's Game.log, 15-29 Oct).
All regexes below were run over the whole corpus; counts are corpus totals. Analysis scripts:
`/tmp/claude-0/-home-claude/467c16f5-812d-556d-9975-f55393710747/scratchpad/corpus/` (`ev.py` holds every regex in this file as Python).

Placeholders in examples: `<HANDLE>` local player, `<OTHER>` another player, `<GEID>` player entity id,
`<ACCT>` account id, `<ID>` entity/item id, `<GUID>`, `<HEX32>` 32-hex session id, `<IP>`, `<PCNAME>`, `<WINUSER>`.

---

## 1. Line format and things the current `logparse.py` gets wrong

```
<2026-10-29T01:37:13.868Z> [Notice] <Join PU> address[<IP>] port[64378] shard[pub_apse2a_12881860_090] locationId[562954248454145] [Team_GameServices][GIM][Matchmaking]
```

* Levels seen: `Notice` (455k), `Error` (227,649), `Trace` (456), `Debug` (3). **No `[Warning]` level exists in any of the 76 logs.**
  There are untagged `Warning in EntitySpawnBatch ...` lines (no level, no tag; harmless ship-interior data warnings).
* Other bracket "levels" the LINE regex picks up as level: `[CIG]`, `[AUDIOREQ]`, `[CVARS]`, `[+]`. Harmless, but note
  `<ts> [CIG] CCIGBroker::FastShutdown` arrives as level=`CIG`, tag=None.
* **Bug 1: `[SPAM n]` prefix.** 13,370 lines look like `<ts> [SPAM 179][Notice] <Tag> ...` and 338 of them are `[SPAM n][Error]`.
  The current `LINE` fails them (level=None, tag=None). Fix: insert `(?:\[SPAM \d+\])?` before the level group:
  ```python
  LINE = re.compile(r"^<(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?)Z>\s?(?:\[SPAM \d+\])?(?:\[(\w+)\] )?(?:<((?:[^<>]|<[^<>]*>){1,160})> ?)?(.*)$")
  ```
* **Bug 2: multi-line notifications carry timestamps on every line.** The notification text can contain newlines, and the
  game writes each continuation line with its own `<ts>` prefix and no level/tag, e.g.
  ```
  <ts> [Notice] <SHUDEvent_OnNotification> Added notification "Objective Complete: Go to Asteroid Mining Base
  <ts> : " [20] to queue. New queue size: 1, MissionId: [<GUID>], ObjectiveId: [...] [Team_CoreGameplayFeatures][Missions][Comms]
  ```
  `_joined_lines` only joins lines *without* a timestamp, so 911 of 6,339 notifications are lost, including **all 237
  "Objective Complete" and both "Objective Failed"** (they always end in `\n: `). Fix: when a `SHUDEvent_OnNotification` line has
  an unclosed quote (NOTIFY doesn't match), keep appending following lines that have **no level and no tag** (strip their
  `<ts> `) until NOTIFY matches (max ~8 lines). Lines that do have a level/tag end the wait and are parsed normally.
  Also ignore the queue-dump lines `<ts>    "Text: " [n]` (no level, no tag): they repeat every queued notification.
* **Bug 3: crash handler block.** After a crash the game appends ~40 lines with no timestamp (see section 5). `_joined_lines`
  glues them onto the last timestamped line (up to 20,000 chars), so `Exception EXCEPTION_ACCESS_VIOLATION...` ends up inside
  some random Notice line's message and the tag-specific library rules win. Stop joining at a blank line, and emit a `crash` event
  from the block (or feed each block line to `library.match(None, "", line)` so the `crash-*` rules fire).
* `TEAMS` (new version) is correct for every trailing tag group in the corpus.
* Tags with nested `<lambda_1>` now parse in full; the library uses the full tag text.
* Region code `ape1` (7 joins, server IPs in 34.80.0.0/15) is missing from `REGION_NAMES`; that IP range is Google Cloud asia-east1
  (Taiwan), so "Asia East" is a fair label but unconfirmed. Seen: `apse2a` 98 joins, `ape1a` 7, `euw1b` 2, `use1b` 1.

## 2. Regexes for the SPEC Event kinds

All tested. `msg` = message after the tag with trailing `[Team_..][..]` removed (TEAMS). Header lines have no level and no tag.

| kind | where | regex (Python) | count |
|---|---|---|---|
| log_start | header | `BackupNameAttachment=" Build\((\d+)\)` | 76 |
| log_start.version | header | `^FileVersion: ([\d.]+)` | 76 (4.10.197.2878 on 12913470) |
| hardware.cpu | header | `^Host CPU: (.+)$` | 76 |
| hardware.threads | header | `^Logical CPU Count: (\d+)` | 76 |
| hardware.ram_mb | header | `^(\d+)MB physical memory installed` | 76 |
| hardware.vram_mb | header | `^\s*- Dedicated video memory: (\d+) MB` | 76 (3 adapters listed: dGPU, iGPU 485 MB, Basic Render 0 MB; the first is the render device here; safer to take the adapter followed by `- Suitable rendering device: yes`) |
| hardware.gpu | header | `^VulkanMetric - Device \(([^)]+)\) \[GPU \(Discrete\)\]` | 76 |
| hardware bench | header | `^GPU benchmark: ([\d.]+) ms`, `^CPU benchmark: ([\d.]+) ms \(int\+mem\), ([\d.]+) ms` | 76 |
| join_pu | tag `Join PU` | `address\[(?P<address>[^\]]*)\] port\[(?P<port>\d+)\] shard\[(?P<shard_id>[^\]]+)\] locationId\[(?P<location_id>-?\d+)\]` | 108 |
| disconnect | tag `Channel Disconnected` | `cause=(?P<cause>\d+) reason="(?P<reason>[^"]*)" frame=\d+ isRemote=(?P<remote>\d) viewState=(?P<view_state>\w+) map="(?P<map>[^"]*)" gamerules="(?P<gamerules>[^"]*)".*?uptime_secs=(?P<uptime>[\d.]+)` | 310 |
| notification | tag `SHUDEvent_OnNotification` | `Added notification "(?P<text>.*?)" \[(?P<n>\d+)\] to queue\. New queue size: \d+, MissionId: \[(?P<mission_id>[0-9a-f-]{36})\], ObjectiveId: \[(?P<objective_id>[^\]]*)\]` (re.S, after joining, see Bug 2) | 6,339 |
| contract_accepted | notification text | `^Contract Accepted:\s+(?P<name>.+?):\s*$` | 270 |
| objective_new | notification text | `^New Objective:\s+(?P<name>.+?)\s*:\s*$` | 652 |
| contract_ended (preferred source) | tag `EndMission` | `MissionId\[(?P<mission_id>[0-9a-f-]{36})\] Player\[[^\]]*\] PlayerId\[\d+\] CompletionType\[(?P<result>\w+)\] Reason\[(?P<reason>[^\]]*)\]` | 214: Complete 196, Fail 10, Abandon 8 |
| error | level Error | any line with level `Error` | 227,649 |

Example lines:
```
<ts> BackupNameAttachment=" Build(12913470) 29 Oct 26 (11 36 33)"  -- used by backup system
<ts> [Notice] <Channel Disconnected> cause=30016 reason="Remote Disconnect - Player requested disconnect" frame=67228 isRemote=1 viewState=eCVS_InGame map="megamap" gamerules="SC_Default" hostType="Replicant" remoteAddr=<IP>:64378 localAddr=0.0.0.0:64090 connection={3, 0} session=<HEX32> node_id=<GUID> nickname="<HANDLE>" playerGEID=<GEID> uptime_secs=704.946289
<ts> [Notice] <SHUDEvent_OnNotification> Added notification "Contract Accepted:  Very Hungry: " [25] to queue. New queue size: 3, MissionId: [<GUID>], ObjectiveId: []
<ts> [Notice] <SHUDEvent_OnNotification> Added notification "New Objective: Need 0/1 of Berry Blend Smoothie: " [26] to queue. New queue size: 4, MissionId: [<GUID>], ObjectiveId: [dropoff_<GUID>_0]
<ts> [Notice] <EndMission> Ending mission for player. MissionId[<GUID>] Player[<HANDLE>] PlayerId[<GEID>] CompletionType[Abandon] Reason[Player left]
```

**Check of `NOTE_KINDS` against the real wording:**
* `Contract Accepted:  Name: ` has **two** spaces after the colon; `Contract Complete: Name: ` has one. `\s*` handles both. OK.
* `Contract Complete:` (196) and `Contract Failed:` (10) exist. **`Contract Completed`, `Contract Abandoned`, `Withdrawn`,
  `Cancelled` never appear.** Abandoning shows no notification at all; use `EndMission ... CompletionType[Abandon]` (8) and
  `PlayerLeft` push lines (30). So `contract_abandoned` from notifications never fires.
* `Objective Complete: Text\n: ` (237), `Objective Failed: Text\n: ` (2), `Objective Withdrawn: Text: ` (28) are the real
  forms; the first two only parse after the Bug 2 fix. Strip the trailing `\n:`.
* **`Contract Shared:` is not a result** (a party member shared a contract with you; 32). The Session currently sets
  `result = "shared"` on 16 contracts. Treat it as its own kind, or as an accept.
* `Contract Available:` (40, e.g. RSI rental offers) is not an accept either.
* Names can contain `<EM4>[100 Rep]</EM4>` (strip tags, already done) and double quotes, e.g. `Preemptive Strike On Benny "Any-port" Janney`.
  The lazy `(.*?)" \[\d+\] to queue` still works.
* Objective progress is never in a notification until it completes. The authoritative progress feed is
  `ObjectiveUpserted ... state MISSION_OBJECTIVE_STATE_*` and the end feed is `MissionEnded ... MISSION_STATE_COMPLETED|FAILED`.
* Different Wikelo contracts reuse the same objective ids (Very Hungry and Test Armor both use `dropoff_8cabaa26-..._0/_1`), so key
  objectives by mission id + objective id, never objective id alone.

**`SHUTDOWN_MARKS`** (`CCIGBroker::FastShutdown`, `Shutting down all force feedback`) are correct: present in all 70 clean logs and
absent from all 6 crashed ones. `<SystemQuit> CSystem::Quit invoked with - cause=30016, reason=Quit via console command, exitCode=0`
is a better primary marker (70/70) because it carries the reason and exit code.

## 3. Other events worth tracking

Tag in the first column; regex searched in `msg`. Counts are corpus totals.

| event | tag | regex | count |
|---|---|---|---|
| quit | `SystemQuit` | `cause=(?P<cause>\d+), reason=(?P<reason>[^,]*), exitCode=(?P<exit_code>-?\d+)` | 70 |
| PU load finished | `Context Establisher Done` | `establisher="CReplicationModel" runningTime=(?P<seconds>[\d.]+) map="(?P<map>[^"]*)" gamerules="(?P<gamerules>[^"]*)"` (ignore `SC_Frontend`; `SC_Default` = PU, `EA_*` = Arena Commander) | 225 (109 non-frontend) |
| load stuck | `CContextEstablisherTaskLongWait` | `taskname="(?P<task>[^"]*)" state=(?P<state>\w+)\(\d+\) status="(?P<status>[^"]*)" runningTime=(?P<seconds>[\d.]+)` | 1 |
| in world (spawned) | `Initializing Game Telemetry` | `Initializing game telemetry component of local player` | 157 (also fires after respawn) |
| shard id | `Update Shard Id` | `New Shard Id: (?P<shard_id>\S+)` | 97 |
| login (handle!) | `Legacy login response` | `User Login Success - Handle\[(?P<handle>[^\]]+)\]` | 79 |
| server change | `Change Server Start` / `Change Server End` | `IsShardPersisted\[(\d)\] IsServer\[(\d)\] IsMultiplayer\[(\d)\]` | 226 each |
| contract state (push) | `MissionEnded` | `mission_id (?P<mission_id>[0-9a-f-]{36}) - mission_state (?P<state>MISSION_STATE_\w+)` | 206 |
| objective state (push) | `ObjectiveUpserted` | `mission_id (?P<mission_id>[0-9a-f-]{36}) - objective_id (?P<objective_id>\S+) - state (?P<state>MISSION_OBJECTIVE_STATE_\w+)` | 3,595 |
| removed from contract | `PlayerLeft` | `mission_id (?P<mission_id>[0-9a-f-]{36})` | 30 |
| QT destination chosen | `Player Selected Quantum Target - Local` | `\|\s*(?P<vehicle>[^|\[]+)\[\d+\]\|CSCItemNavigation::OnPlayerSelectedQuantumTarget\|Player has selected point (?P<target>\S+) as their destination` | 341 |
| QT arrived | `Quantum Drive Arrived - Arrived at Final Destination` | `\|\s*(?P<vehicle>[^|\[]+)\[\d+\]\|CSCItemNavigation::OnQuantumDriveArrived` | 243 |
| QT fuel/route request | `Player Requested Fuel to Quantum Target - Server Routing` | `requested fuel calculation to destination (?P<target>\S+)` | 400 |
| QT route failed | `Failed to Calculate Route!` | `last obstruction entity: (?P<obstruction>\S+)` | 2 |
| QT obstructed (on screen) | notification | `^Quantum Travel: Your destination is obstructed` | 21 |
| QT server reroute | `Local Route Guard - Server Rerouted` | `FinalStop=(?P<final_stop>-?\d+)` | 6,025 (routine, every QT) |
| death | `[ActorState] Dead` | `Actor '[^']+' \[\d+\] ejected from zone '(?P<zone>[^']+)'` | 19 |
| incapacitated | notification | `^Incapacitated:` | 11 |
| ship destroyed | `FatalCollision` | `Fatal Collision occured for vehicle (?P<vehicle>\S+) \[Part: (?P<part>[^,]*),.*?Zone: (?P<zone>[^,]*), PlayerPilot: (?P<pilot>\d)` | 16 |
| med bed | `MED BED HEAL` | `Perform surgery event (?P<result>\w+), med bed name: (?P<bed>[^,]+)` | 4 |
| respawn | none found | there is no explicit respawn line; use `Initializing Game Telemetry` after a death | |
| ASOP list | `VehicleListQuery` | `Retrieved (?P<entitlements>\d+) entitlements out of (?P<vehicles>\d+)` | 603 |
| ASOP spawn request | `CEntityComponentShipListProvider::SetVehicleSpawningInformations` | `VehicleEntityId: \[\d+\], LandingArea: (?P<owner>.+)'s` (owner = handle) | 135 |
| hangar ready | notification | `^Hangar Request Completed` | 256 |
| hangar queue | notification | `^Joined hangar queue\.\s*Your place: (?P<place>\d+)\. Max\. estimated wait: (?P<wait>[\d.]+) s` | 6 |
| elevator call | `SCEvtNotify_BuildingBlocksCallCarriage` | `Player (?P<handle>\S+)\[\d+\] triggered the call carriage event` | 83 |
| elevator arrived | `Carriage state changing` | `from \((?P<from>[^)]*)\) to \((?P<to>[^)]*)\) for reason \((?P<reason>[^)]*)\)` | 225 |
| carriage enter/exit | `Player entered carriage` / `Player exited carriage` | `Player (?P<handle>\S+)\[\d+\] entered this carriage` (any player) | 345 each |
| freight elevator transfer | `CEntityComponentFreightElevatorUIProvider::FillUnstowRequest` | `Processed bindings into transfer request - Entities: (?P<entities>\d+)` | 98 |
| freight platform state | `CSCLoadingPlatformManager::OnLoadingPlatformStateChanged` | `Loading Platform Manager \[(?P<manager>[^\]]+)\] Platform state changed to (?P<state>\w+)` (ClosingFrontGate, LoweringPlatform, ClosedIdle, RaisingPlatform, OpeningFrontGate, OpenIdle) | 6,479 |
| item dropped to ground/platform | `Inventory Drop From Container` | `attempt drag and drop to ground item \[\d+\]` | 106 |
| inventory result | `Player Inventory Request Complete` | `Type\[(?P<type>\w+)\] Result\[(?P<result>\w+)\]` (Succeed 8,675 / Failed 58) | 8,733 |
| shop result | `CEntityComponentShoppingProvider::RmShopFlowResponse` | `result\[(?P<result>\w+)\]` (Success 235 / AuthorityError 5) | 240 |
| purchase sent | `CEntityComponentShoppingProvider::SendStandardItemBuyRequest` | `shopName\[(?P<shop>[^\]]+)\].*?client_price\[(?P<price>[\d.]+)\].*?itemName\[(?P<item>[^\]]+)\]` | 236 |
| socket error | `Socket Send Error (Ignore)` | `socket error: (?P<code>\d+) (?P<name>\w+)` | 18 (all WSAENOBUFS, one session) |
| crash block | no timestamp | see section 5 | 6 |

**Load time.** Use `Join PU` -> `Context Establisher Done establisher="CReplicationModel" gamerules="SC_Default"` (`runningTime`
is the PU load in seconds): n=109, median 32 s, 90th percentile 53 s, max 105 s. `Join PU` -> `Initializing Game Telemetry`
gives almost the same (median 28 s). Log start -> first `Join PU` is mostly time in the menu (median 33 s, up to 36 min), so it
is not a load time; report it as "time to join" at most.

**Failed join.** A `Join PU` with no `SC_Default` load finished before the next disconnect/join: exactly 1 in the corpus
(29 Oct 00:24:58, see section 8).

**Server change mid-session.** Each new `Join PU` (or `Update Shard Id`) in the same log is a server change. 18 of 76 logs have
more than one join; 10 changed shard, 6 of them across regions (apse2 -> ape1, euw1, use1).

**Disconnect causes seen (all of them).** Only two codes in 117 hours:

| cause | reason | isRemote | meaning | count |
|---|---|---|---|---|
| 30010 | `Nub destroyed` | 0 | local menu connection closed on joining the PU (normal, logged twice: Replicant + GameClient) | 220 |
| 30016 | `Remote Disconnect - Player requested disconnect` | 1 | normal quit; `SystemQuit` follows within ms | 85 |
| 30016 | `DisconnectCmd: disconnect light ExitToMenu` | 0 | exit to main menu | 4 |
| 30016 | `Remote Disconnect - Player requested disconnect` with `viewState=eCVS_UnstowPlayer`, uptime 12 s, no SystemQuit | 1 | server dropped the client while spawning; next join was a different shard and region | 1 |

`viewState` != `eCVS_InGame` on a 30016 is the useful signal. No 30000-series "30k" codes occur in this corpus.

## 4. Where identifiers appear (for redact.py)

The local player has **two handles** in this corpus (renamed mid-October; same GEID). Collect handles from
`Legacy login response ... Handle[X]`, `nickname="X"` and `AccountLoginCharacterStatus_Character ... name X`, and redact every one.

| what | formats (regex) |
|---|---|
| own handle | `nickname="([^"]+)"`, `Handle\[([^\]]+)\]`, `Player\[([^\]]+)\]`, `Player \[([^\]]+)\]`, `player \[([^\]]+)\]`, `for '([^']+)' ?\[\d+\]`, `'([^']+)' ?\[<GEID>\]`, `User\[([^,\]]+), \d+\]`, `Actor '([^']+)'`, `Actor: (\S+) \(Non-Authoritative CLIENT: (\S+)\)`, `localClient \[([^\]]+)\]`, `on entity '([^']+)'`, `owned by '([^']+)'`, `entityName="([^"]+)"`, `^(\S+)\[\d+\] - CSCLocalPlayer`, `LandingArea: (.+)'s`, `Player: (\S+) ?\[`, `- name (\S+) - state` (character list), ship chat channels `You have joined channel '<Ship> : (<HANDLE>)'` |
| other players | `Player (\S+)\[\d+\] entered this carriage` / `exited`, `User: ([^,]+),` and `Client: ([^,]+),` (QT errors; Client is the local handle), `player \[([^\]]+)\]` (MoveToZoneUnauthorizedInstance), `on entity '([^']+)'` (Too many actions, other players too), notifications: `New Member Joined\n(\S+) has joined`, `Member Left\n(\S+) has left`, `(\S+)\nParty Invite Received`, `(\S+)\nFriend Request`, `Friend Added\n(\S+)`, `New Party Leader\n(.+) is now party leader`, `Invitation Declined\n(\S*) has declined`, `(\S+) wants to send you [\d,]+ UEC`, `(\S+) has sent you`, `You sent (\S+)`, `Quantum Travel Calibration (?:Started\|Complete) By (\S+)`, `(\S+) has started to QT to your current location`, `Crime Committed: .*\nagainst (.+?): `, `You have (?:created\|left the)\ngroup '([^']*)'` (group names are user text) |
| player entity id (GEID, 12 digits) | `playerGEID=(\d+)`, `PlayerId\[(\d+)\]`, `player_id (\d+)`, `playerId\[(\d+)\]`, `geid (\d+)`, `'[^']+' ?\[(\d+)\]`, `Client (\d+)`, `player id: \[(\d+)\]`, `Subscribing to player (\d+)`, `entityId=(\d+)`, `User\[(\d+)\]`, `Request instance info for player (\d+)` (other player), `TrackedEntityId: (\d+)` (party members), `ownerId\[(\d+)\]` (contract sharer) |
| account id (7 digits) | `accountId (\d+)`, `Subscribing player (\d+) to contacts topics` |
| PC name (here it is the player's real name) | `<Hostname> Name: ([^,]+), Hostname: (\S+)` |
| Windows user name | `C:\\Users\\([^\\]+)\\` (crash block, 33 lines) |
| server IPs | `address\[(\d+\.\d+\.\d+\.\d+)\]`, `remoteAddr=(\d[\d.]+):\d+`, `Connecting (\d[\d.]+):\d+!`, `Connection requested to: (\d[\d.]+):\d+`, `ViewName="Replicant (\d[\d.]+):\d+"`, `UDP send of \d+ bytes to (\d[\d.]+):\d+`; generic `\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b` (keep `0.0.0.0`, `127.0.0.1`) |
| home LAN / ISP IPs | `<Network Interfaces>` block (untagged lines after it): `192.168.x.x/22 Private`, IPv6 `[<global v6>]/64 Public` (ISP-assigned, identifying), `[fdcc:...]/64 Private`, `[fe80::...]`. Generic IPv6: `\[[0-9a-fA-F:]{2,39}\]/\d+` |
| session ids | `session=([0-9a-f]{32})`, `sessionId="([^"]+)"`, `@session: +'(<GUID>)'`, `LoginSessionId: (<GUID>)`, `Local: (<GUID>)\. Env`, `TraceID: ([0-9a-f]{32})`, `node_id=(<GUID>)`, `Join PU} \[0\] id\[(<GUID>)\]` |
| invitations, groups | `accept invitation (<GUID>)`, `leave group (<GUID>)` |
| mission ids | `MissionId: \[(<GUID>)\]`, `mission_id (<GUID>)`, `MissionId\[(<GUID>)\]`, `ContractId: \[(<GUID>)\]` (not personal, but unique per player; redact in shared bundles) |
| entity / item ids | 11-12 digit numbers in `[...]` and `_\d{9,}` suffixes on entity names (e.g. `ORIG_m80_905008048783`) |
| shard / server | `shard\[([^\]]+)\]` and the overlay server name are fine to keep (not personal) |

No e-mail addresses, JWTs or passwords appear anywhere in the corpus.

## 5. Crash vs clean exit

Clean (70 logs): the last lines are, within the same second,
```
<ts> [Notice] <Channel Disconnected> cause=30016 ...
<ts> CGame::OnDisconnected Client quitting game
<ts> [Notice] <SystemQuit> CSystem::Quit invoked with - cause=30016, reason=Quit via console command, exitCode=0, ...
<ts> System Fast Shutdown (ExitOnQuit enabled)
<ts> BaseInput - Shutting down all force feedback
<ts> ActionGame - Shutting down all force feedback
<ts> [CIG] CCIGBroker::FastShutdown
```
(`CGame::OnDisconnected` is missing in some clean logs; `SystemQuit` and `FastShutdown` are always there.)

Crash (6 logs, all 4.10.2, about 1 in 10 sessions): the timestamped lines just stop, then an untagged block:
```
Process Memory Status: 13242MB working set size, 35557MB commit size (36260MB peak), 1225MB left to commit
System Memory Status: 31653MB total physical, 5193MB free physical, 49094MB system wide commit limit
=== Level Profile Statistics===  (frames, entities, FPS buckets)
Cloud Imperium Games public crash handler taking over...
Saved dump file to C:\Users\<WINUSER>\AppData\Local\Star Citizen\Crashes\error.dmp (md5=...)
Exception EXCEPTION_ACCESS_VIOLATION(0xC0000005) addr=0x00007FF7E4A370D4 digest=f55b3dd89ac10134a552674d5532a3cb
Is fatal error: No
Is GPU crash: No
Is Timeout: No
Is out of system memory: No
Is out of video memory: No
...
All crash related data successfully handed over to crash info collector process
```
Regexes (no timestamp, search the raw line):
```python
CRASH_START = re.compile(r"^Cloud Imperium Games public crash handler taking over")
CRASH_EXC   = re.compile(r"^Exception (?P<exception>\w+)\((?P<code>0x[0-9A-Fa-f]+)\) addr=0x[0-9A-Fa-f]+ digest=(?P<digest>[0-9a-f]+)")
CRASH_FLAG  = re.compile(r"^Is (?P<flag>fatal error|GPU crash|Timeout|out of system memory|out of video memory|reported bug): (?P<value>Yes|No)")
CRASH_MEM   = re.compile(r"^Process Memory Status: (?P<ws_mb>\d+)MB working set size, (?P<commit_mb>\d+)MB commit size \((?P<peak_mb>\d+)MB peak\), (?P<left_mb>-?\d+)MB left to commit")
```
Decision order for the end of a log: crash block present -> **crash** (exception, digest, flags); else `SystemQuit`/`FastShutdown`
present -> **clean** (report the 30016 reason); else (no marker, file not growing, game not running) -> **killed / frozen / power
loss** (no examples in this corpus). Read the last ~20 KB, not the last line, because the crash block is long.

All 6 crashes were `EXCEPTION_ACCESS_VIOLATION`; digest `f55b3dd8...` repeated 3 times (17, 18, 21 Oct), the other three
were different digests. Memory "left to commit" at crash: 1.2, 8.1, 11.3, 5.9, 4.1, 15.5 GB (the 27 Oct crash had a 45 GB commit and
an `[AUDIOREQ] Audio request queue [HIGH] ... now at 2927.0%` line just before it). None flagged GPU, timeout or out-of-memory.

## 6. Signature normalisation

The library and coverage numbers use the coordinator's `scstatus.logparse.signature(tag, msg)` (current version, imported fresh).
It works, with two weaknesses found on the corpus:

1. **Handles leak into signatures** (would leave the PC in a shared bundle and split one error into several keys): 878 Error lines,
   e.g. `Too many actions| Attempting to queue too many actions (N) on entity '<HANDLE>'`, `owned by '<HANDLE>'!`,
   `<HANDLE>[N] - CSCLocalPlayerNotifications...`, `Attempting to move player [<OTHER>]`, `Player: <HANDLE> [`, `User: <OTHER>,`.
2. Entity class names are kept, so some tags explode into many keys (4.10: `CAttachableComponent::GetPortFromId` 266 keys,
   `Failed attachment` 102, `[Particle System] Kidnapping Child Effect` 102). That's acceptable for grouping (the library matches by
   tag and regex, not by sig), so I haven't changed it.

Suggested fix for 1 (tested: zero handles left in any Error signature; 880 -> 875 distinct signatures):
```python
_HANDLE_SUBS = [
    (re.compile(r"(on entity|owned by) '[^']+'"), r"\1 '<name>'"),
    (re.compile(r"\b(Player|User|player|user):? ?\[?[A-Za-z0-9_-]{3,40}\]?(?=[ ,\[]|$)"), r"\1 <player>"),
    (re.compile(r"^[A-Za-z0-9_-]{3,40}\[\d+\] - "), "<player>[N] - "),
    (re.compile(r'entityName="[^"]*"'), 'entityName="<name>"'),
]

def signature(tag, msg, handles=()):
    """handles = the local player's known handles (from the login lines)."""
    s = TEAMS.sub("", msg or "")
    for h in handles:
        if h:
            s = s.replace(h, "<me>")
    for rx, rep in _HANDLE_SUBS:
        s = rx.sub(rep, s)
    for rx, rep in _SIG_SUBS:          # the existing substitutions, unchanged
        s = rx.sub(rep, s)
    return f"{tag or '-'}| {s.strip()[:160]}"
```

## 7. Corpus summary (sanity checks)

| | 12572603 | 12660092 | 12913470 (4.10.2) | all |
|---|---|---|---|---|
| sessions (logs) | 4 | 12 | 60 | 76 |
| PU joins | 4 | 19 | 85 | 108 |
| Error lines | 45,049 | 9,374 | 173,226 | 227,649 |
| of which `[SPAM n][Error]` | 169 | 0 | 169 | 338 |
| clean exits | 4 | 12 | 54 | 70 |
| crashes | 0 | 0 | 6 | 6 |

* Play time 117 h; session length median 71 min, longest 6 h.
* Joins per log: 1 join 58 logs, 2 joins 12, 3+ joins 6. Shards seen 22; regions apse2a 98, ape1a 7, euw1b 2, use1b 1.
* PU load (CReplicationModel runningTime): median 32 s, p90 53 s, max 105 s (18 Oct 09:53). One `CContextEstablisherTaskLongWait`
  (`RequestAndWaitForOCHierarchyData`, 60 s, 17 Oct).
* Disconnects: see table in section 3. Only one abnormal one (29 Oct).
* Contracts: 270 accepted notifications (248 unique missions), 196 Complete, 10 Failed, 8 Abandoned (`EndMission`), 34 still open
  at log end. Objectives: 652 new, 237 complete, 28 withdrawn, 2 failed. 32 contracts shared by party members.
* Other: 341 QT targets, 243 QT arrivals, 21 "destination obstructed", 2 route failures; 19 deaths, 11 incapacitations,
  16 ships destroyed by collision; 135 ASOP spawn requests, 6 hangar queues, 1 ATC timeout; 83 elevator calls; 98 freight elevator
  transfers; 58 failed inventory requests (14 Move, 12 StackAll, 9 QueryInventory, 6 Interaction, 6 AmmoRepool, ...);
  5 shop AuthorityErrors; 18 WSAENOBUFS socket errors (one session, 17 Oct).
* Running the current `logparse.parse_file` over the corpus gives: 227,311 errors (338 SPAM lines missed), 4,240 plain
  notifications + 1,188 typed ones (911 multi-line notifications lost), objective_complete 0, clean_exit 70, contract results
  `active 42, complete 196, failed 10, shared 16`.

## 8. The Wikelo "Very Hungry" case (28-29 Oct)

Very Hungry needs 1 Berry Blend Smoothie (`Drink_bottle_smoothie_01_a`) and 1 Ermer Family Farms Fat Free Ice Cream
(`Food_icecream_eff_01_fatfree_a`), handed in through the freight elevator at a Wikelo station (`..._HangarXL_Rund_Collector`).
The log shows the item classes were right (global.ini maps both class names exactly).

Accepted 5 times: 28 Oct 05:28 and 06:48 UTC, 29 Oct 00:08, 00:13 and 00:39 UTC. None completed. What the logs show:

1. **The items reached the elevator and the elevator cycled, but the server never registered them.** Each attempt is:
   drop items on the platform -> `ClosingFrontGate -> LoweringPlatform -> ClosedIdle` -> no `ObjectiveUpserted` for the Very Hungry
   mission at all -> the player opens the kiosk and gets the items back (`FillUnstowRequest ... Entities: 2`, platform rises).
   The same player's **Wikelo Arrive to System** delivery on 28 Oct 03:28 followed exactly the same steps and the server sent
   `ObjectiveUpserted ... MISSION_OBJECTIVE_STATE_COMPLETED` 1 second after `ClosedIdle`, then `Contract Complete`.
2. **`FindBoxSize ... does not have a resource container` is a correlate, not proven cause.** It fired on 4 of the 5 Very Hungry
   hand-ins, but it also fired for Vestal Water in the Arrive to System delivery that *did* count, and it did not fire on the
   first 29 Oct hand-in (00:10), which still failed. The library rule therefore says "check the objective counter" rather than
   "this is why it failed".
3. **29 Oct had a server change mid-attempt.** 00:13:48 the first contract was abandoned (`EndMission CompletionType[Abandon]
   Reason[Player left]`) and re-accepted 6 s later. At 00:24:47 the player exited to menu, rejoined the same shard (apse2a_090),
   and 12 s later the server dropped the connection while still spawning (30016, `viewState=eCVS_UnstowPlayer`). The next join went
   to a different region and shard (`pub_ape1a_12881860_090`). Contract 2 vanished without any end line (it was accepted again at
   00:39 as contract 3).
4. **Items were left on the old shard.** The smoothie and ice cream sent at 00:12-00:13 on apse2a stayed in that elevator.
   On the new shard, at 01:05:27 the kiosk built a request that included both of them:
   `FillUnstowRequest [FreightElevatorKioskUIProvider] EntityId[<ID>] is not present.` (twice), `Entities: 4`.
   That error is a symptom of the shard change, not the reason the objective didn't count (attempt 1 failed before it).
5. **Leaving the server drops Wikelo contracts.** 28 Oct 06:47:56, 2 s after a normal quit-to-menu, `PlayerLeft` arrived for all
   three active Wikelo contracts (Very Hungry, Test Armor, What is Terrapin?) and Very Hungry had to be accepted again.
6. On 28 Oct, Test Armor and Very Hungry were active at the same time and **share objective ids** (`dropoff_8cabaa26-..._0` and `_1`).
   Test Armor was accepted after the first failed hand-ins, so it isn't the cause there, but it's a likely source of confusion
   for any tool (or server) that keys on objective id.
7. The last 29 Oct contract was still open when the player quit at 01:33 (no end line). The game also logs
   `Comms Bindings Init ... MCN_Collector_FoodMissionAccept has no DNA component` on every accept (cosmetic).

Plain-English conclusion for the player: the elevator took the food and drink but the server never counted them, on two
separate days and two shards, while a different Wikelo delivery through the same elevator type worked. That points at the
Very Hungry objective itself (or food and drink items specifically) rather than anything the player did. Changing server
mid-attempt then stranded the items on the old shard. It needs an Issue Council report; the library's
`cargo-no-resource-container`, `freight-entity-not-present` and `disconnect-30016-spawn` rules will surface the pieces.

## 9. Library notes

* `scstatus/library/issues.json`: 110 rules (38 problem, 13 info, 59 noise). Every regex compiles, every non-general rule matches
  the corpus, `builds_seen` is computed from the corpus.
* **General-knowledge rules** (not seen in the data, `builds_seen: []`, `"general_knowledge": true`): `crash-out-of-memory`,
  `crash-gpu`. Every crash here had those flags at `No`. No generic "unexpected disconnect code" rule was added because
  `diagnose._disconnects` already reports any cause outside `NORMAL_CAUSES`; note that it will *also* report
  `disconnect-30016-spawn` lines unless it checks the library first (it only skips when a rule id is exactly `disconnect-<cause>`,
  and `disconnect-30016` exists, so 30016 is skipped; good, but keep that in mind if the info rule is ever removed).
* The crash and `[AUDIOREQ]` rules need the parser to pass those lines in (section 1, Bug 3). The `[AUDIOREQ]` line parses as
  level `AUDIOREQ` with no tag, so `diagnose` already sees it.
* Coverage: 100% of Error lines in every build are matched by some rule (173,226 of 173,226 in 4.10; 754 distinct 4.10 signatures).
  That is because most noise rules match on the tag alone; a new message under a noisy tag (e.g. `Failed attachment`) will be
  treated as noise. Problem rules always use a specific regex. With the current parser (SPAM lines invisible) coverage is also 100%
  of the 173,057 lines it sees.
* Untagged lines with no level (`Streamable ... has failed streaming 3 times` 283k, `Warning in EntitySpawnBatch` 3.8k) are
  never passed to the library by `diagnose`, so they have no rules.
