import json
import time
from pathlib import Path

from conftest import FIX
from scstatus import community, report, score
from scstatus.diagnose import diagnose
from scstatus.issues import Library
from scstatus.logparse import parse_file, parse_line, region_of, signature
from scstatus.names import Names
from scstatus.redact import Redactor, find_handles, leaks

LOG = FIX / "wikelo_sample.log"
GAME = FIX / "game"
LIB = Library(FIX / "mini_issues.json")


def test_session_basics():
    s = parse_file(LOG)
    d = s.summary()
    assert d["build"] == "12913470" and d["version"] == "4.10.197.2878"
    assert d["shard_id"] == "pub_ape1a_12881860_090" and region_of(d["shard_id"]) == "ape1"
    assert d["hardware"]["cpu"].startswith("AMD Ryzen") and d["hardware"]["gpu"] == "AMD Radeon RX 9070"
    assert d["hardware"]["ram_mb"] == 31653 and d["hardware"]["gpu_bench_ms"] == 24.37
    assert d["load_s"] == 55 and d["clean_exit"] and d["bad_disconnects"] == 0
    names = [c["name"] for c in d["contracts"]]
    assert names.count("Very Hungry") == 2
    vh = [c for c in d["contracts"] if c["name"] == "Very Hungry"]
    assert vh[0]["result"] == "abandoned" and vh[1]["result"] == "active"
    arrive = next(c for c in d["contracts"] if c["name"].startswith("Wikelo Arrive"))
    assert arrive["objectives"]["dropoff_x_0"]["state"] == "complete"     # joined multi-line notification
    assert d["freight_cycles"] == 2 and d["quit"]["exit_code"] == 0 and d["crash"] is None


def test_nested_tag_and_team_strip():
    ev = parse_line("<2026-10-28T23:52:24.294Z> [Error] <CSCLoadingPlatformManager::loadEntityFromXML::<lambda_1>::operator ()> "
                    "Loading Platform Manager: Failed [Team_CoreGameplayFeatures][Cargo]")
    assert ev["tag"] == "CSCLoadingPlatformManager::loadEntityFromXML::<lambda_1>::operator ()"
    assert ev["text"] == "Loading Platform Manager: Failed"


def test_signature_hides_ids():
    a = signature("X", "Request[12] for 'Someone'[770469245981] id 1793238464 at 1.2.3.4:80")
    b = signature("X", "Request[99] for 'Other'[1] id 5 at 9.9.9.9:1")
    assert a == b and "Someone" not in a


def test_diagnose_links_contract_to_cargo_error():
    s = parse_file(LOG)
    r = diagnose(LOG, LIB, Names(GAME), lookback_min=300, now=s.end + 1, session=s)
    top = r["findings"][0]
    assert top["severity"] == "high" and top["title"] == '"Very Hungry": deliveries never counted'
    assert "Berry Blend Smoothie" in top["explain"] and "aren't the cause" in top["explain"] and top["examples"]
    assert top["fields"]["elevator_cycles"] == 2 and top["fields"]["times_accepted"] == 2
    assert r["noise_lines"] == 1
    # the [SPAM n] line is read too
    cargo = next(f for f in r["findings"] if f["rule_id"] == "cargo-no-resource-container" and f["fields"].get("item_name") == "Berry Blend Smoothie")
    assert cargo["count"] == 2
    assert any(u["area"] == "CEntityComponentFreightElevatorUIProvider::FillUnstowRequest" for u in r["unknown"])


def test_report_has_disclaimer_and_steps():
    s = parse_file(LOG)
    r = diagnose(LOG, LIB, Names(GAME), lookback_min=300, now=s.end + 1, session=s)
    d = report.draft(r["findings"][0], r, {"server_fps": 21.8, "pop_shard": 435, "pop_srv": 34, "ping_ms": 24})
    assert "Aurelius_Draco" in d["body"] and "Reviewed and submitted by the player" in d["body"]
    assert "1. Accept the contract \"Very Hungry\"" in d["body"] and len(d["title"]) <= 120
    secs = {x["key"]: x for x in d["sections"]}
    assert secs["steps"]["steps"][0] == "Accept the contract \"Very Hungry\"." and len(secs["steps"]["steps"]) == 4
    assert secs["summary"]["text"].endswith("Reviewed and submitted by the player.")


def test_redaction_removes_names_ids_ips():
    lines = LOG.read_text().splitlines()
    assert find_handles(lines)[0] == "Test_Pilot"
    red = Redactor.from_lines(lines)
    out = "\n".join(red.lines(lines))
    assert not leaks(out, ["Test_Pilot"])
    assert "<YOU>" in out and "203.0.113.10" not in out


def test_review_payload_is_clean():
    s = parse_file(LOG)
    r = diagnose(LOG, LIB, Names(GAME), lookback_min=300, now=s.end + 1, session=s)
    red = Redactor.from_lines(LOG.read_text().splitlines())
    unk = r["unknown"][0]
    rid, p = community.review_request(unk, {"build": "12913470"}, red, "abc123", ["Very Hungry"])
    txt = json.dumps(p)
    assert p["checked_clean"] and "Test_Pilot" not in txt and "900000000000777" not in txt and len(rid) == 10


def test_shard_report_has_nothing_personal():
    snap = {"ts": 1793238096.48, "shard_id": "pub_apse2a_12881860_090", "server_name": "pub-apse2a-sc-alpha-4102-12974691-game-07",
            "server_fps": 21.8, "pop_shard": 435, "pop_srv": 34, "ping_ms": 24.4, "loss_pct": 0.0}
    p = community.shard_report(snap, "abc", "12913470")
    assert p["ts"] % 60 == 0 and p["ping_ms"] == 20 and p["server"] == "07"
    # Long numbers here are the build and the time, nothing else
    assert set(leaks(json.dumps(p), [])) <= {"long number"}
    assert set(p) == {"v", "kind", "install", "build", "ts", "shard_id", "server", "server_fps", "server_fps_min",
                      "server_fps_max", "hitches", "restarts", "pop_shard", "pop_srv", "ping_ms", "loss_pct", "issues"}


def _snaps(fps, n=10, **kw):
    now = time.time()
    return [dict({"ts": now - (n - i) * 10, "ok": True, "server_fps": fps, "ping_ms": 30, "loss_pct": 0,
                  "hitches": 0, "restarts": 0, "pop_shard": 400, "pop_srv": 30}, **kw) for i in range(n)]


def test_score_bands():
    good = score.assess(_snaps(21.5))
    assert good["score"] >= 95 and good["label"] == "Healthy"
    assert "Healthy shard. 400 players, 30 on your server." in good["summary"]
    bad = score.assess(_snaps(5))
    assert bad["label"] in ("Bad", "Struggling") and any("server hop" in t.lower() for t in bad["points"])
    rising = _snaps(21, restarts=0)
    for x in rising[5:]:
        x["restarts"] = 1
    restart = score.assess(rising)
    assert restart["score"] < good["score"] and any("restarted while you were on it" in t for t in restart["points"])
    before = score.assess(_snaps(21, restarts=2))      # a lifetime count that never moves is not an alarm
    assert before["score"] == good["score"] and any("at some point" in t for t in before["points"])
    assert score.assess([])["score"] is None


def test_overlay_finding_for_slow_server():
    s = parse_file(LOG)
    snaps = [{"ts": s.end - 400 + i * 30, "ok": True, "server_fps": 6} for i in range(10)]
    r = diagnose(LOG, LIB, Names(GAME), snapshots=snaps, lookback_min=300, now=s.end + 1, session=s)
    assert any(f["title"] == "Server running very slowly" for f in r["findings"])


def test_shipped_library_is_valid():
    path = Path(__file__).resolve().parent.parent / "scstatus" / "library" / "issues.json"
    if not path.exists():
        return
    lib = Library(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(lib.rules) == len(data["rules"]), "a rule failed to load"
    ids = [r["id"] for r in data["rules"]]
    assert len(ids) == len(set(ids)), "duplicate rule ids"
    blob = path.read_text(encoding="utf-8")
    assert "Aurelius" not in blob and not leaks(blob.replace("12913470", "").replace("12660092", "").replace("12572603", ""), [])
