"""Groups: recruiting and looking-for-group posts, pirate reports, and lines to paste into global chat.

Everything here happens only when you press a button. A post carries your shard, server and the area you're in
(a planet, jump point or open space, never the exact place), the activity you picked, an optional note and, only
if you choose, your handle. Posts end after 2 hours (pirate reports after 45 minutes) and the site deletes them.
"""

import json
import time

from .community import shard_name

POLL_EVERY_S = 60
OFFER_WINDOW_S = 600        # how long after your ship is destroyed the pirate report is offered
MAX_HOURS = 3               # a post runs at most 3 hours from posting (Playing for 1, 2 or 3 h, plus +1 hour)
FULL_SHOW_S = 600           # a full crew shows "Crew full" for 10 minutes, then closes itself
OLD_SITE = "Verse Shards hasn't been updated for this yet, so nothing changed. Try again in a little while."
DETAIL_VALUES = {"voice": ("voice", "text"), "exp": ("new", "regular", "veteran"), "style": ("chill", "focused")}


def clean_details(d):
    """The optional details on a post: only known keys and values go out, anything else is dropped."""
    if not isinstance(d, dict):
        return None
    out = {k: d[k] for k, ok in DETAIL_VALUES.items() if d.get(k) in ok}
    ship = d.get("ship")
    if isinstance(ship, str) and ship.strip():
        out["ship"] = " ".join(ship.split())[:25]
    elif d.get("seat") is True:
        out["seat"] = True
    if d.get("seat") is True:          # needing a seat wins over a ship name
        out.pop("ship", None)
        out["seat"] = True
    for k, n in (("lang", 20), ("org", 30)):
        v = d.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = " ".join(v.split())[:n]
    return out or None


def clean_hours(h, default=2):
    try:
        h = int(h)
    except (TypeError, ValueError):
        return default
    return max(1, min(MAX_HOURS, h))


class Groups:
    def __init__(self, app, community):
        self.app, self.community = app, community
        self.poll_at = 0
        self.open = None            # are the boards switched on at the site? (None until checked)
        self.activities = []
        self.interest = []          # replies to your posts, newest first: {post, activity, handle, note, created}
        self.keen = {}              # post id -> how many players have pressed I'm interested (and not been turned down)
        self.filled = {}            # post id -> crew filled so far (keen players you marked in)
        self.full_at = {}           # post id -> when this app first saw the crew full
        self.status = {}            # (post id, handle) -> sent, seen, in or out
        self.error = None

    # -- your posts (the keys the site handed back, so only this PC can see who replied or close them)
    def _keys(self):
        try:
            rows = json.loads(self.app.store.meta("post_keys", "[]") or "[]")
        except ValueError:
            rows = []
        now = time.time()
        return [r for r in rows if r.get("expires", 0) > now]

    def _save_keys(self, rows):
        self.app.store.set_meta("post_keys", json.dumps(rows[-10:]))

    def context(self):
        """Shard, server and area right now, from the overlay and Game.log."""
        snap = self.app.latest_snap() or {}
        s = self.app.session
        shard = snap.get("shard_id") or (s.shard_id if s else None)
        server = (snap.get("server_name") or "").rsplit("-", 1)[-1] or None
        code = snap.get("location") or _last_location(s)
        w = self.community.places.where(code) if code else None
        return {"shard_id": shard, "shard": shard_name(shard) if shard else None, "server": server,
                "system": (w or {}).get("system"), "area": (w or {}).get("area"), "area_name": (w or {}).get("area_name")}

    def handle(self):
        """Your handle from Game.log, offered (never sent) until you confirm it on a looking-for-group post."""
        s = self.app.session
        return s.handles[-1] if s and s.handles else None

    def post(self, kind, activity=None, note=None, spots=None, handle=None, details=None, hours=None):
        ctx = self.context()
        if not ctx["shard_id"]:
            raise ValueError("Join a shard in game first, so the post can say where you are.")
        body = {"v": 1, "kind": kind, "install": self.app.store.install_id(), "shard_id": ctx["shard_id"],
                "server": ctx["server"], "system": ctx["system"], "area": ctx["area"], "area_name": ctx["area_name"]}
        if kind in ("recruit", "lfg"):
            body.update(activity=activity or None, note=(note or "").strip()[:80] or None,
                        spots=int(spots) if str(spots or "").isdigit() else None,
                        handle=(handle or "").strip() or None,
                        details=clean_details(details), hours=clean_hours(hours))
        try:
            code, d = self.community._req("/api/v1/posts", body)
        except Exception as e:
            raise ValueError(f"Couldn't reach Verse Shards ({e.__class__.__name__}).")
        if code != 200:
            raise ValueError(d.get("error") or f"Verse Shards answered {code}.")
        if d.get("key"):
            rows = [r for r in self._keys() if r.get("kind") != kind or kind == "pirate"]
            rows.append({"id": d["id"], "key": d["key"], "kind": kind, "activity": activity, "expires": d.get("expires"),
                         "spots": body.get("spots"), "shard": ctx["shard"], "shard_id": ctx["shard_id"],
                         "server": ctx["server"], "area_name": ctx["area_name"], "handle": body.get("handle"),
                         "note": body.get("note"), "created": time.time(), "details": body.get("details"),
                         # an older site ignores hours and keeps a post for 2 hours
                         "hours": d.get("hours") or (2 if kind != "pirate" else None)})
            self._save_keys(rows)
            self.poll_at = 0
        h = d.get("hours") or 2
        span = "an hour" if h == 1 else f"{h} hours"
        return {"pirate": "Reported. Other players see the area for 45 minutes.",
                "recruit": f"Posted on Verse Shards for {span}. Players who are keen send their handle, and it pops up here.",
                "lfg": f"Posted on Verse Shards for {span}. Recruiters can copy your handle and send a party invite."}[kind] \
            + (" You'd already reported this area." if d.get("duplicate") else "")

    def _row(self, post_id=None, kind=None):
        rows = self._keys()
        if post_id:
            return next((r for r in rows if r["id"] == post_id), None)
        return next((r for r in rows if r.get("kind") == kind), None)

    def _update_row(self, post_id, **changes):
        rows = self._keys()
        for r in rows:
            if r["id"] == post_id:
                r.update(changes)
        self._save_keys(rows)

    def extend(self, post_id):
        """+1 hour on your post: at most 3 hours from posting, and not once the crew is full."""
        row = self._row(post_id)
        if not row:
            raise ValueError("That post has already finished.")
        try:
            code, d = self.community._req(f"/api/v1/posts/{post_id}/extend", {"key": row["key"]})
        except Exception as e:
            raise ValueError(f"Couldn't reach Verse Shards ({e.__class__.__name__}).")
        if code == 404 and d.get("error") in (None, "not found"):
            raise ValueError(OLD_SITE)
        if code != 200 or not d.get("ok"):
            raise ValueError(d.get("error") or f"Verse Shards answered {code}.")
        self._update_row(post_id, expires=d["expires"], hours=d.get("hours"))
        when = time.strftime("%H:%M", time.localtime(d["expires"]))
        return {"message": f"Extended. Your post now ends at {when}.", "expires": d["expires"]}

    def decide(self, post_id, handle, verdict):
        """Mark a keen player filled (in), not this time (out), or undo (None). Needs your post's key."""
        row = self._row(post_id) or self._row(kind="recruit")
        if not row:
            raise ValueError("That post has already finished.")
        post_id = row["id"]
        verdict = verdict if verdict in ("in", "out") else None
        if not any(i["post"] == post_id and i["handle"] == handle for i in self.interest):
            raise ValueError("That player isn't on your post any more.")
        try:
            code, d = self.community._req(f"/api/v1/posts/{post_id}/decide",
                                          {"key": row["key"], "handle": handle, "verdict": verdict})
        except Exception as e:
            raise ValueError(f"Couldn't reach Verse Shards ({e.__class__.__name__}).")
        if code == 404 and d.get("error") in (None, "not found"):
            raise ValueError(OLD_SITE)
        if code != 200 or not d.get("ok"):
            raise ValueError(d.get("error") or f"Verse Shards answered {code}.")
        self.status[(post_id, handle)] = verdict or "seen"
        filled, full = int(d.get("filled") or 0), bool(d.get("full"))
        self.filled[post_id] = filled
        if full:
            self.full_at.setdefault(post_id, time.time())
        else:
            self.full_at.pop(post_id, None)
        msg = {"in": f"{handle} is in the crew. Their pip turns teal on the site.",
               "out": f"Done. {handle} sees a polite \"not this time\" on the site."}.get(verdict, "Undone.")
        return {"message": msg, "filled": filled, "full": full}

    # -- the public feed: pirate reports and other players' groups on your shard (only with the community board on)
    def pirates_here(self):
        ctx = self.context()
        feed = getattr(self.community, "posts", None) or {}
        if not ctx["shard_id"] or not feed.get("open"):
            return {"here": None, "elsewhere": None, "area_name": ctx.get("area_name")}
        mine = [p for p in feed.get("pirates", []) if p.get("shard_id") == ctx["shard_id"]]
        pick = (lambda p: {"area": p.get("area"), "area_name": p.get("area_name"), "system": p.get("system"),
                           "reporters": p.get("reporters"), "created": p.get("created"), "expires": p.get("expires"),
                           "last": p.get("latest") or p.get("last") or p.get("created")} if p else None)
        here = next((p for p in mine if ctx["area"] and p.get("area") == ctx["area"]), None)
        others = sorted((p for p in mine if p is not here), key=lambda p: -(p.get("reporters") or 0))
        return {"here": pick(here), "elsewhere": pick(others[0] if others else None), "area_name": ctx["area_name"]}

    def groups_on_shard(self):
        ctx = self.context()
        feed = getattr(self.community, "posts", None) or {}
        if not ctx["shard_id"] or not feed.get("open"):
            return 0
        own = {r["id"] for r in self._keys()}
        return sum(1 for p in feed.get("posts", [])
                   if p.get("kind") == "recruit" and p.get("shard_id") == ctx["shard_id"] and p.get("id") not in own
                   and not p.get("full"))

    def close(self, post_id):
        row = next((r for r in self._keys() if r["id"] == post_id), None)
        if not row:
            raise ValueError("That post has already finished.")
        try:
            self.community._req(f"/api/v1/posts/{post_id}/close", {"key": row["key"]})
        except Exception:
            pass
        self._save_keys([r for r in self._keys() if r["id"] != post_id])
        return "Post taken down."

    def mine(self):
        out = []
        for r in self._keys():
            row = {k: r.get(k) for k in ("id", "kind", "activity", "expires", "spots", "shard", "shard_id", "server",
                                         "area_name", "handle", "note", "created")}
            row["keen"] = self.keen.get(r["id"], 0)
            spots, filled = r.get("spots"), min(r.get("spots") or 0, self.filled.get(r["id"], 0))
            full = bool(spots and filled >= spots)
            if full and time.time() - self.full_at.get(r["id"], time.time()) > FULL_SHOW_S:
                continue                    # a full crew closes itself 10 minutes after it fills
            created = r.get("created") or time.time()
            hours = r.get("hours") or max(1, round(((r.get("expires") or created) - created) / 3600))
            row.update(hours=hours if r.get("kind") != "pirate" else None, filled=filled, full=full,
                       details=r.get("details"),
                       can_extend=r.get("kind") != "pirate" and not full
                       and (r.get("expires") or 0) - created + 3600 <= MAX_HOURS * 3600 + 60)
            open_spots = spots - filled if spots else None
            if r.get("kind") == "recruit" and r.get("shard") and not full:
                row["chat"] = (f"{r.get('activity') or 'Group'} on {r['shard']}"
                               + (f" near {r['area_name']}" if r.get("area_name") else "")
                               + (f" looking for {open_spots} more" if open_spots else " looking for players")
                               + (f". Message {r['handle']} for an invite" if r.get("handle") else ". Press I'm interested on Verse Shards"))
            out.append(row)
        return out

    def interest_rows(self):
        """Keen players on your live posts, each with where they stand: seen (this app picked them up), in or out."""
        live = {r["id"] for r in self._keys()}
        return [dict(i, status=self.status.get((i["post"], i["handle"]), "seen")) for i in self.interest if i["post"] in live]

    def tick(self, now=None):
        """Check for replies to your posts (and whether the boards are open) once a minute while you have a post up."""
        now = now or time.time()
        if now - self.poll_at < POLL_EVERY_S:
            return
        self.poll_at = now
        keys = self._keys()
        feed = getattr(self.community, "posts", None)
        if feed:                            # the community tick already read the public feed
            self.open, self.activities = bool(feed.get("open")), feed.get("activities") or self.activities
        if (self.open is None or not keys) and not feed:
            try:
                code, d = self.community._req("/api/v1/posts")
                if code == 200:
                    self.open, self.activities = bool(d.get("open")), d.get("activities") or []
            except Exception:
                pass
        if not keys:
            return
        try:
            code, d = self.community._req("/api/v1/posts/mine", {"keys": [r["key"] for r in keys]})
        except Exception as e:
            self.error = f"couldn't reach Verse Shards ({e.__class__.__name__})"
            return
        if code != 200:
            return
        self.error = None
        seen = {(x["post"], x["handle"]) for x in self.interest}
        polled = {p["id"]: {i["handle"] for i in p.get("interested", [])} for p in d.get("posts", [])}
        # Someone who withdrew is gone from the site, so they go from here too
        self.interest = [x for x in self.interest if x["post"] not in polled or x["handle"] in polled[x["post"]]]
        for p in d.get("posts", []):
            ints = p.get("interested", [])
            self.keen[p["id"]] = sum(1 for i in ints if i.get("status") != "out")
            if "filled" in p:               # a v3 site counts the crew; an older one doesn't
                self.filled[p["id"]] = int(p.get("filled") or 0)
                if p.get("full"):
                    self.full_at.setdefault(p["id"], now)
                else:
                    self.full_at.pop(p["id"], None)
            for i in ints:
                st = i.get("status")
                self.status[(p["id"], i["handle"])] = st if st in ("in", "out") else "seen"
            for i in ints:
                if (p["id"], i["handle"]) in seen:
                    continue
                self.interest.insert(0, {"post": p["id"], "activity": p.get("activity"), "handle": i["handle"],
                                         "note": i.get("note"), "created": i.get("created")})
                if not i.get("seen"):
                    self._popup(i["handle"], p.get("activity"), i.get("note"))
        del self.interest[30:]

    def _popup(self, handle, activity, note):
        a = self.app.alerts
        body = f"{handle} wants to join your {activity or 'group'}." + (f" \"{note}\"" if note else "") + \
            " Send them a party invite in game."
        a.recent.appendleft({"ts": time.time(), "key": "group", "title": "Someone's interested", "body": body})
        try:
            a.notify("Someone's interested", body, tag="group", sound=a.mode == "sound")
        except Exception:
            pass

    # -- after your ship is destroyed: offer (never send) a pirate report for the area
    def pirate_offer(self, now=None):
        now = now or time.time()
        s = self.app.session
        if not s or not getattr(s, "deaths", None) or self.open is False:
            return None
        d = s.deaths[-1]
        if d.get("collision") or not d.get("ts") or now - d["ts"] > OFFER_WINDOW_S:
            return None
        if float(self.app.store.meta("pirate_offer_done", 0) or 0) >= d["ts"]:
            return None
        code = _last_location(s, d["ts"])
        w = self.community.places.where(code) if code else None
        if not w:
            return None
        from .timeline import ship_name
        return {"ts": d["ts"], "ship": ship_name(d["ship"]), "area_name": w["area_name"], "area": w["area"]}

    def pirate_done(self):
        self.app.store.set_meta("pirate_offer_done", time.time())


def _last_location(session, before=None):
    if not session:
        return None
    for e in reversed(getattr(session, "travel", [])):
        if e["kind"] == "location" and (before is None or (e["ts"] or 0) <= before):
            return e["code"]
    return None


def chat_lines(now_data, health):
    """Short lines about your shard to paste into global chat, from what the Now tab shows."""
    sh = (now_data.get("shard") or {}).get("name")
    if not sh:
        return []
    out = []
    w = now_data.get("where") or {}
    fps, pop = health.get("server_fps"), health.get("pop_srv")
    area = w.get("area_name")
    if fps is not None and fps < 8:
        out.append(f"{sh} server fps dropping to critical{f' near {area}' if area else ''} ({fps:g} fps). "
                   "I'd avoid high-risk stuff there")
    elif fps is not None and fps >= 18:
        out.append(f"{sh} server{f' running {area}' if area else ''} is healthy right now, {fps:g} server fps")
    if pop is not None and area and pop <= 30:
        out.append(f"{sh} server running {area} has only {pop} players right now")
    if health.get("restarts"):
        out.append(f"{sh} server{f' running {area}' if area else ''} just restarted. Expect things to reset")
    c = now_data.get("community") or {}
    best, mine = c.get("best"), c.get("mine")
    if best and mine and best["shard_id"] != mine["shard_id"] and best.get("reporters", 0) >= 2 \
            and (best.get("score") or 0) - (mine.get("score") or 0) >= 20:
        out.append(f"{best.get('name')} is running better than {sh} right now, server at {best.get('server_fps')} fps")
    return out[:3]
