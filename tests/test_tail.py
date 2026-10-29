from conftest import FIX
from scstatus.logparse import LogTail


def test_tail_follows_appends_and_new_log(tmp_path):
    lines = (FIX / "wikelo_sample.log").read_text().splitlines(keepends=True)
    log = tmp_path / "Game.log"
    log.write_text("".join(lines[:10]))
    seen, sessions = [], []
    t = LogTail(log, on_event=lambda e, raw: seen.append(e["kind"]), on_new_session=sessions.append)
    t.poll()
    with open(log, "a") as f:
        f.write("".join(lines[10:]))
        f.write(lines[-1].rstrip("\n"))         # a half-written last line
    t.poll()
    t.poll()                                    # idle poll flushes the pending line
    s = t.session
    assert s.shard_id == "pub_ape1a_12881860_090" and len(s.contracts) == 3 and s.clean_exit
    assert "join_pu" in seen and "contract_accepted" in seen
    # The game starts a new log: a fresh session
    log.write_text(lines[0].replace("29 Oct 26", "30 Oct 26"))
    t.poll()
    assert len(sessions) == 2 and t.session is not s and t.session.shard_id is None


def test_tail_waits_for_second_line_of_notification(tmp_path):
    log = tmp_path / "Game.log"
    head = (FIX / "wikelo_sample.log").read_text().splitlines(keepends=True)[:3]
    first = ('<2026-10-29T01:13:00.000Z> [Notice] <SHUDEvent_OnNotification> Added notification '
             '"Objective Complete: Deliver Vestal Water\n')
    second = ('<2026-10-29T01:13:00.000Z> : " [71] to queue. New queue size: 1, MissionId: '
              '[11111111-2222-3333-4444-555555555555], ObjectiveId: [dropoff_x_0] [Team_CoreGameplayFeatures][Missions]\n')
    log.write_text("".join(head) + first)
    seen = []
    t = LogTail(log, on_event=lambda e, raw: seen.append(e))
    t.poll()
    t.poll()                                    # idle: still waiting for the second line
    assert not any(e["kind"] == "objective_complete" for e in seen)
    with open(log, "a") as f:
        f.write(second)
    t.poll()
    done = [e for e in seen if e["kind"] == "objective_complete"]
    assert done and done[0]["objective_id"] == "dropoff_x_0" and done[0]["name"] == "Deliver Vestal Water"


def test_tail_split_multibyte_character(tmp_path):
    log = tmp_path / "Game.log"
    line = '<2026-10-29T01:12:00.000Z> [Notice] <SHUDEvent_OnNotification> Added notification "Contract Accepted:  Café Run: " [70] to queue. New queue size: 1, MissionId: [11111111-2222-3333-4444-555555555555], ObjectiveId: [] [Team_X]\n'
    data = line.encode("utf-8")
    cut = data.index("é".encode()) + 1
    log.write_bytes(data[:cut])
    seen = []
    t = LogTail(log, on_event=lambda e, raw: seen.append(e))
    t.poll()
    with open(log, "ab") as f:
        f.write(data[cut:])
    t.poll()
    assert [e["name"] for e in seen if e["kind"] == "contract_accepted"] == ["Café Run"]
