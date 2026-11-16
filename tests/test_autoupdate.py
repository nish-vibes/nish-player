"""Automatic update tests (autoupdate.py): what gets installed by itself, and when nothing happens.

Run:  python tests/test_autoupdate.py
"""
import os
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="nish-auto-"))
os.environ["LOCALAPPDATA"] = str(TMP / "local")

import engine  # noqa: E402

engine.DATA_DIR = TMP / "local" / "NiSH Player"
import settings  # noqa: E402

settings.FILE = engine.DATA_DIR / "settings.json"
import apppack  # noqa: E402
import autoupdate  # noqa: E402
import ytpack  # noqa: E402


def ok(msg):
    print("ok:", msg)


calls = []


def fake(app=None, yt=None, fits=True, pack=None, fail=None):
    """Pretend GitHub publishes this: an app update (app/yt version newer?) and a YouTube-only pack."""
    calls.clear()

    def check():
        calls.append("check")
        if fail:
            raise fail
        return {"version": "2.1.9", "youtube": "2099.01.01", "fits": fits, "app_newer": bool(app),
                "yt_newer": bool(yt), "newer": bool(app or yt)}

    def install(m, **kw):
        calls.append("install")
        return {"app": bool(m["app_newer"]), "youtube": bool(m["yt_newer"])}

    apppack.check, apppack.install = check, install
    ytpack.check = lambda: (calls.append("yt-check"), {"version": "2099.02.02", "newer": bool(pack)})[1]
    ytpack.install = lambda m, **kw: calls.append("yt-install")
    autoupdate.last.update(when=0.0, app=None, youtube=None, error="")


def main():
    assert autoupdate.enabled(), "on by default"
    told = []
    notify = lambda: told.append(1)          # noqa: E731

    fake()
    assert autoupdate.run(notify) == {"app": None, "youtube": None} and calls == ["check"] and not told
    ok("nothing new: checks, installs nothing, says nothing")

    fake(yt=True)
    assert autoupdate.run(notify) == {"app": None, "youtube": "2099.01.01"} and calls == ["check", "install"]
    assert told and autoupdate.last["youtube"] == "2099.01.01" and autoupdate.last["when"] > 0
    ok("a new yt-dlp (YouTube changed): installed by itself, the app is told")

    told.clear()
    fake(app=True, yt=True)
    assert autoupdate.run(notify) == {"app": "2.1.9", "youtube": "2099.01.01"} and told
    ok("app changes and a YouTube fix together: both installed (the app part from the next start)")

    fake(fits=False, pack=True)
    assert autoupdate.run() == {"app": None, "youtube": "2099.02.02"}
    assert calls == ["check", "yt-check", "yt-install"], calls
    ok("an older base: the YouTube-only fix instead")

    fake(fail=RuntimeError("Couldn't reach GitHub\nmore"))
    assert autoupdate.run() == {"app": None, "youtube": None}
    assert autoupdate.last["error"] == "Couldn't reach GitHub"
    ok("offline: no error shown, it tries again later")

    autoupdate.set_enabled(False)
    fake(app=True, yt=True)
    assert autoupdate.run() == {"app": None, "youtube": None} and calls == []
    assert settings.get("auto_update") is False
    autoupdate.set_enabled(True)
    ok("switched off: nothing is checked or installed")

    fake(yt=True)
    with autoupdate.LOCK:                    # the cogwheel menu is installing right now
        assert autoupdate.run() == {"app": None, "youtube": None} and calls == []
    ok("never two installations at once")

    # a failed YouTube download checks soon, but not over and over
    fake()
    done = threading.Event()
    real_run = autoupdate.run
    autoupdate.run = lambda notify=None: (real_run(), done.set())
    autoupdate.youtube_failed(lambda: None)
    assert done.wait(5) and calls == ["check"]
    calls.clear()
    autoupdate.youtube_failed(lambda: None)  # it just checked
    assert calls == []
    autoupdate.run = real_run
    ok("a failed YouTube download checks for a fix (once per half hour)")

    # timing: 20 s after start, then every 6 hours
    class Root:
        def __init__(self):
            self.queue = []

        def after(self, ms, fn):
            self.queue.append((ms, fn))
            return len(self.queue)

    r = Root()
    autoupdate.start(r, lambda: None)
    assert r.queue[0][0] == 20_000
    fake()
    done.clear()
    autoupdate.run = lambda notify=None: (real_run(), done.set())
    r.queue[0][1]()
    assert done.wait(5) and r.queue[1][0] == 6 * 3600 * 1000
    autoupdate.run = real_run
    ok("checks 20 s after start, then every 6 hours")
    print("AUTOUPDATE TESTS PASSED")


if __name__ == "__main__":
    main()
