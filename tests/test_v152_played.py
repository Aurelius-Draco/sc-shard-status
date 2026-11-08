"""1.5.2: the login queue, why your ship was lost, blueprints you've earned (and a want list), and one card per
session for History. Made-up handles only."""
import time
import types

from scstatus import app as app_mod
from scstatus import played
from scstatus.logparse import Session, contract_title, parse_line
from scstatus.store import Store

T = "2026-11-08T"


def _feed(lines, s=None):
    s = s or Session("Game.log")
    for raw in lines:
        s.add(parse_line(raw))
    return s


def _note(ts, text, mid="00000000-0000-0000-0000-000000000000"):
    return (f'<{T}{ts}Z> [Notice] <SHUDEvent_OnNotification> Added notification "{text}: " [5] to queue. '
            f"New queue size: 1, MissionId: [{mid}], ObjectiveId: [] [Team_CoreGameplayFeatures][Missions][Comms]")


def test_login_queue_is_read_and_cleared_once_you_are_in():
    s = _feed([f"<{T}05:33:44.492Z> [Notice] <AccountLoginQueueStatus> Received a queue status update message with values: "
               "queue name global - position 37 - eta (seconds) 410 [Team_GameServices][Login]"])
    assert s.queue["position"] == 37 and s.queue["eta_s"] == 410
    _feed([f"<{T}05:40:00.000Z> [Notice] <Join PU> address[1.2.3.4] port[64300] shard[pub_apse2a_12913470_090] locationId[-1]"], s)
    assert s.queue is None


def test_your_ship_lost_with_the_reason_never_who():
    s = _feed([
        f"<{T}06:35:56.649Z> [Notice] <AccountLoginCharacterStatus_Character> Character: createdAt 1 - updatedAt 2 - geid 111222333444 "
        "- accountId 5 - name Test_Pilot - state STATE_CURRENT [Team_GameServices][Login]",
        f"<{T}07:00:00.000Z> [Notice] <Vehicle Destroyed> Vehicle 'ORIG_m80_9001' [9001] class 'ORIG_m80' (owner player [111222333444], "
        "driver [0]) destroyed: reason [SelfDestruct] level [0] -> [2] flags [2022] killer 'Test_Pilot' [111222333444] authority [0] [Team_CGP4][Vehicle]",
        f"<{T}07:10:00.000Z> [Notice] <Vehicle Destroyed> Vehicle 'DRAK_Cutlass_Black_9002' [9002] class 'DRAK_Cutlass_Black' (owner player [111222333444], "
        "driver [111222333444]) destroyed: reason [Combat] level [0] -> [1] flags [2022] killer 'Made_Up_Other' [555] authority [0] [Team_CGP4][Vehicle]",
        f"<{T}07:10:05.000Z> [Notice] <Vehicle Destroyed> Vehicle 'DRAK_Cutlass_Black_9002' [9002] class 'DRAK_Cutlass_Black' (owner player [111222333444], "
        "driver [0]) destroyed: reason [Combat] level [1] -> [2] flags [2022] killer 'Made_Up_Other' [555] authority [0] [Team_CGP4][Vehicle]",
        f"<{T}07:20:00.000Z> [Notice] <Vehicle Destroyed> Vehicle 'ANVL_C8X_Pisces_Expedition_PU_AI_CRIM_9003' [9003] class "
        "'ANVL_C8X_Pisces_Expedition_PU_AI_CRIM' (owner player [0], driver [0]) destroyed: reason [Combat] level [0] -> [2] flags [0] "
        "killer 'Test_Pilot' [111222333444] authority [0] [Team_CGP4][Vehicle]",
        f"<{T}07:30:00.000Z> [Notice] <Vehicle Destroyed> Vehicle 'AEGS_Gladius_9004' [9004] class 'AEGS_Gladius' (owner player [777], "
        "driver [777]) destroyed: reason [Combat] level [0] -> [2] flags [0] killer 'Test_Pilot' [111222333444] authority [0] [Team_CGP4][Vehicle]",
    ])
    lost = s.summary()["ships_lost"]
    assert [(x["ship"], x["reason"]) for x in lost] == [("ORIG_m80", "SelfDestruct"), ("DRAK_Cutlass_Black", "Combat")]
    assert all(set(x) == {"ts", "ship", "reason"} for x in lost)          # no killer, owner or ids kept
    assert "Made_Up_Other" not in repr(s.summary()) and "111222333444" not in repr(s.summary())
    c = played.card(s.summary())
    assert [x["reason"] for x in c["lost"]] == ["Self destruct", "Combat"]


def test_rep_is_a_number_only_when_the_game_states_one():
    assert contract_title("Reclusive Bounty: Made Up | High Risk [200 Rep]") == ("Reclusive Bounty: Made Up | High Risk", "200 Rep")
    assert contract_title("Bounty Assignment: Made Up (HRT) [4000/8000 Rep] [BP]*") == ("Bounty Assignment: Made Up (HRT)", "rep by rank")
    assert contract_title("Seeking Experienced Combat Pilots") == ("Seeking Experienced Combat Pilots", None)


def test_blueprints_with_the_contract_that_gave_them_and_their_group():
    mid = "0d902cfe-0627-4dd2-a27c-320499269dbc"
    s = _feed([
        _note("23:20:00.000", "Contract Accepted: Bounty Assignment: Made Up (HRT) <EM4>[4000/8000 Rep] [BP]*</EM4>", mid),
        _note("23:28:43.465", "Contract Complete: Bounty Assignment: Made Up (HRT) <EM4>[4000/8000 Rep] [BP]*</EM4>", mid),
        _note("23:28:45.154", "Received Blueprint: Oracle Helmet"),
        _note("23:28:45.502", "Received Blueprint: Quartz Energy SMG Battery (45 cap)"),
        _note("23:59:00.000", "Received Blueprint: Coda \"Big Boss\" Pistol"),
        _note("23:59:30.000", "Journal Entry Added: Tracker License Earned (MRT)"),
    ])
    bps = s.summary()["blueprints"]
    assert [b["name"] for b in bps] == ["Oracle Helmet", "Quartz Energy SMG Battery (45 cap)", 'Coda "Big Boss" Pistol']
    assert bps[0]["contract"] == "Bounty Assignment: Made Up (HRT)" and bps[2]["contract"] is None
    assert [j["text"] for j in s.summary()["journal"]] == ["Tracker License Earned (MRT)"]
    groups = {n: played.GROUPS[played.group_of(n)] for n in (
        "Oracle Helmet", "Quartz Energy SMG Battery (45 cap)", 'Coda "Big Boss" Pistol', "Pulse Laser Pistol",
        "Sledge III Mass Driver Cannon", "Attrition-3 Repeater", "Dust Devil Armor Core", "Spettro Shoes", "IceBox",
        "R97 Shotgun Magazine (18 cap)", "Testudo Legs Clanguard")}
    assert groups == {"Oracle Helmet": "Armour", "Quartz Energy SMG Battery (45 cap)": "Magazines and batteries",
                      'Coda "Big Boss" Pistol': "FPS weapons", "Pulse Laser Pistol": "FPS weapons",
                      "Sledge III Mass Driver Cannon": "Ship weapons", "Attrition-3 Repeater": "Ship weapons",
                      "Dust Devil Armor Core": "Armour", "Spettro Shoes": "Armour", "IceBox": "Other",
                      "R97 Shotgun Magazine (18 cap)": "Magazines and batteries", "Testudo Legs Clanguard": "Armour"}
    # Across sessions: first time kept, repeats counted, this session's are fresh
    old = {"blueprints": [{"ts": 100, "name": "Oracle Helmet", "contract": None}, {"ts": 90, "name": "Monde Arms", "contract": None}]}
    got = played.blueprints([old], s)
    oh = next(b for b in got if b["name"] == "Oracle Helmet")
    assert oh["times"] == 2 and oh["ts"] == 100 and oh["fresh"]
    assert not next(b for b in got if b["name"] == "Monde Arms")["fresh"]


def test_want_list_and_a_wanted_blueprint_coming_off_it(tmp_path):
    st = Store(tmp_path / "s.db")
    w = played.WantList(st)
    w.add("  F55   LMG ")
    w.add("Spettro Shoes")
    w.add("spettro shoes")
    assert w.get() == ["F55 LMG", "Spettro Shoes"]
    try:
        w.add("Oracle Helmet", earned=["Oracle Helmet"])
        raise AssertionError("should refuse one you have")
    except ValueError as e:
        assert "already have" in str(e)
    assert w.received(["Spettro Shoes", "Something Else"]) == ["Spettro Shoes"]
    assert w.get() == ["F55 LMG"]
    # The app takes a wanted one off the list when it turns up in the log, and says so
    a = types.SimpleNamespace(store=st, session=Session("Game.log"), alerts=types.SimpleNamespace(mode=None))
    for n in ("check_blueprints",):
        setattr(a, n, types.MethodType(getattr(app_mod.App, n), a))
    a.want = w
    a.news = __import__("collections").deque(maxlen=20)
    a.check_blueprints()
    a.session.add(parse_line(_note("10:00:00.000", "Received Blueprint: F55 LMG")))
    assert a.check_blueprints() == ["F55 LMG"] and w.get() == []
    assert "moved to FPS weapons" in a.news[-1]["text"]


def test_a_session_card_and_notes(tmp_path):
    st = Store(tmp_path / "s.db")
    start = time.mktime((2026, 11, 8, 8, 24, 0, 0, 0, -1))
    summ = {"start": start, "end": start + 159 * 60, "minutes": 159, "shards": ["pub_apse2a_12913470_090"],
            "contracts": [{"name": "x", "title": "Verified Bounty: Made Up", "accepted": start, "result": "complete", "rep": "rep by rank"},
                          {"name": "y", "title": "Reclusive Bounty: Made Up", "accepted": start, "result": "failed", "rep": "200 Rep"}],
            "blueprints": [{"ts": start, "name": "Oracle Helmet"}], "journal": [{"ts": start, "text": "Tracker License Earned (MRT)"}],
            "problems": [{"ts": start + 120, "title": "Joining the universe took 106 seconds", "rule_id": "loading-slow-join"}],
            "ships_lost": []}
    snaps = [{"ts": start + i * 60, "server_fps": 21, "ping_ms": 40, "loss_pct": 0, "shard_id": "pub_apse2a_12913470_090",
              "server_name": "pub-apse2a-12913470-game-22"} for i in range(10)]
    c = played.card(summ, snaps, None, [start + 300], None)
    assert c["day"] == "Sun 8 Nov" and c["time"] == "8:24 am to 11:03 am" and c["dur"] == "2 h 39 min"
    assert c["score"] >= 90 and c["health"] == "good" and c["word"] == "Healthy"
    assert (c["accepted"], c["completed"], c["failed"], c["moments"]) == (2, 1, 1, 1)
    assert c["shards"][0]["servers"] == ["22"]
    # Without overlay readings there's no score, not a 0
    c2 = played.card(summ, [], None, [], None)
    assert c2["score"] is None and not c2["overlay"] and c2["word"] == "No score"
    a = types.SimpleNamespace(store=st)
    a.session_note = types.MethodType(app_mod.App.session_note, a)
    a.session_note(c["id"], rating="good", note="x" * 300, auec_start="1,250,000", auec_end="1,980,000")
    n = st.session_notes()[c["id"]]
    assert n["rating"] == "good" and len(n["note"]) == 200 and n["auec_start"] == 1250000 and n["auec_end"] == 1980000
    a.session_note(c["id"], rating="meh")
    assert st.session_notes()[c["id"]]["rating"] is None and st.session_notes()[c["id"]]["note"] == "x" * 200


def test_the_pirate_question_only_follows_a_ship_lost_in_combat():
    from scstatus import groups
    from tests.test_v13 import _App, _Comm
    s = Session()
    now = time.time()
    s.travel = [{"ts": now - 300, "kind": "location", "code": "Stanton1_CuttersRig"}]
    s.deaths = [{"ts": now - 60, "ship": "ORIG_m80", "collision": False}]
    s.vehicles_lost = [{"ts": now - 58, "ship": "ORIG_m80", "reason": "SelfDestruct"}]
    g = groups.Groups(_App(s), _Comm())
    assert g.pirate_offer(now) is None                       # you self-destructed: nobody to report
    s.vehicles_lost.append({"ts": now - 20, "ship": "DRAK_Cutlass_Black", "reason": "Combat"})
    assert g.pirate_offer(now)["ship"] == "DRAK Cutlass Black"


def test_licences_contract_kinds_stats_and_your_week():
    mid = "0d902cfe-0627-4dd2-a27c-320499269dbc"
    s = _feed([
        _note("13:30:00.000", "Contract Accepted: Tracker License Certification <EM4>[50 Rep]</EM4>", mid),
        _note("13:41:00.000", "Contract Complete: Tracker License Certification <EM4>[50 Rep]</EM4>", mid),
        _note("13:41:05.000", "Journal Entry Added: Tracker License Earned (MRT)"),
        _note("13:50:00.000", "Journal Entry Added: Jurisdiction: Made Up Industries"),
    ])
    lic = played.licences([], s)
    assert [(l["name"], l["contract"]) for l in lic] == [("Tracker License (MRT)", "Tracker License Certification")]
    assert played.card(s.summary())["journal"] == ["Tracker License Earned (MRT)"]          # a jurisdiction isn't a licence
    k = played.contract_kind
    assert k("Verified Bounty: Made Up | VLRT (Solo Craft, Minimal Support)") == "Verified Bounty (VLRT)"
    assert k("Reclusive Bounty: Made Up | High Risk") == "Reclusive Bounty (High Risk)"
    assert k("Neutralize UEE Threat: Madeup Person") == "Neutralize UEE Threat"
    assert k('New Defense Contract: Made "Nick" Up') == "New Defense Contract"
    assert k("Mercenary: Retake Outpost") == "Mercenary: Retake Outpost" and k("Data Transfer") == "Data Transfer"
    summ = {"contracts": [
        {"name": "a", "title": "Verified Bounty: A B | HRT", "accepted": 1, "ended": 601, "result": "complete", "rep": "rep by rank"},
        {"name": "b", "title": "Verified Bounty: C D | HRT", "accepted": 1, "ended": 1201, "result": "complete", "rep": "rep by rank"},
        {"name": "c", "title": "Verified Bounty: E F | HRT", "accepted": 0, "ended": 300, "result": "failed", "rep": "rep by rank"},
        {"name": "d", "title": "Data Transfer", "accepted": 0, "ended": 900, "result": "complete", "rep": "100 Rep"}],
        "blueprints": [{"name": "Aves Arms", "ts": 905, "contract": "Data Transfer"}]}
    st = {r["kind"]: r for r in played.contract_stats([summ])}
    assert st["Verified Bounty (HRT)"]["completed"] == 2 and st["Verified Bounty (HRT)"]["success"] == 67
    assert st["Verified Bounty (HRT)"]["typical_min"] == 20
    assert st["Data Transfer"]["blueprints"] == [{"name": "Aves Arms", "times": 1}] and st["Data Transfer"]["rep"] == ["100 Rep"]
    now = time.time()
    cards = [{"id": "1", "start": now - 3600, "minutes": 90, "completed": 5, "accepted": 6, "blueprints": [1], "journal": [],
              "problems": [1, 2], "score": 80, "day": "Sun 8 Nov", "word": "Healthy"},
             {"id": "2", "start": now - 8 * 86400, "minutes": 60, "completed": 2, "accepted": 2, "blueprints": [], "journal": [],
              "problems": [], "score": None, "day": "Sat 31 Oct", "word": "No score"}]
    w = played.week(cards, now)
    assert (w["this"]["sessions"], w["this"]["minutes"], w["this"]["contracts"], w["this"]["score"]) == (1, 90, 5, 80)
    assert w["this"]["best"]["id"] == "1" and w["last"]["score"] is None and w["last"]["contracts"] == 2
