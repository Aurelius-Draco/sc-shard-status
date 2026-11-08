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
