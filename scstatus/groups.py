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


class Groups:
    def __init__(self, app, community):
        self.app, self.community = app, community
        self.poll_at = 0
        self.open = None            # are the boards switched on at the site? (None until checked)
        self.activities = []
        self.interest = []          # replies to your posts, newest first: {post, activity, handle, note, created}
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

    def post(self, kind, activity=None, note=None, spots=None, handle=None):
        ctx = self.context()
        if not ctx["shard_id"]:
            raise ValueError("Join a shard in game first, so the post can say where you are.")
        body = {"v": 1, "kind": kind, "install": self.app.store.install_id(), "shard_id": ctx["shard_id"],
                "server": ctx["server"], "system": ctx["system"], "area": ctx["area"], "area_name": ctx["area_name"]}
        if kind in ("recruit", "lfg"):
            body.update(activity=activity or None, note=(note or "").strip()[:80] or None,
                        spots=int(spots) if str(spots or "").isdigit() else None,
                        handle=(handle or "").strip() or None)
        try:
            code, d = self.community._req("/api/v1/posts", body)
        except Exception as e:
            raise ValueError(f"Couldn't reach Verse Shards ({e.__class__.__name__}).")
        if code != 200:
            raise ValueError(d.get("error") or f"Verse Shards answered {code}.")
        if d.get("key"):
            rows = [r for r in self._keys() if r.get("kind") != kind or kind == "pirate"]
            rows.append({"id": d["id"], "key": d["key"], "kind": kind, "activity": activity, "expires": d.get("expires"),
                         "spots": body.get("spots"), "shard": ctx["shard"], "area_name": ctx["area_name"],
                         "handle": body.get("handle")})
            self._save_keys(rows)
            self.poll_at = 0
        return {"pirate": "Reported. Other players see the area for 45 minutes.",
                "recruit": "Posted on Verse Shards for 2 hours. Players who are keen send their handle, and it pops up here.",
                "lfg": "Posted on Verse Shards for 2 hours. Recruiters can copy your handle and send a party invite."}[kind] \
            + (" You'd already reported this area." if d.get("duplicate") else "")

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
            row = {k: r.get(k) for k in ("id", "kind", "activity", "expires")}
            if r.get("kind") == "recruit" and r.get("shard"):
                row["chat"] = (f"{r.get('activity') or 'Group'} on {r['shard']}"
                               + (f" near {r['area_name']}" if r.get("area_name") else "")
                               + (f" looking for {r['spots']} more" if r.get("spots") else " looking for players")
                               + (f". Message {r['handle']} for an invite" if r.get("handle") else ". Press I'm interested on Verse Shards"))
            out.append(row)
        return out

    def tick(self, now=None):
        """Check for replies to your posts (and whether the boards are open) once a minute while you have a post up."""
        now = now or time.time()
        if now - self.poll_at < POLL_EVERY_S:
            return
        self.poll_at = now
        keys = self._keys()
        if self.open is None or not keys:
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
        for p in d.get("posts", []):
            for i in p.get("interested", []):
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
