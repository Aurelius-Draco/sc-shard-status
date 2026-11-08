"""Pop-up alerts while you play: a Windows notification (and a sound, if you want one) when something goes wrong.

Checked every 10 seconds from the overlay readings and Game.log the app is already following:
  - the server's fps falls off a cliff
  - the server node you're on restarts
  - packet loss
  - you're disconnected with an error
  - a known problem turns up in the log (checked every 3 minutes over the last 10)
Each kind of alert is shown at most once every 10 minutes, so a bad server doesn't nag.

Windows hides notifications over full-screen games (Settings, System, Notifications, "Turn on do not disturb
automatically when playing a game"). Borderless window mode, a second screen, or the sound gets around that.
"""

import collections
import os
import statistics as st
import subprocess
import threading
import time

from .config import FROZEN, say

EVERY_S = 10
PROBLEM_EVERY_S = 180
QUIET_S = 600
DISC_SETTLE_S = 8                                # a disconnect is only judged once this long has passed (a quit may follow)
APP_ID = "AureliusDraco.SCShardStatus"          # set on the installer's Start menu shortcut
PS_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

TOAST_PS = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$x = $t.GetElementsByTagName('text')
$x.Item(0).AppendChild($t.CreateTextNode($env:SCSS_TITLE)) > $null
$x.Item(1).AppendChild($t.CreateTextNode($env:SCSS_BODY)) > $null
$n = [Windows.UI.Notifications.ToastNotification]::new($t)
$n.Tag = $env:SCSS_TAG
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:SCSS_APPID).Show($n)
"""


def windows_notify(title, body, tag="scss", sound=False):
    """Show a Windows notification. Title and text go through environment variables, never into the script."""
    if os.name != "nt":
        return False
    env = dict(os.environ, SCSS_TITLE=title[:120], SCSS_BODY=body[:300], SCSS_TAG=tag[:60],
               SCSS_APPID=APP_ID if FROZEN else PS_APP_ID)
    try:
        subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-Command", TOAST_PS],
                         env=env, creationflags=0x08000000, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        say(f"Couldn't show a notification ({e}).")
        return False
    if sound:
        try:
            import winsound
            winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS | winsound.SND_ASYNC)
        except Exception:
            pass
    return True


def _median(vals):
    vals = [v for v in vals if v is not None]
    return st.median(vals) if vals else None


class Alerts:
    def __init__(self, app, notify=windows_notify, clock=time.time):
        self.app = app
        self.notify = notify
        self.clock = clock
        self.last = {}                         # alert key -> when it was last shown
        self.recent = collections.deque(maxlen=20)
        self.disc_seen = None
        self.problem_at = 0
        self.problems_seen = set()
        self.restarts_seen = {}                # server name -> confirmed restarts already alerted on
        self.unplayable = None                 # {since, fps, checked, findings} while the server is under 5 fps

    @property
    def mode(self):
        """'sound', 'quiet' or None (off)."""
        m = self.app.cfg.get("alerts")
        return m if m in ("sound", "quiet") else None

    def run(self, stop):
        while not stop.wait(EVERY_S):
            try:
                self.watch_unplayable()            # runs whether or not pop-up alerts are on
            except Exception as e:
                say(f"Unplayable check failed: {e}")
            if self.mode:
                try:
                    self.tick()
                except Exception as e:             # an alert check must never take the app down
                    say(f"Alert check failed: {e}")
                    from . import errors
                    errors.capture("alerts", e)

    def fire(self, key, title, body, force=False):
        now = self.clock()
        if not force and now - self.last.get(key, -1e9) < QUIET_S:
            return False
        self.last[key] = now
        self.recent.appendleft({"ts": now, "key": key, "title": title, "body": body})
        say(f"Alert: {title} {body}")
        self.notify(title, body, tag=key.split(":")[0], sound=self.mode == "sound")
        return True

    def test(self):
        return self.fire("test", "Verse Shards alerts are on",
                         "This is what an alert looks like. Over a full-screen game, Windows may hold it back; "
                         "the sound still plays if you chose one.", force=True)

    def tick(self):
        now = self.clock()
        from . import clean
        with self.app.lock:
            run = clean.current_run(list(self.app.snaps))       # this server only: a hop or relog starts afresh
        self._server([s for s in run if now - s["ts"] <= 360], now, run)
        self._disconnects()
        if now - self.problem_at >= PROBLEM_EVERY_S:
            self.problem_at = now
            self._problems(now)

    def _server(self, snaps, now, run=()):
        from . import clean
        last_min = [s for s in snaps if now - s["ts"] <= 60]
        before = [s for s in snaps if now - s["ts"] > 60]
        if len(last_min) >= 3:
            fps_now = _median(s.get("server_fps") for s in last_min)
            fps_before = _median(s.get("server_fps") for s in before) if len(before) >= 6 else None
            # A healthy server falling off a cliff, or an already-slow one dropping to almost nothing
            if fps_now is not None and ((fps_now < 8 and (fps_before is None or fps_before >= 14)) or fps_now < 5):
                was = f" (was {fps_before:.0f})" if fps_before is not None and fps_before - fps_now >= 3 else ""
                self.fire("fps", f"Server fps down to {fps_now:.0f}{was}",
                          "Expect slow elevators, laggy AI and missions that don't update. Hold off take-off, "
                          "cargo moves and anything you can't afford to lose; a server hop may help.")
            # Only loss that holds for the whole minute; short bursts of 9.0% are the overlay misread
            losses = [v for v in clean.settle([s.get("loss_pct") for s in last_min]) if v is not None]
            loss = min(losses) if len(losses) >= 8 else None
            if loss is not None and loss >= 3:
                self.fire("loss", f"Packet loss at {loss:.0f}%",
                          "Your connection to the server is dropping data. Expect rubber-banding and delays.")
        name = clean.identity(run)[1] if run else None
        if name:
            rises = clean.restart_rises([s.get("restarts") for s in run])
            seen = self.restarts_seen.setdefault(name, rises)
            if rises > seen:
                self.restarts_seen[name] = rises
                self.fire("restart", "The server you're on just restarted",
                          "Items in transit, hangar requests and contract steps can go missing around a restart. "
                          "Check before you carry on.")

    def _disconnects(self):
        s = self.app.session
        if not s:
            return
        n = len(s.disconnects)
        if self.disc_seen is None or n < self.disc_seen:      # first look, or a new Game.log
            self.disc_seen = n
            return
        from .logparse import NORMAL_CAUSES
        # Wait a few seconds after a disconnect: a quit written just after it means you quit, not a kick
        now = time.time()
        fresh = [i for i, d in enumerate(s.disconnects) if i >= self.disc_seen and d.get("ts") and now - d["ts"] < DISC_SETTLE_S]
        if fresh:
            n = fresh[0]
        for d in s.disconnects[self.disc_seen:n]:
            if d.get("to_menu") and d.get("by_server"):
                self.fire("disconnect", "The server sent you back to the menu",
                          "You didn't choose Exit to Menu, so the server ended your session. Anything you were doing "
                          "may need redoing. \"What's gone wrong?\" on the dashboard looks at what happened just before.")
            elif d["cause"] not in NORMAL_CAUSES:
                self.fire("disconnect", f"Disconnected (error {d['cause']})",
                          f"{d.get('reason') or 'The game lost the server.'} When you're back, press "
                          "\"What's gone wrong?\" on the dashboard.")
        self.disc_seen = n

    def _problems(self, now):
        if not self.app.session or not self.app.game_found:
            return
        from .diagnose import diagnose
        with self.app.lock:
            snaps = list(self.app.snaps)
        try:
            res = diagnose(self.app.game_dir / "Game.log", self.app.library, self.app.names, snaps, lookback_min=10,
                           now=now, session=self.app.session)
        except Exception:
            return
        for f in res.get("findings", []):
            # Only what happened in the last 15 minutes: a crash at the end of an old Game.log isn't news when
            # the app starts up hours later
            when = f.get("last_ts") or f.get("first_ts")
            if when and when < now - 900:
                continue
            # Library problems, and the contract checks (deliveries not counting). Slow servers, restarts, packet
            # loss and disconnects are covered by the live checks above.
            key = f.get("rule_id") or ("contract:" + f["title"] if f.get("area") == "Contracts" else None)
            if not key or f.get("kind", "problem") != "problem" or f.get("severity") not in ("high", "medium") \
                    or key in self.problems_seen:
                continue
            self.problems_seen.add(key)
            self.fire("problem:" + key, f["title"], (f.get("explain") or "")[:220])

    def watch_unplayable(self, now=None):
        """Server under 5 fps: run What's gone wrong? over the last 10 minutes straight away, then again every
        3 minutes while it stays that low, so the Now tab can say what the log shows. Clears once it recovers."""
        from . import score
        now = now or self.clock()
        with self.app.lock:
            snaps = list(self.app.snaps)
        a = score.assess(snaps, now=now)
        if not a.get("unplayable"):
            self.unplayable = None
            return None
        u = self.unplayable
        if u is None:
            u = self.unplayable = {"since": now, "fps": a["server_fps_now"], "checked": None, "findings": []}
        u["fps"] = a["server_fps_now"]
        if u["checked"] is None or now - u["checked"] >= PROBLEM_EVERY_S:
            u["findings"] = self._check(now, snaps)
            u["checked"] = now
            say(f"Server unplayable ({u['fps']} fps). Log check found {len(u['findings'])} thing(s).")
        return u

    def _check(self, now, snaps):
        """The same check as the What's gone wrong? button, last 10 minutes. Problems only, newest first."""
        if not self.app.session or not self.app.game_found:
            return []
        from .diagnose import diagnose
        try:
            res = diagnose(self.app.game_dir / "Game.log", self.app.library, self.app.names, snaps, lookback_min=10,
                           now=now, session=self.app.session)
        except Exception:
            return []
        out = [{"title": f["title"], "severity": f.get("severity"), "rule_id": f.get("rule_id")}
               for f in res.get("findings", []) if f.get("kind", "problem") == "problem"
               and f["title"] != "Server running very slowly"]      # the alarm already says that
        return out[:4]

    def info(self):
        return {"mode": self.mode, "recent": list(self.recent)[:10]}
