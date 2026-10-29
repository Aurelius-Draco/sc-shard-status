# SC Shard Status v1: build spec

Working name: **SC Shard Status** (package `scstatus`). A free community tool by Aurelius_Draco for Star
Citizen players. Sister app to SC Inventory Tracker (github.com/Aurelius-Draco/sc-inventory-tracker):
same structure, same look, separate app.

## What it does (v1, runs on the player's Windows PC)

1. **Live shard health.** Reads the game's own debug overlay (`r_displayinfo 3`, top right of the screen)
   with OCR every few seconds: server FPS and range, server frame time, hitches, restarts, shard and
   server population, ping, packet loss, bandwidth, replication-layer stats, client FPS. Gives a 0-100
   health score and a plain-English summary.
2. **Session tracking from Game.log.** Shard joined, region, server address, build, load time,
   disconnects with cause codes, contracts and objectives, errors. Hardware from the log header.
3. **"What's gone wrong?"** Scans the last N minutes of log + overlay readings, matches a known-issues
   library, explains each finding in plain English with fixes, and drafts an Issue Council report.
4. **History.** Per-shard and per-session stats, best times and shards.
5. **Community-ready exports (no network in v1).** A redacted "send for review" bundle and a
   community snapshot format, so v2 can add the live service without changing the core.

Hard rules (same as the tracker): read-only. Screen capture + Game.log + global.ini only. No memory
reading, no network interception, no input automation. Player handle, account ids, session ids, IP
addresses and other players' handles never leave the PC except in an Issue Council report the player
submits themselves.

Writing style for every user-facing string: plain direct Australian English, no em dashes, no hype.

## Facts established from real data (4.10.2, Oct 2026)

Overlay block (r_displayinfo 2/3/4 look the same in 4.10), example lines:
```
Session: b360e83b-5c9c-c24f-b80f-4977ca855a2c
ShardId: pub apse2a 12881860 090
FPS 106.3 [72..144], - 10.3ms [7.1ms]
Server FPS 21.8 [21.2..22.3] - 45.9ms [44.8..47.3], Hitches: 0
Server: pub-apse2a-sc-alpha-4102-12974691-game-07, restarts 0, pop. [shard 435, srv 34]
Net: ping 24.4ms, loss 0.0% BwIn 222.221kbps, BwOut 50.556kbps
RL: entities: 17295, tick: 0.26ms, MTSync: 0.97ms
ServerTime: Thu Oct 29 01:41:36 2026
Working Set (OS): 13.14 GiB Committed (OS): 24.89 GiB
VRAM(MB): 9250 / 15423
Current player location : RR_CRU_L4  (LZ : RR_CRU_L4)
Entities: 20536, ...
```
Healthy 4.10 server FPS is about 20-22. The block sits at the top right; when the session QR code is on
(r_DisplaySessionInfo 1) the block shifts left to make room.

Session QR decodes to: `<session guid> <shard id> <unix time> <env>`, e.g.
`b360e83b-... pub_apse2a_12881860_090 1793238464 pub-sc-alpha-4102-12881860`.

Game.log (UTC timestamps `<2026-10-29T01:37:13.868Z>`):
- `<Join PU> address[34.87.201.204] port[64378] shard[pub_apse2a_12881860_090] locationId[...]`
- `<Channel Disconnected> cause=30016 reason="Remote Disconnect - Player requested disconnect" ...`
  (30010 "Nub destroyed" = normal frontend to PU transition; 30016 = player quit)
- `Host CPU: AMD Ryzen 7 9800X3D 8-Core Processor`, `Logical CPU Count: 16`,
  `31653MB physical memory installed`, `- Dedicated video memory: 16191 MB`,
  `GPU benchmark: 24.37 ms`, `CPU benchmark: 27.48 ms (int+mem), 23.41 ms (fp+mem)`,
  `VulkanMetric - Device (AMD Radeon RX 9070) [GPU (Discrete)]`
- `FileVersion: 4.10.197.2878`, `BackupNameAttachment=" Build(12913470) ..."`
- Contracts: `<SHUDEvent_OnNotification> Added notification "Contract Accepted:  Very Hungry: " [25] ...
  MissionId: [873ac79a-...]`, `"New Objective: Need 0/1 of Berry Blend Smoothie: "`
- Known real problem (Wikelo "Very Hungry"): `<CargoSystemUtilities::FindBoxSize> Item class
  [Drink_bottle_smoothie_01_a] does not have a resource container`, and
  `<CEntityComponentFreightElevatorUIProvider::FillUnstowRequest> ... EntityId[907731241777] is not present.`
  The objectives never progressed. Item class -> display name comes from global.ini
  (`item_NameDrink_bottle_smoothie_01_a=Berry Blend Smoothie`).
- Lines carry the player handle (e.g. `'Aurelius_Draco'[770469245981]`, `Player[Aurelius_Draco]`),
  account/entity ids, session GUIDs, IPs, friend and party member handles. All must be redactable.
- Lines are `<ts> [Level] <Tag> message [Team_X][Area]...`; levels seen: Notice, Error, Warning, Trace.

## Package layout

```
scstatus/
  config.py      VERSION, HERE, DATA, load_config(), find_game_dir(), say()   (pattern from tracker)
  logparse.py    parse lines -> Event; parse_file(); LogTail (live follow, handles a new Game.log)
  names.py       global.ini item class -> display name
  overlay.py     OCR overlay reader: find_block(img) / read(img) -> Snapshot dict; parse_lines(lines)
  capture.py     screen grab loop (mss, dxcam on Windows) feeding overlay.read
  issues.py      known-issues library: load, classify error lines, correlation rules
  diagnose.py    what's gone wrong: findings for a time window
  score.py       health score + plain-English summary from snapshots
  store.py       SQLite: sessions, snapshots, events, findings, reviews
  redact.py      strip identifiers
  report.py      Issue Council draft + report folder
  dashboard.py   localhost web page (token, 127.0.0.1 only), static/index.html
  app.py, cli.py
  library/issues.json   the known-issues library (data, updated without app releases)
```

## Interfaces

### Snapshot (overlay reading), a dict
```
ts (float, unix, local capture time)
shard_id (str "pub_apse2a_12881860_090" normalised with underscores) | None
server_name (str "pub-apse2a-sc-alpha-4102-12974691-game-07") | None
server_fps, server_fps_min, server_fps_max (float) | None
server_ms, server_ms_min, server_ms_max (float) | None
hitches, restarts (int) | None
pop_shard, pop_srv (int) | None
ping_ms, loss_pct, bw_in_kbps, bw_out_kbps (float) | None
rl_entities (int), rl_tick_ms, rl_mtsync_ms (float) | None
client_fps, client_fps_min, client_fps_max, client_ms (float) | None
vram_used_mb, vram_total_mb (int) | None
location (str "RR_CRU_L4") | None
server_time (str) | None
ok (bool: at least server_fps and one of pop/ping parsed)
```
Never put the Session GUID in a Snapshot.

### Event (from Game.log), a dict
```
ts (float unix UTC), kind (str), plus kind-specific fields
```
Kinds: `log_start` (build, version), `hardware` (cpu, threads, ram_mb, gpu, vram_mb, gpu_bench_ms,
cpu_bench_ms), `join_pu` (shard_id, region, address, port), `disconnect` (cause, reason, remote),
`contract_accepted` (name, mission_id), `objective_new` (text, mission_id), `contract_ended`
(name, result), `notification` (text), `error` (level, tag, text, sig), plus whatever the corpus
analysis shows is useful.

`sig` = normalised signature of an error line: tag + message with numbers, ids, GUIDs, handles,
quoted entity names' trailing ids removed; used for grouping and for matching the library.

### Known-issues library: `scstatus/library/issues.json`
```json
{
  "version": "2026-10-29.1",
  "rules": [
    {
      "id": "cargo-no-resource-container",
      "kind": "problem",            // "problem" | "noise" | "info"
      "severity": "high",           // "high" | "medium" | "low"
      "area": "Cargo",              // short area for grouping in the UI
      "match": {"tag": "CargoSystemUtilities::FindBoxSize", "regex": "Item class \\[(?P<item>[^\\]]+)\\] does not have a resource container"},
      "title": "Items can't go through the freight elevator",
      "explain": "The game can't work out a cargo box for {item_name}, so the freight elevator can't handle it properly. If a contract needs this item, the delivery may never count.",
      "fixes": ["Don't send more of these items through the elevator until this is fixed.", "..."],
      "ic_title": "Freight elevator: {item_name} has no resource container, delivery objective never completes",
      "builds_seen": ["12913470"],
      "links": []
    }
  ]
}
```
- `match.tag` is matched exactly against the `<Tag>` of the line (optional); `match.regex` is a Python
  regex searched in the message (named groups become fields). At least one of them must be present.
- `{item_name}` in text = global.ini display name for the `item` group (falls back to the class name).
- Any named group can be used in text as `{group}`.
- Lines at Error/Warning level matching no rule are "unknown".

## UI (localhost dashboard, tracker theme)
Tabs: **Now** (score dial, plain-English summary, live numbers, server FPS and population sparkline,
current shard), **What's gone wrong?** (button, findings, Issue Council draft, report folder), **History**
(sessions and shards table, best times), **My PC** (hardware, client FPS), **Known issues** (library
browse), **About** (author, "Also by Aurelius_Draco" panel linking to SC Inventory Tracker).
