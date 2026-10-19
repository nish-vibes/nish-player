"""Small user settings kept in %LOCALAPPDATA%\\NiSH Player\\settings.json.

They live outside the app folder, so updating the app never touches them.
"""
import datetime
import json
import os
from pathlib import Path

import engine

FILE = engine.DATA_DIR / "settings.json"
YT_FAIL_LIMIT = 5   # failed YouTube extractions on one day before suggesting an update


def _load():
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data):
    try:
        FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, FILE)
    except Exception:
        pass


def get(key, default=None):
    return _load().get(key, default)


def put(key, value):
    data = _load()
    data[key] = value
    _save(data)


def desktop():
    """The user's real Desktop folder (also when Windows has moved it into OneDrive)."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD),
                            ("d", ctypes.c_ubyte * 8)]
            # FOLDERID_Desktop {B4BFCC3A-DB2C-424C-B029-7FE99A87C641}
            fid = GUID(0xB4BFCC3A, 0xDB2C, 0x424C, (ctypes.c_ubyte * 8)(0xB0, 0x29, 0x7F, 0xE9, 0x9A, 0x87, 0xC6, 0x41))
            out = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(fid), 0, None, ctypes.byref(out)) == 0:
                path = out.value
                ctypes.windll.ole32.CoTaskMemFree(out)
                if path and Path(path).is_dir():
                    return path
        except Exception:
            pass
    d = Path.home() / "Desktop"
    return str(d if d.is_dir() else Path.home())


def export_folder():
    """Where exports go: the folder chosen last time, or the Desktop."""
    f = get("export_folder")
    if f and Path(f).is_dir():
        return f
    return desktop()


def set_export_folder(path):
    put("export_folder", str(path))


def note_yt_failure(today=None):
    """Count a failed YouTube extraction. Returns today's count."""
    today = today or datetime.date.today().isoformat()
    data = _load()
    rec = data.get("yt_failures") or {}
    n = rec.get("count", 0) + 1 if rec.get("date") == today else 1
    data["yt_failures"] = {"date": today, "count": n}
    _save(data)
    return n


def yt_failures_today(today=None):
    today = today or datetime.date.today().isoformat()
    rec = get("yt_failures") or {}
    return rec.get("count", 0) if rec.get("date") == today else 0


def suggest_update(today=None):
    return yt_failures_today(today) >= YT_FAIL_LIMIT
