"""The local dashboard: a web page served from this PC only (http://127.0.0.1).

Nothing here is reachable from other machines. Each run uses a fresh random
token, so other web pages open in your browser can't call it.
"""

import json
import os
import re
import secrets
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .config import TEST_LABEL, VERSION, say

STATIC = Path(__file__).resolve().parent / "static"


class _Server(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR lets a second copy bind a port that's already in use; ask for the port to ourselves
    allow_reuse_address = os.name != "nt"
    daemon_threads = True

    def server_bind(self):
        if os.name == "nt" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def already_running(port):
    """Is SC Shard Status already serving on this port? Returns its address or None."""
    import urllib.request
    url = f"http://127.0.0.1:{port}/"
    try:
        with urllib.request.urlopen(url, timeout=1.5) as r:
            if b"SC Shard Status v" in r.read():
                return url
    except Exception:
        return None
    return None


def start_server(app, open_browser=False):
    token = secrets.token_urlsafe(16)
    port = int(app.cfg.get("dashboard_port", 8775))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _host_ok(self):
            host = (self.headers.get("Host") or "").split(":")[0]
            return host in ("127.0.0.1", "localhost")

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body, default=str).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if "json" in ctype or "html" in ctype else ""))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if not self._host_ok():
                return self._send(403, {"error": "local only"})
            path = self.path.split("?")[0]
            qs = {k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()}
            if path in ("/", "/index.html"):
                html = (STATIC / "index.html").read_text(encoding="utf-8")
                html = html.replace("__TOKEN__", token).replace("__VERSION__", VERSION + TEST_LABEL)
                return self._send(200, html.encode("utf-8"), "text/html")
            m = re.fullmatch(r"/img/[a-z0-9-]+\.(jpg|png|webp)", path)
            if m:
                f = STATIC / path.lstrip("/")
                if not f.is_file():         # e.g. a screenshot Ray hasn't added yet: the page shows a placeholder
                    return self._send(404, b"", "text/plain")
                return self._send(200, f.read_bytes(), {"jpg": "image/jpeg", "png": "image/png", "webp": "image/webp"}[m.group(1)])
            if path == "/favicon.ico":
                ico = STATIC.parent / "assets" / "status.ico"
                return self._send(200, ico.read_bytes(), "image/x-icon") if ico.exists() else self._send(404, {})
            if path == "/api/shot":
                # A picture for the moment picker. An <img> can't send the token header, so it comes in the address.
                if not secrets.compare_digest(qs.get("t", ""), token):
                    return self._send(403, {"error": "bad token"})
                from .screenshots import thumbnail
                got = thumbnail(app.game_dir / "screenshots", qs.get("name", ""))
                return self._send(200, got[0], got[1]) if got else self._send(404, b"", "text/plain")
            if self.headers.get("X-Token") != token:
                return self._send(403, {"error": "bad token"})
            try:
                if path == "/api/now":
                    return self._send(200, app.now())
                if path == "/api/history":
                    return self._send(200, app.history())
                if path == "/api/news":
                    return self._send(200, {"news": list(app.news)[-5:]})
                if path == "/api/logbook":
                    return self._send(200, app.logbook())
                if path == "/api/contracts":
                    return self._send(200, app.contracts())
                if path == "/api/blueprints":
                    return self._send(200, app.blueprints())
                if path == "/api/sessions":
                    return self._send(200, app.sessions_cards(qs.get("page", 0)))
                if path == "/api/session":
                    return self._send(200, app.session_report(qs.get("id", "")))
                if path == "/api/pc":
                    return self._send(200, app.pc())
                if path == "/api/timeline":
                    return self._send(200, app.timeline(qs.get("minutes", 60)))
                if path == "/api/issues":
                    return self._send(200, {"version": app.library.version, "rules": app.library.listing()})
                if path == "/api/settings":
                    return self._send(200, app.settings())
                if path == "/api/gamesettings":
                    return self._send(200, app.gamesettings.state())
                if path == "/api/last":
                    return self._send(200, app.last_result or {})
                if path == "/api/groups":
                    g = app.groups
                    if g.open is None:
                        g.poll_at = 0
                        g.tick()
                    return self._send(200, {"open": g.open, "activities": g.activities, "context": g.context(),
                                            "handle": g.handle(), "mine": g.mine(), "interest": g.interest_rows()[:20],
                                            "offer": g.pirate_offer(), "error": g.error})
                if path == "/api/profile":
                    return self._send(200, {"profile": app.profiles.get()})
                if path == "/api/moment":
                    if qs.get("part") == "shots":
                        from .issues import asks_for
                        asks = asks_for(getattr(app.library, "cig_fixes", []), getattr(app.session, "branch", None),
                                        getattr(app, "build", None))
                        return self._send(200, {"shots": app.moment_shots(qs.get("ts")),
                                                "asks": [{"chip": a["chip"], "patch": a["patch"]} for a in asks]})
                    return self._send(200, app.moment(qs.get("ts")))
                if path == "/api/places":
                    return self._send(200, {"places": app.groups.places(qs.get("q", "")[:40])})
                if path == "/api/reviews":
                    return self._send(200, app.store.reviews())
                if path == "/api/about":
                    from . import about
                    au = dict(about.AUTHOR)
                    au["picture"] = f"/img/{au['picture']}" if au.get("picture") else ""
                    return self._send(200, {"author": au, "message": about.MESSAGE, "rules": about.RULES,
                                            "links": about.LINKS, "also_by": about.ALSO_BY, "version": VERSION,
                                            # the star count comes from GitHub, so only with update checks on
                                            "star": dict(about.STAR, show_count=app.updater.enabled),
                                            "coming": about.COMING})
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            except Exception as e:
                say(f"Dashboard error on {path}: {e}")
                from . import errors
                errors.capture(f"dashboard GET {path}", e)
                return self._send(500, {"error": str(e)})
            return self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._host_ok() or self.headers.get("X-Token") != token:
                return self._send(403, {"error": "not allowed"})
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n > 1_500_000:               # the largest thing posted is a profile picture (about 900 KB)
                    # Read and drop the body first (up to 20 MB), so the browser gets the answer instead of a broken pipe
                    left = min(n, 20_000_000)
                    while left > 0:
                        chunk = self.rfile.read(min(left, 65536))
                        if not chunk:
                            break
                        left -= len(chunk)
                    self.close_connection = True
                    return self._send(413, {"error": "That's too big."})
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                return self._send(400, {"error": "bad request"})
            try:
                return self._send(200, handle_post(app, self.path, body))
            except ValueError as e:
                return self._send(400, {"error": str(e)})
            except Exception as e:
                say(f"Dashboard error on {self.path}: {e}")
                from . import errors
                errors.capture(f"dashboard POST {self.path.split('?')[0]}", e)
                return self._send(500, {"error": str(e)})

    server = None
    for p in range(port, port + 10):
        try:
            server = _Server(("127.0.0.1", p), Handler)
            port = p
            break
        except OSError:
            continue
    if server is None:
        raise OSError(f"ports {port}-{port + 9} are all in use")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    if open_browser:
        webbrowser.open(url)
    return server, url


def handle_post(app, path, body):
    if path == "/api/diagnose":
        return app.run_diagnosis(body.get("minutes"), body.get("mark"))
    if path == "/api/mark":
        m = app.mark("button")
        return {"message": "Moment marked. Keep playing; \"What's gone wrong?\" will look at it.", "mark": m}
    if path == "/api/blueprints/want":
        return app.want_add(body.get("name"))
    if path == "/api/blueprints/unwant":
        return app.want_remove(body.get("name"))
    if path == "/api/session/note":
        kw = {k: body[k] for k in ("rating", "note", "auec_start", "auec_end") if k in body}
        return {"note": app.session_note(body.get("id"), **kw)}
    if path == "/api/gamesettings/save":
        return app.gamesettings.save(replace=bool(body.get("replace")))
    if path == "/api/gamesettings/restore":
        return app.gamesettings.restore(str(body.get("copy") or ""))
    if path == "/api/gamesettings/dismiss":
        return app.gamesettings_dismiss()
    if path == "/api/mark/note":
        return {"mark": app.mark_note(body.get("ts"), body.get("what"))}
    if path == "/api/groups/post":
        kind = body.get("kind")
        if kind not in ("recruit", "lfg", "pirate"):
            raise ValueError("Unknown post type.")
        msg = app.groups.post(kind, body.get("activity"), body.get("note"), body.get("spots"), body.get("handle"),
                              details=body.get("details"), hours=body.get("hours"),
                              report_kind=body.get("report_kind"), place=body.get("place"))
        if kind == "pirate" and not body.get("place"):
            app.groups.pirate_done()           # the destroyed-ship offer is answered; a report for elsewhere isn't it
        if kind == "pirate":
            return {"message": msg, "area_name": getattr(app.groups, "last_area_name", None)}
        return {"message": msg}
    if path == "/api/moment/review":
        return app.moment_review(body.get("ts"), body.get("what"), body.get("issues"))
    if path == "/api/moment/draft":
        out = app.moment_draft(body.get("ts"), body.get("what"), body.get("shots"))
        if body.get("open"):
            from .app import open_folder
            open_folder(out["folder"])
        return out
    if path == "/api/moment/open":
        from .app import open_folder
        from .config import DATA
        folder = Path(str(body.get("folder", ""))).resolve()
        if (DATA / "reports").resolve() not in folder.parents or not folder.is_dir():
            raise ValueError("unknown folder")
        open_folder(folder)
        return {"ok": True}
    if path == "/api/issue/link":
        return app.community.add_ic_link(str(body.get("issue", "")), body.get("url"), body.get("relation"), body.get("to"))
    if path == "/api/groups/extend":
        return app.groups.extend(str(body.get("id", "")))
    if path == "/api/groups/decide":
        return app.groups.decide(str(body.get("post") or ""), str(body.get("handle", "")), body.get("verdict"))
    if path == "/api/profile":
        return {"message": "Profile saved on this PC.", "profile": app.profiles.save(body.get("profile"))}
    if path == "/api/groups/close":
        return {"message": app.groups.close(str(body.get("id", "")))}
    if path == "/api/groups/dismiss":
        app.groups.pirate_done()
        return {"message": "OK."}
    if path == "/api/report":
        return app.report_draft(body.get("group", "findings"), body.get("i"))
    if path == "/api/bundle":
        out = app.report_bundle(body.get("group", "findings"), body.get("i"), body.get("text"))
        if body.get("open"):
            from .app import open_folder
            open_folder(out["folder"])
        return out
    if path == "/api/review":
        return app.review(body.get("i"), save=bool(body.get("save")), send=bool(body.get("send")))
    if path == "/api/review/send":
        d = app.send_saved_review(str(body.get("ticket", "")))
        return {"message": "Sent." + (" It already has an answer." if d.get("answer") else ""), "reviews": app.store.reviews()}
    if path == "/api/alerts/test":
        app.alerts.test()
        return {"message": "Test alert sent."}
    if path == "/api/library/check":
        return app.libsync.update_library()
    if path == "/api/usercfg":
        msg = app.set_user_cfg(body.get("name", "r_displayinfo"), body.get("on", True) is not False)
        return {"message": msg, "user_cfg": app.user_cfg_state()}
    if path == "/api/had":
        return {"message": app.community.had(body.get("rule_id", ""))}
    if path == "/api/setup":
        return {"message": app.apply_setup(body.get("choices") or {}), "settings": app.settings()}
    if path == "/api/gamedir":
        return {"message": app.set_game_dir(body.get("path", "")), "game_dir": app.cfg["game_dir"]}
    if path == "/api/settings":
        return {"message": app.save_settings(body.get("live"), body.get("screenshots"), body.get("share"), body.get("board"),
                                             body.get("updates"), body.get("library"), body.get("alerts"),
                                             body.get("errors"), body.get("hotkey")),
                "settings": app.settings()}
    if path == "/api/update/check":
        return app.updater.check()
    if path == "/api/update/install":
        return app.updater.install(app.quit)
    if path == "/api/dismiss":
        return {"message": app.dismiss(body.get("what", ""))}
    if path == "/api/open":
        from .app import open_folder
        from .config import DATA
        target = {"data": DATA, "reports": DATA / "reports"}.get(body.get("what"))
        if target is None:
            raise ValueError("unknown folder")
        target.mkdir(parents=True, exist_ok=True)
        open_folder(target)
        return {"ok": True}
    raise ValueError("unknown action")
