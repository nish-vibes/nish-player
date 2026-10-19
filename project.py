"""NiSH Player projects (.nish): which files are loaded and how everything is set.

A project is a small JSON file. It points to the audio files instead of copying them; paths are
stored relative to the project file, so a song folder with its project can be moved or copied
(e.g. to a USB stick) and still opens. Absolute paths are kept as a fallback.
"""
import json
import os
from pathlib import Path

import settings

EXT = ".nish"
FORMAT = 1
RECENT_MAX = 15


def _rel(path, base):
    try:
        return os.path.relpath(Path(path).resolve(), Path(base).resolve()).replace("\\", "/")
    except ValueError:          # another drive on Windows
        return None


def save(path, state):
    """Write state (see App.project_state) to path. Returns the path written."""
    path = Path(path)
    if path.suffix.lower() != EXT:
        path = path.with_suffix(EXT)
    base = path.parent
    data = dict(state)
    data["tracks"] = []
    for t in state.get("tracks", []):
        t = dict(t)
        t["abs"] = str(Path(t["file"]).resolve())
        t["file"] = _rel(t["file"], base) or t["abs"]
        data["tracks"].append(t)
    data = {"app": "NiSH Player", "format": FORMAT, **data}
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    add_recent(path)
    return path


def load(path):
    """(state, missing): state with absolute track paths; missing = names of files not found."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("app") != "NiSH Player":
        raise ValueError("This isn't a NiSH Player project.")
    tracks, missing = [], []
    for t in data.get("tracks", []):
        cands = [path.parent / t.get("file", "")]
        if t.get("abs"):
            cands.append(Path(t["abs"]))
        found = next((c for c in cands if c.is_file()), None)
        if found is None:
            missing.append(t.get("name") or Path(t.get("file", "?")).name)
            continue
        t = dict(t)
        t["file"] = str(found.resolve())
        tracks.append(t)
    data["tracks"] = tracks
    add_recent(path)
    return data, missing


def new_state(tracks):
    """A project with neutral settings for [(path, name)] (used for YouTube imports)."""
    return {"tracks": [{"file": str(p), "name": n, "volume": 1.0, "mute": False, "solo": False}
                       for p, n in tracks],
            "speed": 1.0, "pitch": 0, "fine": 0, "auto440": False, "auto440_result": None,
            "loop": {"on": False, "start": None, "end": None, "fade": 1.0}, "master": None}


def add_recent(path):
    p = str(Path(path).resolve())
    lst = [x for x in settings.get("recent_projects", []) if x != p]
    settings.put("recent_projects", [p] + lst[:RECENT_MAX * 2])


def recent():
    """Most recently saved/opened projects that still exist (newest first)."""
    lst = [x for x in settings.get("recent_projects", []) if Path(x).is_file()]
    return lst[:RECENT_MAX]


def signature(state):
    """Compare two states to see whether anything changed."""
    return json.dumps(state, sort_keys=True, default=str)
