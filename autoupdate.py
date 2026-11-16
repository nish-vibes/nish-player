"""Automatic updates: the quick update (the app + YouTube support, apppack.py) installs by itself.

YouTube changes how its pages work every week or so; yt-dlp follows within days. The build workflow
checks for a new yt-dlp every few hours and publishes it in the app update (see .github/workflows).
This module brings it to the user without a click:
- about 20 seconds after the window is up, then every 6 hours while the app runs, and soon after a
  YouTube download fails (YouTube may just have changed);
- the update is downloaded, verified and checked in a new process exactly like a manual install;
  the YouTube part works from the next download, the app part from the next start (start.py falls
  back to the previous app if a new one doesn't start);
- an installation older than the published update's base gets the YouTube-only fix (ytpack.py);
- nothing is shown unless something was installed (the cogwheel menu says what, and offers
  "Restart now" for app changes). Off with the "Automatic updates" switch in the cogwheel menu.
Full downloads (a new base, ~600 MB) are never installed automatically.
"""
import threading
import time
import traceback

import apppack
import settings
import ytpack

FIRST = 20                 # seconds after start
EVERY = 6 * 3600           # seconds between checks while the app runs
AFTER_FAIL = 30 * 60       # a failed YouTube download checks again if the last check is older than this
LOCK = threading.Lock()    # one installation at a time (this and the cogwheel menu's Install button)

last = {"when": 0.0, "app": None, "youtube": None, "error": ""}   # what the last run did
_timer = None


def enabled():
    return bool(settings.get("auto_update", True))


def set_enabled(on):
    settings.put("auto_update", bool(on))


def run(notify=lambda: None):
    """Check once and install what's new. Returns {'app': version|None, 'youtube': version|None}."""
    got = {"app": None, "youtube": None}
    if not enabled() or not LOCK.acquire(blocking=False):
        return got
    try:
        last["when"] = time.time()
        m = apppack.check()
        if m["newer"]:
            done = apppack.install(m)
            got = {"app": m["version"] if done["app"] else None,
                   "youtube": m.get("youtube") if done["youtube"] else None}
        elif not m["fits"]:                      # an older base: the YouTube-only fix
            p = ytpack.check()
            if p["newer"]:
                ytpack.install(p)
                got["youtube"] = p["version"]
        last["error"] = ""
    except Exception as e:                       # offline, nothing published, or an update that didn't fit
        traceback.print_exc()
        last["error"] = str(e).split("\n")[0][:200]
    finally:
        LOCK.release()
    if got["app"]:
        last["app"] = got["app"]
    if got["youtube"]:
        last["youtube"] = got["youtube"]
    if any(got.values()):
        notify()
    return got


def start(root, notify):
    """Schedule the checks (Tk `root.after` for the timing, the work in a thread)."""
    def tick():
        global _timer
        threading.Thread(target=run, args=(notify,), daemon=True).start()
        _timer = root.after(EVERY * 1000, tick)

    global _timer
    _timer = root.after(FIRST * 1000, tick)


def youtube_failed(notify):
    """A YouTube download failed: YouTube may have changed. Check now unless we just did."""
    if enabled() and time.time() - last["when"] > AFTER_FAIL:
        threading.Thread(target=run, args=(notify,), daemon=True).start()
