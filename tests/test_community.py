"""Sharing with the community board: what goes in a summary, and that nothing is sent while sharing is off."""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scstatus import community


def snaps(n=60, now=None, shard="pub_apse2a_12881860_090", restart_at=None):
    now = now or time.time()
    out = []
    for i in range(n):
        out.append({"ts": now - (n - i) * 5, "ok": True, "shard_id": shard, "server_name": "pub-x-game-07",
                    "server_fps": 20 + (i % 3) * 0.5, "server_fps_min": 19.0, "hitches": 0,
                    "restarts": 4 + (1 if restart_at is not None and i >= restart_at else 0),
                    "pop_shard": 430, "pop_srv": 37, "ping_ms": 31.0, "loss_pct": 0.0, "client_fps": 100})
    return out


def test_summary_is_medians_and_restart_rise():
    now = time.time()
    s = community.summarise(snaps(now=now), now)
    assert s["server_fps"] == 20.5 and s["readings"] == 60
    assert s["restarts"] == 0          # the node's lifetime count (4) isn't news
    s = community.summarise(snaps(now=now, restart_at=50), now)
    assert s["restarts"] == 1


def test_summary_needs_recent_readings_on_one_shard():
    now = time.time()
    assert community.summarise(snaps(n=2, now=now), now) is None
    assert community.summarise(snaps(now=now - 3600), now) is None


def test_payload_has_nothing_identifying():
    now = time.time()
    p = community.shard_report(community.summarise(snaps(now=now), now), "0123456789abcdef", "12913470",
                               [{"rule_id": "cargo.no_box_size"}], "1.0")
    assert set(p) == {"v", "kind", "install", "build", "ts", "shard_id", "server", "server_fps", "server_fps_min",
                      "server_fps_max", "hitches", "restarts", "pop_shard", "pop_srv", "ping_ms", "loss_pct",
                      "issues", "readings", "app"}
    assert p["server"] == "07" and p["ping_ms"] == 30 and p["ts"] % 60 == 0


class _Fake:
    def __init__(self, cfg, s):
        self.cfg, self.snaps, self.lock, self.last_result, self.build = cfg, s, threading.RLock(), None, "12913470"

        class St:
            def install_id(self):
                return "0123456789abcdef"
        self.store = St()


def _server(log):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            log.append(json.loads(self.rfile.read(int(self.headers["content-length"]))))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"ok":true}')

        def do_GET(self):
            log.append("board")
            body = json.dumps({"reporters": 2, "updated": time.time(), "regions": [{"name": "Australia", "shards": [
                {"shard_id": "pub_apse2a_12881860_020", "score": 100, "cls": "good"},
                {"shard_id": "pub_apse2a_12881860_090", "score": 60, "cls": "ok"}]}]}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def test_nothing_sent_when_off_and_one_summary_when_on():
    log = []
    srv = _server(log)
    try:
        app = _Fake({"share_readings": False, "community_board": False}, snaps())
        c = community.Community(app, f"http://127.0.0.1:{srv.server_address[1]}", "1.0")
        c.tick()
        assert log == []
        app.cfg.update(share_readings=True, community_board=True)
        c.tick()
        c.tick()                                 # second tick inside 5 minutes sends nothing more
        assert log.count("board") == 1
        sent = [x for x in log if x != "board"]
        assert len(sent) == 1 and sent[0]["shard_id"] == "pub_apse2a_12881860_090"
        assert c.share_status == "sharing"
        v = c.region_view("pub_apse2a_12881860_090", "apse2")
        assert v["region"] == "Australia" and v["mine"]["score"] == 60 and v["best"]["score"] == 100
    finally:
        srv.shutdown()
