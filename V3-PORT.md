# Verse Shards for PC 1.4.0: the v3 port

This branch (`next`, uncommitted) is the v3 design from the simulation, ported into the real app with the Python
behind every new field and endpoint. VERSION stays 1.4.0, since 1.4 was never released; the 1.4.0 CHANGELOG entry
covers the whole update. Nothing is committed, pushed or released.

## What changed

**Page** (`scstatus/static/index.html`): the v3 companion page with the simulation lines taken out (the four mock
script tags at the top, the dev panel and glue at the bottom) and `__TOKEN__` / `__VERSION__` put back. The
`<meta name="app" content="SC Shard Status v__VERSION__">` line stays, so a newer copy still finds an older one
running. New images in `scstatus/static/img`: `1-now-healthy.webp` (About) and `centaurus.webp` (About, from Ray's
MKV.jpg). The installer bundles the whole `static` folder already.

**Python:**

| Where | What |
|---|---|
| `dashboard.py` | `GET/POST /api/profile`, `POST /api/groups/extend`, `POST /api/groups/decide`; `/api/groups/post` passes `details` and `hours`; `/img/` serves `.jpg`, `.png` and `.webp`, and a missing image is a plain 404 (About's Pyro shot until Ray adds it); posted bodies over 1.5 MB are refused |
| `app.py` | `/api/now` gains `sharing {on, fed_week, status}`, `pirates_here {here, elsewhere, area_name}`, `groups_on_shard`, `crash {ts, after_code}` and `session.end`; `/api/history` gains `ships_retrieved`; past sessions are read once more on first start so they carry ship counts |
| `groups.py` | posts carry `details` (only known keys and values) and `hours` (1 to 3); `mine()` gives `hours`, `filled`, `full`, `details`, `can_extend`, and the chat line counts open spots (none once full); each keen player has a `status` (`seen` once this app has picked them up, `in`, `out`); players who withdrew on the site drop out; `extend()` and `decide()` call the site with the post's key; `pirates_here()` and `groups_on_shard()` read the public feed |
| `community.py` | reads `GET /api/v1/posts` every 60 s while the community board is on (nothing new is sent); asks `GET /api/v1/fed?install=` every 10 minutes while sharing is on |
| `logparse.py`, `store.py` | ships retrieved per session (from the retrieval line plus the ATC line that names the ship; never a handle), summed over this build |
| `profile.py` (new) | `profile.json` and `profile.<png/jpg/webp/gif>` in the data folder, never sent anywhere; text limits, picture up to about 900 KB, a handle is required |
| `tools/showcase.py` | the local fake site now answers the groups feed, the fed count, your posts, extend and decide, so the screenshots show v3; sharing is on in the demo and goes to that fake only |

**Site contract the app relies on** (built in `verse-shards-v3/server-src`):

- `POST /api/v1/posts` takes `hours` and `details`, answers `{ok, id, key, expires, hours}`
- `POST /api/v1/posts/mine` answers each post with `hours`, `filled`, `full` and each interest with `status`
- `POST /api/v1/posts/<id>/extend {key}` answers `{ok, expires, hours}` or 409 with the reason
- `POST /api/v1/posts/<id>/decide {key, handle, verdict}` answers `{ok, filled, full}`
- `GET /api/v1/fed?install=<16 hex>` answers `{install, week, since}`
- `GET /api/v1/posts` lists `pirates` with `latest` and posts with `full`

The new site must keep accepting 1.3 posts (no `hours`, no `details`): `server-src` defaults to 2 hours, so it does.

## Coping with the old site

The site and the app launch together, but the app still copes with the site as it is today, for the minutes between
the two steps and for any rollback:

- `extend` and `decide` against an old site (404 "not found") say "Verse Shards hasn't been updated for this yet, so
  nothing changed." and change nothing.
- An old site ignores `hours`, so the post's length comes back as 2 hours and the message says so.
- No `filled` from `/posts/mine`: the crew shows 0 filled, nothing closes early.
- `/api/v1/fed` missing or failing: `fed_week` is null and the page leaves the count out.
- Pirate and group lines need `GET /api/v1/posts`, which the old site already has.

## Tests and checks

- `python3 -m pytest -q tests`: **117 passed** (102 before). New in `tests/test_v14_live.py`: details and hours,
  posting messages, keen statuses and withdrawals, full crews closing, extend and decide (and the site's reasons), the
  old-site fallbacks, the pirate and groups lines from the feed, the fed count on an old site or an error, ships
  retrieved from realistic log lines, past sessions summed by build, the crash state naming the library entry, the
  profile store limits, and the dashboard's webp, missing image, profile and 413 answers. `tests/test_v14.py` now
  checks the v3 Now tab and the two-line copy for chat.
- `docs/screenshots` regenerated with `tools/showcase.py` (made-up data, the local fake site only).
- The real app with made-up readings, every tab in Chromium at 1440 and 960, dark and light: no page errors and no
  sideways scroll. The only failed loads were About's missing `centaurus-pyro.webp` (404, placeholder shows) and the
  GitHub star count (GitHub rate-limits this test machine; players' PCs are fine). The HUD, Groups, My pilot, Set up
  and About match the v3 simulation's screenshots.

## The companion's part of the joint launch

The new site and 1.4.0 go live together, as one launch.

**Ready beforehand**

1. Ray adds `centaurus-pyro.webp` to `scstatus/static/img` (or the About placeholder ships; it's labelled and fine).
2. Ray says go: commit this branch to `next`, merge to `main`, push (both kept level, as before). Tests green.
3. Draft the GitHub release `v1.4.0` (title "Verse Shards for PC 1.4.0", notes from the 1.4.0 CHANGELOG entry), target
   `main`. Save as a draft; don't publish.
4. The site's v3 is ready on its own branch, with its database migration tested locally.

**On launch**

1. Site first: apply the site's database migration to the live database, then deploy the site (push its `main`).
2. Check the site answers: `/api/v1/health`, `/api/v1/posts` (has `full` and `hours` on posts),
   `/api/v1/fed?install=0000000000000000` (answers with a `week` count rather than 404).
3. Within a few minutes, Ray presses **Publish** on the `v1.4.0` draft. The release workflow builds the Windows
   installer on CI (about 10 minutes), attaches it, then posts to Discord.
4. Until the installer is attached, 1.3 players see no update; once it is, 1.3 shows "Version 1.4.0 is out" and
   updates in one click.

**Check afterwards** (Ray, on his PC)

- The update from 1.3 installs and the app restarts on its own; the header reads "Verse Shards for PC · v1.4.0";
  settings and history are still there.
- Now: the HUD fills with readings; with sharing on, "Fed it N times this week" appears within 10 minutes.
- Groups (boards open): post a recruiting post with a couple of details and Playing for 1 h. On verseshards.com it
  shows the chips and "Playing for 1 hour". From another browser press I'm interested; in the app press Mark filled;
  the browser shows "You're in". Press +1 hour, then Take it down.
- My pilot: fill in the card, restart the app, it's still there.
- Rollback, if needed: the site can go back on its own (the app copes, see above). To pull 1.4.0, delete the GitHub
  release (the updater reads "latest"), so 1.3 players stop being offered it.

## For Ray

- Release only when you say: nothing here is committed, pushed or published.
- The README's title still says "SC Shard Status" (the repo and install name). Change it to "Verse Shards for PC"
  if you want the GitHub page to match.
- The old `docs/screenshots/12-phone-width.png` is still in the repo but no longer used; the README now shows
  `12-narrow-window.png`.
- Most-visited places on My pilot show the game's location codes (as 1.3's My PC did), not place names.
