# Changelog

## 1.5.2 (not released yet)
- **Blueprints, a new tab.** Every crafting blueprint you've earned, read from your game logs: grouped (armour, FPS weapons, magazines and batteries, ship weapons, other), searchable, with the date and the contract it came from. Keep a want list, and when a wanted one turns up in game it comes off the list with a toast (and an alert, if alerts are on). It's built from the logs on this PC, so blueprints earned on another PC or before your logs were kept won't show, and a wipe isn't logged; the fabricator in game is the final word.
- **Your sessions, in History.** One card for every time you played, nine to a page: the health score for the session, contracts completed and failed, blueprints, licences, problems hit, moments marked. Open one for the full report: every contract with its rep (a number only when the game states one; a ladder shows as "rep by rank"), shards and servers, problems with what happened, ships lost and why, and your own good or bad rating, a note and, if you like, your aUEC at the start and end. All of it stays on this PC.
- **Your game settings, saved.** Set up lists every setting you've changed from the game's default and your custom key binds, saves them with one button, and checks each copy of the game (LIVE, PTU, Tech Preview) against the save. Put them back with one button while the game is closed; what's there is backed up first, to Documents\Verse Shards\Settings backups. When the copy you're playing isn't set up the way you saved it, the Now tab says so once per launch.
- **Licences and permits** sit with your blueprints: every licence, permit and certification the game has logged for you, with the date and the contract that gave it.
- **Your week** at the top of Your sessions: hours played, contracts, blueprints and licences, average health and your best and worst session, against the week before.
- **Your contracts** in History: every kind of contract you've done, how many, how many failed, typical time from accept to complete, the rep the game stated, and which blueprints came with it, so you can see what's worth farming.
- **More in each session report:** quantum jumps, how long your ship took to be ready after you asked for it, the jurisdictions you entered, injuries and med bed heals, and the aUEC the game logged (spent at shops, sent, received; contract pay and sales aren't in the log, and other players' names are never kept).
- **My pilot's logbook** adds your lifetime quantum jumps, aUEC spent at shops, typical wait for your ship, times downed, and the jurisdictions you've been in.
- **The login queue** shows on the Now tab with your place and the game's own estimate.
- **Why your ship was lost.** From 4.10.3 the log says why a ship was destroyed (combat, self destruct, collision); the session report shows it, never who did it. "Was it another player?" is only asked after a ship lost in combat.
- **What you type into a moment is kept** as you type it, for a month, and shows on the list. Before, closing a moment without sending lost the note.
- **Sent back to the menu by the server** is told apart from quitting or choosing Exit to Menu, on the timeline, in alerts and in moments.
- **Server fps is checked against its frame time** on the overlay, and a reading where the two don't agree is dropped. A decimal point split by a space (110. 9ms) is read properly.
- **Shard ids with a dropped or swapped digit** are caught against Game.log instead of showing as a new shard.
- **Reading through the ship banner and pop-ups.** When the ship name banner or a mission pop-up covers part of the overlay, the app takes a second look keeping only the overlay's own colours and its shadow, and fills in what the first read missed. Values a pop-up could turn into a wrong number (the location, hitches, the shard id and player counts) are left out of that reading. On test screenshots it read 5 more of 26 4K shots and about 220 more values, with no wrong ones.
- **The PTU's long Server line at 1440p** is read: your server and its player counts now show on the 4.10.3 PTU (0 of 44 shots before, 33 now). Server names misread with a missing dash or a letter for a digit are put right, or left blank, never shown wrong.

## 1.5.1 (7 Nov 2026)
- **Ready for the Microsoft Store.** Windows 11's Smart App Control blocks apps it doesn't know, and it can switch itself on without asking. This version also comes as a Microsoft Store package, signed by Microsoft so Smart App Control lets it run, and kept up to date by the Store. Microsoft is reviewing it now; verseshards.com will link to it as soon as it's in the Store. It's the same app: the Store version uses the same folder for your settings and history, so moving from this copy keeps everything. Nothing changes for this GitHub version, which carries on updating itself as before.

## 1.5.0 (7 Nov 2026)
- **More from the overlay, on the Now tab.** With r_displayinfo 3 the game also shows the ship you're in, the planet, the mission you're tracking and how long your CPU and graphics card take per frame. The Now tab now shows them: "In your RSI Constellation Mk5 Centaurus, tracking InterSec Bounty Nyx Intro · Your PC: graphics card is the limit (CPU 12.7 ms, GPU 15.4 ms a frame)". When your own frame rate is low, the advice says whether lower graphics settings will help or it's your CPU. A group post starts on the activity your tracked mission points to (a bounty, hauling, a Vanduul Incursion mission). None of this is shared.
- **The shard from the session QR code.** When the game's QR code is on screen, the app reads the shard id from it whenever the ShardId line is hard to read. Only the shard id is used, never the session id.
- **The overlay reader finds the overlay more often.** At 4K it reads finer: on the 4.10.3 PTU it found the overlay in 99% of readings instead of 85%, in about half the time. When a reading misses, it now has one more go at the other text size, which at 1440p took good readings from 79% to 98% of the times the overlay was on screen. The tracked mission line is found even when the overlay block is long, and the planet shows as its name (ArcCorp).
- **Your game server, not the whole shard.** Since server meshing each area of the verse has its own game server, so the Now tab now says "Your game server (178) is struggling" instead of blaming the shard. With Show other shards on, when your server is slow and another server on your shard is fine, it says which areas that one runs, so you can fly there instead of hopping.
- **Misreads stay out.** A server number with letters in it, a shard id with a short build number, or a player count far past what a shard holds is treated as a misread and not used or shared. One misread server name no longer counts as a server change.
- **Send for review is quicker on long sessions,** and if a moment can't be worked out it says so instead of sending an empty one.
- Fixed: a bad end date on the message of the week could stop the Now tab loading, and picking a place the app didn't know the area of gave an error.
- **Error codes never carry names.** A code sent for review or with a marked moment goes through the name stripper too, and anything in quotes (a chat channel or org name) is blanked. A moment's code that still has a name in it isn't sent at all.
- A moment opened late still looks back half an hour before the moment you marked, however long after you open it.
- **Taken a Vanduul Incursion contract?** A new group post starts on the Vanduul Incursion activity (change it if you like). The contract titles come with library updates, so new mission packs don't need a new app.
- **What CIG's patch notes say about your problems.** When a check finds something CIG's notes list a potential fix for, the card says so: a fix on the way in a later patch, or, if it turns up on the patch that listed the fix, that it's still happening (and the Issue Council draft says so too). The list comes with library updates, so it's ready on patch day without a new app.
- **Patch day names fixes for problems you hit.** The new-build notice lists the fixes in CIG's notes for problems your own logs showed in the fortnight before, and links the patch report card, which shows whether other players still hit them.
- **Saw into someone else's hangar?** When CIG asks players to report where something still happens, Mark this moment offers it as a quick pick, and the Issue Council draft is set up for it.
- Shared session summaries also say which patch they're on (like 4.10.3), so the patch report card can line builds up with CIG's patch notes.
- **Test servers stay off the board.** Pointed at a PTU, EPTU, Tech Preview or Hotfix folder, the app reads and checks as usual but shares nothing: no readings, no session summaries, no group posts or pirate reports. Set up says sharing is paused and why. Shared readings now also say they come from LIVE.
- **Message of the week.** Now and then the Now tab shows a short message from Verse Shards with a link, for example a Spectrum post worth an upvote. It comes with the board the app already downloads when Show other shards is on, so nothing extra is sent. Hide puts that message away for good.
- Reading-quality counts (sent with shared readings) now count a misread only when a value blips for one reading and comes straight back, not every time the player count moves. The old count mostly measured how busy the server was.
- Fixed: the overlay wasn't found when the game runs at a lower resolution than the monitor (for example 1440p on a 4K screen). Thanks to the player who reported it on GitHub.
- Windows now calls the app **Verse Shards for PC** in Settings, Apps, the installer, Task Manager and the exe's Properties. It still installs as SC Shard Status: same folder, same Start menu shortcuts, and your settings and history stay where they are. Updating and uninstalling work as before.
- **Pirate reports for somewhere else send only the area.** You still pick a place, so the app knows which planet, moon group, jump point or open space it's in, but only that area goes to the board, never the place you picked. The confirmation names the area too.
- **Update checks wait for your answer.** The app no longer asks GitHub for a new version before you've answered the update question in set-up. The About tab's GitHub star count only shows with update checks on. If you've already answered, your choice stays as it was and you won't be asked again.
- **Plainer about what leaves your PC.** Update checks ask GitHub, only when switched on. Show other shards only downloads the board and sends nothing about you. Sharing readings, app error reports and the buttons you press are what send things to verseshards.com.
- **Moments noticed late are still caught.** Mark a moment 20 or 30 minutes after the trouble started (say, items that went missing after a burst of failed inventory moves) and Your moment now shows the known problems from the half hour before, under Earlier.
- **Moments sent for review say a bit more, so we can work them out without your files.** Besides your description and the issues found near it, Send for review now also sends the area (never the exact place), your game server's number and its fps then, known problems from the half hour before, the kinds of thing that happened in the 5 minutes before (a server change, quantum travel, a ship retrieved), and the codes of any errors the app doesn't know yet, with names and numbers stripped. Your moment lists exactly what goes before you press the button. Still never screenshots or log lines.
- **Send for review works on its own.** Sending a marked moment for review no longer needs Show other shards switched on: pressing the button is your yes. It sends the time, game build, shard, what you typed and the ids of known issues found near it. Never screenshots or log lines.

## 1.4.1

- **Unplayable server:** when your server stays under 5 fps for a minute, the Now tab shows the red alarm and hazard stripe labelled Unplayable, and checks the log straight away so you can see what it found. A Bad server now breathes slowly the whole time instead of blinking.
- **Mark this moment, start to finish:** mark it, take screenshots if you can, pick them from your last 10 minutes, say what went wrong, and see your moment: the readings at that second, the log either side and what it shows. Then send it to Verse Shards for review (only your description and what the log found, never screenshots), write the Issue Council report (your picked screenshots go in its folder), or both. Earlier marks open the same way from What's gone wrong?.
- **Pirate reports:** "Someone says they're patrolling" as well as "I saw them", and you can now report somewhere else on your shard. Start typing and pick from 882 places across Stanton, Pyro and Nyx: stations, rest stops, outposts and settlements, from Ruin Station to Ashland. Patrolling reports show amber and count for less.
- **Issue Council, after you post:** paste your report's link into the draft and it goes on that issue's page on verseshards.com. Say if it's a duplicate, linked or the same as one already there, and attach it in the same step.
- Copy buttons say Copied, crew spots pop as they fill, and your post's time-left bar runs down smoothly.
- Kicked for being idle (30028) is now treated as a normal disconnect, not an error, and no longer counts against the patch.
- Fixes since 1.4.0: copy fixes, the pirate beacon matches the site, and an oversized request is refused cleanly.

## 1.4.0

The app is now **Verse Shards for PC**, with a new look that matches verseshards.com. Your install, settings and history stay where they are (it still installs as SC Shard Status).

- **Now tab, cockpit view:** a health bar across the top, then your score and six gauges, each with an hour of small bars: server fps (with the low), players on your server, players on the shard, ping, packet loss (with hitches and restarts) and your own fps. The card's edge reacts: calm when healthy, a slow amber breath when it's slowing, a red beacon when it's bad.
- **What to do next, up front:** the verdict, the top two reasons (the rest folded), a hop suggestion when a healthier shard in your region has at least two players sharing, and What's gone wrong? as the main button when there's trouble.
- **Crash alarm:** when Game.log ends with the game's crash handler, the Now tab says so, names the crash it matched if it knows one, and puts What's gone wrong? first.
- **Pirate reports near you:** with the community board on, a line on Now says if pirate activity was reported in your area or elsewhere on your shard in the last 45 minutes, and "Pirates near <area>" files the report. Reports are still only ever sent when you press the button, and only the area goes.
- **Your region on the board:** pips for players sharing on each shard. Not sharing? Your shard shows as a dashed row with a short note on what sharing does and what's sent. Sharing? "Fed the board N times this week" from Verse Shards' own count.
- **Groups:** your post shows exactly as it does on verseshards.com. Add optional details (voice or text, experience, play style, bringing a ship or need a seat, language, org) and pick Playing for 1, 2 or 3 hours. Mark keen players filled or "not this time" (with Undo); they see where they stand on the site. +1 hour on a post, up to 3 hours in all. A full crew closes itself 10 minutes after it fills. "N groups recruiting on your shard" links to the site.
- **My pilot** (was My PC): your own pilot card with handle, org, ships (tap one to make it your main), what you fly for, play times and a picture. It stays on this PC and is never sent anywhere. Below it, a logbook from Game.log: hours played this patch, contracts completed, shards played on, server fps on your sessions, ships you retrieved most, and your PC and fps by place as before.
- **Set up:** a systems check across the top (game folder, overlay, live reading, board, sharing, alerts, updates, library) with each lamp jumping to its setting. No settings or wording changed.
- **Known issues and your reviews:** traffic lights for how serious each problem is (Critical, Major, Minor), Critical first.
- **Copy for global chat:** the best line, then "Found this on Verse Shards: verseshards.com" as its own line with its own Copy button. After copying: "Copied. In game press Enter, then Ctrl+V."
- **About** matches the site's About: who made it and why, how it works, the ground rules, the org, what's coming and thanks, plus the app's own extras.
- Clearer text: lighter grey for secondary text and nothing smaller than 14 px.
- The tab bar wraps onto a second row in a narrow window instead of hiding Set up and About.
- Works with the site before and after its own update: anything the site can't do yet says so and changes nothing.

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
