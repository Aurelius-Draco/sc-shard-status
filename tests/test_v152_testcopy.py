"""The TEST copy fetches the newest next build from the test-next pre-release, never the player releases."""
import types

from scstatus import updater


REL = {"tag_name": "test-next", "html_url": "https://example.invalid/r", "body": "TEST build of next (abc1234)",
       "assets": [{"name": "Verse-Shards-test-1.5.1-abc1234.zip", "browser_download_url": "https://example.invalid/z", "size": 10},
                  {"name": "Verse-Shards-test-1.5.1-abc1234.zip.sha256", "browser_download_url": "https://example.invalid/s"}]}


def test_test_release_is_read_and_offered_only_to_the_test_copy(tmp_path):
    L = updater.parse_test_release(REL)
    assert L["build"] == "abc1234" and L["version"] == "TEST next abc1234" and L["sha_url"].endswith("/s")
    app = types.SimpleNamespace(cfg={"check_updates": False, "setup_version": 0})
    u = updater.Updater(app, frozen=True, store=False, test_dir=str(tmp_path), test_build="0000000")
    assert u.enabled and u.version == "TEST next 0000000"          # always checks, whatever the player switch says
    u.latest = L
    i = u.info()
    assert i["test"] and i["available"] and i["can_install"] and i["latest"] == "TEST next abc1234"
    u.test_build = "abc1234"
    assert not u.available
    # A normal copy ignores test builds and keeps the player switch
    p = updater.Updater(app, frozen=True, store=False, test_dir=None, test_build=None)
    assert not p.enabled and not p.info()["test"]


def test_the_launcher_points_at_the_new_build(tmp_path):
    updater.write_test_launcher(tmp_path, "abc1234")
    t = (tmp_path / "Start Verse Shards TEST.cmd").read_text()
    assert 'SCSTATUS_BUILD=abc1234' in t and 'app-abc1234\\SC Shard Status.exe' in t and 'SCSTATUS_DATA=%~dp0data' in t
