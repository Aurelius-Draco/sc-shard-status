"""1.5.2 small fixes: shard ids misread with a dropped or swapped digit are caught against Game.log."""
from scstatus.app import _close, _edits


def test_edits():
    assert _edits("abc", "abc") == 0
    assert _edits("abc", "ac") == 1
    assert _edits("090", "009") == 2


def test_a_dropped_digit_and_a_swap_is_a_slip_of_the_shard_in_the_log():
    real = "pub_apse2a_12881860_090"
    assert _close("pub_apse2a_1288186_009", real)      # 8 Nov 9:19, Ray's session
    assert _close("pub_apse2a_12881860_O90", real)
    assert not _close("pub_use1b_12881860_090", real)   # another region is never a slip
    assert not _close("pub_apse2a_12881860_120", real)  # a different instance number
    assert not _close("pub_apse2a_12881860_090", None)


def test_server_fps_is_checked_against_its_frame_time():
    from scstatus.overlay import parse_lines
    def sf(line):
        o = parse_lines([line])
        return o["server_fps"], o["server_ms"]
    assert sf("Server FPS: 21.8 [21.2..22.3] - 45.9ms [44.8..47.3], Hitches: 0") == (21.8, 45.9)    # agrees
    assert sf("Server FPS: 50.0 [30.0..30.0] - 33.3ms [33.3..33.3], Hitches: 0") == (30.0, 33.3)    # LAB misread
    assert sf("Server FPS: 30.0 [30.0..30.0] - 3.3ms [33.3..33.3], Hitches: 0") == (30.0, 33.3)
    assert sf("Server FPS: 7.5 [27.1..27.9] - 36.3ms [35.8..36.9], Hitches: 1") == (27.5, 36.3)
    assert sf("Server FPS: 50.0 [48.0..52.0] - 9.0ms [8.8..9.3], Hitches: 0") == (None, None)      # can't tell: dropped


def test_a_decimal_point_split_by_a_space_is_closed_up():
    from scstatus.overlay import fix_digits, parse_lines
    assert fix_digits("ping 110. 9ms") == "ping 110.9ms"
    assert fix_digits("113 . 2ms") == "113.2ms"
    assert fix_digits("pop. [shard 91, srv 10]") == "pop. [shard 91, srv 10]"     # a list stays a list
    assert parse_lines(["Net: ping 110. 9ms, loss 0.0% BwIn 222.221kbps, BwOut 50.556kbps"])["ping_ms"] == 110.9


def _session(lines):
    from scstatus import logparse
    s = logparse.Session()
    for raw in logparse.records(lines):
        ev = logparse.parse_line(raw)
        if ev:
            s.add(ev)
    return s


DISC = ('<2026-09-16T10:30:27.271Z> [Notice] <Channel Disconnected> cause=30016 reason="{r}" frame=99835 isRemote={rem} '
        'viewState=eCVS_InGame map="megamap" gamerules="SC_Default" hostType="Replicant" remoteAddr=1.2.3.4:64 [Team_Network]')
MENU = '<2026-09-16T10:30:27.287Z> [CSessionManager::RequestFrontEnd] Started - RequestFrontEndReason="OnLobbyPostGameUnload"!'
QUIT = '<2026-09-16T10:30:28.000Z> [CIG] CCIGBroker::FastShutdown'


def test_sent_back_to_the_menu_by_the_server_or_by_you():
    from scstatus.timeline import timeline
    s = _session([DISC.format(r="Remote Disconnect - Player requested disconnect", rem=1), MENU])
    assert s.disconnects[-1]["by_server"] is True
    assert [i["text"] for i in timeline(s, None) if i["group"] == "connection"] == ["The server sent you back to the menu"]
    s = _session([DISC.format(r="DisconnectCmd: disconnect light ExitToMenu", rem=0), MENU])
    assert s.disconnects[-1]["to_menu"] is True and s.disconnects[-1]["by_server"] is False
    assert [i["text"] for i in timeline(s, None) if i["group"] == "connection"] == ["Went back to the menu"]
    s = _session([DISC.format(r="Remote Disconnect - Player requested disconnect", rem=1), QUIT])     # a quit
    assert not s.disconnects[-1].get("to_menu")
    # 8 Nov, Ray's TEST copy: the menu, then the game quits in the same moment. That's you quitting, not a kick
    sysquit = ('<2026-09-16T10:30:27.287Z> [Notice] <SystemQuit> CSystem::Quit invoked with - cause=30016, reason=Quit via '
               'console command, exitCode=0, thread id=17100, main thread id=17100 [Team_Unknown][System]')
    s = _session([DISC.format(r="Remote Disconnect - Player requested disconnect", rem=1), MENU, sysquit])
    assert s.disconnects[-1]["by_server"] is False and not s.disconnects[-1]["to_menu"]
    assert "The server sent you back to the menu" not in [i["text"] for i in timeline(s, None)]
