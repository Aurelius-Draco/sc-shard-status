"""1.5.1: the Microsoft Store version. The same app from an MSIX package: the Store installs new versions, so the
app's own updater never checks or installs, set-up doesn't ask about updates, and About says where it came from."""
import types

from scstatus import app as app_mod
from scstatus import updater


def _app(cfg=None):
    return types.SimpleNamespace(cfg=cfg or {"setup_version": 99, "check_updates": True}, QUESTIONS={"updates": 2})


def test_the_store_version_never_checks_or_installs(monkeypatch):
    u = updater.Updater(_app(), version="1.5.1", frozen=True, store=True)
    monkeypatch.setattr(updater, "_get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("asked GitHub")))
    assert u.enabled is False
    info = u.check()
    assert info["store"] is True and info["can_install"] is False and info["store_url"].endswith("9PNJ4LD1LFZG")


def test_the_github_copy_still_checks():
    u = updater.Updater(_app(), version="1.5.1", frozen=True, store=False)
    assert u.enabled is True and u.info()["store"] is False and u.info()["github_copy"] is False


def test_both_copies_installed_is_noticed(tmp_path, monkeypatch):
    exe = tmp_path / "SC Shard Status.exe"
    exe.write_text("x")
    monkeypatch.setattr(updater, "GITHUB_COPY", exe)
    assert updater.Updater(_app(), frozen=True, store=True).info()["github_copy"] is True


def test_set_up_skips_the_update_question_in_the_store_version():
    a = types.SimpleNamespace(cfg={"setup_version": 0}, QUESTIONS=app_mod.App.QUESTIONS, updater=types.SimpleNamespace(store=True))
    assert "updates" not in app_mod.App.setup_ask.fget(a)
    a.updater.store = False
    assert "updates" in app_mod.App.setup_ask.fget(a)


def test_packaged_check_follows_the_override(monkeypatch):
    from scstatus import config
    monkeypatch.setenv("SCSTATUS_STORE", "1")
    assert config._packaged() is True
    monkeypatch.setenv("SCSTATUS_STORE", "0")
    assert config._packaged() is False
