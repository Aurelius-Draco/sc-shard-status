"""1.5.2: Send feedback. The answers are checked here too, the RSI handle goes only with a reply, five a day from
this PC, and a screenshot picked for it has the session QR code blacked out. Made-up handles only."""
import json
import types

import pytest

from scstatus import app as app_mod
from scstatus import screenshots


class _Store:
    def __init__(self):
        self.m = {}

    def meta(self, k, d=None):
        return self.m.get(k, d)

    def set_meta(self, k, v):
        self.m[k] = v


class _Community:
    def __init__(self):
        self.sent = []

    def send_feedback(self, body):
        self.sent.append(body)
        return {"ok": True, "id": "0123456789ab"}


def _app(channel="LIVE"):
    a = types.SimpleNamespace(store=_Store(), community=_Community(), channel=channel)
    a.send_feedback = types.MethodType(app_mod.App.send_feedback, a)
    for n in ("FEEDBACK_KINDS", "FEEDBACK_OFTEN", "FEEDBACK_MATTERS", "FEEDBACK_PER_DAY", "HANDLE_RX", "PICTURE_RX"):
        setattr(a, n, getattr(app_mod.App, n))
    return a


def _good(**kw):
    b = {"kind": "feature", "area": "companion-history", "want": "Show how long each contract took.", "why": "Pick better bounties.",
         "often": "every", "matters": "lots", "similar": "", "reply": False, "handle": "Made_Up_Hauler", "image": None}
    b.update(kw)
    return b


def test_a_request_goes_with_the_channel_and_no_handle_unless_a_reply_is_asked_for():
    a = _app("PTU")
    r = a.send_feedback(_good())
    assert r["ok"] and r["id"] == "0123456789ab" and not r["reply"]
    sent = a.community.sent[0]
    assert sent["channel"] == "PTU" and "handle" not in sent and "image" not in sent and "similar" not in sent
    assert not sent["reply"]
    assert "Spectrum" not in r["message"]


def test_a_reply_needs_an_rsi_handle_and_sends_it():
    a = _app()
    with pytest.raises(ValueError, match="RSI handle"):
        a.send_feedback(_good(reply=True, handle="no spaces allowed"))
    with pytest.raises(ValueError, match="RSI handle"):
        a.send_feedback(_good(reply=True, handle=""))
    assert not a.community.sent
    r = a.send_feedback(_good(reply=True, handle="Pretend_Pilot-7"))
    assert r["reply"] and "Spectrum" in r["message"]
    assert a.community.sent[0]["handle"] == "Pretend_Pilot-7"


@pytest.mark.parametrize("bad, words", [({"kind": "rant"}, "what kind"), ({"want": "short"}, "what you'd like"),
                                        ({"why": ""}, "help you do"), ({"often": "always"}, "how often"),
                                        ({"image": "data:image/gif;base64,R0lGOD"}, "PNG, JPEG or WebP"),
                                        ({"image": "https://example.com/x.png"}, "PNG, JPEG or WebP")])
def test_bad_answers_are_turned_back_before_anything_is_sent(bad, words):
    a = _app()
    with pytest.raises(ValueError, match=words):
        a.send_feedback(_good(**bad))
    assert not a.community.sent


def test_a_picture_goes_as_a_data_url():
    a = _app()
    a.send_feedback(_good(image="data:image/webp;base64,UklGRhoAAABXRUJQ"))
    assert a.community.sent[0]["image"].startswith("data:image/webp;base64,")


def test_five_a_day_from_this_pc():
    a = _app()
    for _ in range(5):
        a.send_feedback(_good())
    with pytest.raises(ValueError, match="5 today"):
        a.send_feedback(_good())
    assert len(a.community.sent) == 5
    # Only today's count is kept
    assert len(json.loads(a.store.meta("feedback_sent"))) == 1


def test_a_failed_send_does_not_count():
    a = _app()

    def fail(body):
        raise ValueError("Verse Shards answered 500.")
    a.community.send_feedback = fail
    with pytest.raises(ValueError, match="500"):
        a.send_feedback(_good())
    assert a.store.meta("feedback_sent") is None


def test_a_screenshot_for_feedback_is_shrunk_with_the_qr_code_blacked_out(tmp_path):
    cv2 = pytest.importorskip("cv2")
    np = pytest.importorskip("numpy")
    img = np.full((1440, 2560, 3), 200, dtype=np.uint8)
    try:
        qr = cv2.QRCodeEncoder.create().encode("https://example.com/made-up-session")
    except Exception:
        pytest.skip("this OpenCV can't make a QR code")
    qr = cv2.resize(qr, (qr.shape[1] * 8, qr.shape[0] * 8), interpolation=cv2.INTER_NEAREST)
    qh, qw = qr.shape[:2]
    img[40:40 + qh, 2560 - 60 - qw:2560 - 60] = cv2.cvtColor(qr, cv2.COLOR_GRAY2BGR)
    cv2.imwrite(str(tmp_path / "ScreenShot-2026-11-08_10-00-00-000.jpg"), img)
    out = screenshots.feedback_picture(tmp_path, "ScreenShot-2026-11-08_10-00-00-000.jpg")
    assert out and out[1] == "image/jpeg"
    small = cv2.imdecode(np.frombuffer(out[0], dtype=np.uint8), cv2.IMREAD_COLOR)
    assert small.shape[1] == 1600
    found, _ = cv2.QRCodeDetector().detect(small)
    assert not found
    # The rest of the picture is left alone
    assert small[800, 400].mean() > 150


def test_only_a_screenshot_in_the_folder_can_be_picked(tmp_path):
    assert screenshots.feedback_picture(tmp_path, "../secret.jpg") is None
    assert screenshots.feedback_picture(tmp_path, "missing.jpg") is None
