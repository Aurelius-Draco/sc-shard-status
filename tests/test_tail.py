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
