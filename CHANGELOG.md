# Changelog

## 1.3.0

- Cleaner readings. The overlay is read off the screen, so now and then one value comes out wrong (a restart counter of 435, packet loss of 9%). A value now only counts once it repeats, restarts must hold and never drop back, and each server stint is judged on its own: a server hop, relog or long gap starts afresh. No more false restart alerts or 519-hitch spikes, in the app or on verseshards.com.
- New alert when a server that's already slow drops under 5 fps.
- Issue Council drafts laid out like the form, box by box and inside its limits: title, exact game version, suggested category and severity, steps (where you were and the server's fps first, from Verse Shards), what happened, what should have happened and any workaround. "What were you doing?" is started for you from the log. If players have linked a report on verseshards.com, the draft takes you there and writes your contribution instead.
- Mark this moment: a button at the top of the dashboard, and an optional hotkey (Ctrl+Alt+M and others, set up on the Set up tab). "What's gone wrong?" then looks at that moment first.
- Groups tab: post a recruiting or looking-for-group notice on verseshards.com (shard, server and area filled in), see who's keen to join as a pop-up, and report pirate activity in an area. After your ship is destroyed (and it wasn't a crash), the app offers the pirate report; it never sends it by itself. The boards open on the site once there are moderators.
- Copy for global chat: short lines about your shard on the Now tab, and a separate "Found this on Verse Shards" line.
- Overlay off: the dashboard says "Overlay off, readings paused".
- The session QR code is now off unless you want it.
- New set-up question: send a report when something in the app itself goes wrong (off unless you say yes; paths and names taken out).
- Sharing adds counts of how cleanly the overlay was read and your screen size, so screen setups that misread can be helped, and the game's wording for disconnect errors (letters only), so new error codes can be explained. If you share, you're asked once more.
- New library entry: lost flight control after take-off (a fatal collision at walking pace).
- About: star the project on GitHub, add Aurelius_Draco as a friend, the Spectrum thread, help wanted, and org tools coming soon.

## 1.2.0

- Shards have short names: AU-20, EU-410, USE-130 (region and shard number), in the app, on verseshards.com and in Discord. The full id is still there when you hover.
- Where you are, in words: the Now tab shows your place using the game's own names (CRU-L4 Shallow Fields Station, Bloom, the Stanton to Pyro jump point) and which area your server runs.
- New Timeline tab: what happened in order, from quantum jumps and armistice zones to ships, contracts, the freight elevator, loading, disconnects and crashes. Filters by kind and a Details switch for the log lines.
- Issue Council drafts now have real steps to reproduce, built from your timeline.
- When RSI's status page reports a problem, the Now tab says so.
- With the community board on, your region shows its quieter areas right now (fewest players on the server running them; quieter, not safer), and shards show which areas their servers run.
- Sharing now also sends the area your server runs (a planet, jump point or open space, never the exact place) and, after each session, its build, length, load time, whether it crashed and disconnect error codes, for the new patch report card on verseshards.com. If you share, you're asked once more so you can see the new list.
- New on verseshards.com: Trends (busiest times by hour, patch report cards, issue trends, every shard and server seen) and Trade (UEX trade routes beside how busy each end's server is).

## 1.1.2

- With more than one copy of Star Citizen on the PC, the app now picks the one you played most recently. Before, the installed app could pick an old copy and spend a long time reading its old logs.

## 1.1.1

- Pop-up alerts only cover the last 15 minutes, so starting the app no longer alerts about a crash from an earlier session.
- Set up tab: an Open the data folder button beside the second-monitor tip, and clearer help when the game folder isn't found.

## 1.1.0

- A proper Windows installer: download SC-Shard-Status-Setup and run it. No Python, no admin password, Start menu and desktop shortcuts, and an uninstaller that asks whether to keep your history.
- One-click updates: the dashboard says when a new version is out and Update now installs it and starts the app again, keeping your settings and history. The download is checked against its published SHA-256 before it runs.
- Used the zip version? The installed app finds it on first start and brings your settings, history and reports across.
- The known-issues library keeps itself up to date from verseshards.com (new set-up question, a plain download that sends nothing about you). New entries reach everyone without a new version of the app.
- Send for review now really sends: unrecognised errors go to the review queue on the community site, after you've seen exactly what's in them. Answers show under Your reviews on the "What's gone wrong?" tab.
- Pop-up alerts while you play (new set-up question, with or without a sound): a Windows notification when the server's fps falls off a cliff, the server restarts, packet loss climbs, you're disconnected, or a known problem turns up, like contract deliveries not counting. Each kind at most once every 10 minutes.
- Patch day: when the game build changes, the Now tab says so and explains why servers may be slower for the first day.
- About links to the new Verse Shards Discord: https://discord.gg/8kH5pfHYbe (shard alerts, help, new versions).
- Your region on the Now tab marks a score from one player as a first look, and won't suggest a server hop on the strength of one.
- New set-up questions: tell you when there's a new version, pop-up alerts, and keep the library current. If you've already been through set-up, you're asked only the new ones.

## 1.0.1

- The community site has its own address: https://verseshards.com. Linked from the top of every page in the app, the About tab and each finding in "What's gone wrong?".

## 1.0

First release.

- Live shard health from the game's debug overlay (r_displayinfo 3): score out of 100, plain-English summary, server fps, shard and server population, ping, packet loss, hitches, restarts, your own fps.
- Game.log followed live: shard joined and region, load time, disconnects with cause codes, contracts and objectives, hardware and the game's CPU and GPU tests, crashes.
- "What's gone wrong?": checks the last 10 minutes to 4 hours against the known-issues library, joins contracts to item errors, flags slow servers, restarts, packet loss and crashed sessions.
- Issue Council drafts with a report folder (report, Game.log, screenshots from around that time).
- History: shards with their server fps and population, past sessions from logbackups, server fps by hour.
- Unrecognised errors can be prepared for review with identifiers stripped; saved locally until the community service exists.
- Finds the game folder on any drive, or from the running game, or from a folder you paste on the Set up tab.
- Quick on/off switches for the overlay and the session QR code, in game and at start-up (USER.cfg).
- First-run questions: every setting is a yes or no you answer once (game folder, overlay and QR code at start-up, live and screenshot reading, community board, sharing). Asked again only when a new question is added.
- Community board (opt in): see the other shards in your region, and share 5-minute summaries of your readings. Live reading and screenshot reading now switch on and off without a restart.
- One-click Setup.bat, shortcuts with their own icon, dark and light themes.
