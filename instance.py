"""One NiSH Player at a time, and .nish files that open with a double-click.

* The running app listens on a local socket (127.0.0.1 only). Starting NiSH Player again – for
  example by double-clicking a project – hands the files to the running app and quits, so two
  players never play at once.
* On Windows, the app registers .nish files for the current user (no admin rights): they open with
  this NiSHPlayer.exe and get its icon. It re-registers on every start, so a moved app folder (or a
  copy on a USB stick) always points to the right place.
"""
import json
import os
import socket
import sys
import threading
from pathlib import Path

import engine

PORT_FILE = engine.DATA_DIR / "instance.port"
MAGIC = b"NISH1\n"


def hand_off(paths, timeout=2.0):
    """Give paths to an already running NiSH Player. True if it took them."""
    try:
        port = int(PORT_FILE.read_text().strip())
    except Exception:
        return False
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as s:
            s.sendall(MAGIC + json.dumps([str(Path(p).resolve()) for p in paths]).encode("utf-8"))
            s.shutdown(socket.SHUT_WR)
            return s.recv(16) == b"OK"
    except OSError:
        return False


def serve(on_paths):
    """Listen for other starts of the app. on_paths(list) is called from a worker thread."""
    try:
        srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        srv.bind(("127.0.0.1", 0))
        srv.listen(4)
        PORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        PORT_FILE.write_text(str(srv.getsockname()[1]))
    except OSError:
        return None

    def loop():
        while True:
            try:
                conn, _ = srv.accept()
            except OSError:
                return
            with conn:
                try:
                    conn.settimeout(3)
                    data = b""
                    while len(data) < 1 << 16:
                        chunk = conn.recv(4096)
                        if not chunk:
                            break
                        data += chunk
                    if not data.startswith(MAGIC):
                        continue
                    paths = [p for p in json.loads(data[len(MAGIC):].decode("utf-8")) if isinstance(p, str)]
                    on_paths(paths)
                    conn.sendall(b"OK")
                except Exception:
                    pass

    threading.Thread(target=loop, daemon=True).start()
    return srv


def stop(srv):
    try:
        if srv is not None:
            if PORT_FILE.exists() and PORT_FILE.read_text().strip() == str(srv.getsockname()[1]):
                PORT_FILE.unlink()
            srv.close()
    except Exception:
        pass


PROG_ID = "NiSHPlayer.Project"


def register_file_type():
    """Make .nish files open with this NiSHPlayer.exe (current user only, no admin)."""
    if sys.platform != "win32" or not getattr(sys, "frozen", False):
        return False
    import winreg
    exe = str(Path(sys.executable).resolve())
    want = {
        r"Software\Classes\.nish": {"": PROG_ID},
        rf"Software\Classes\{PROG_ID}": {"": "NiSH Player project"},
        rf"Software\Classes\{PROG_ID}\DefaultIcon": {"": f'"{exe}",0'},
        rf"Software\Classes\{PROG_ID}\shell\open\command": {"": f'"{exe}" "%1"'},
    }
    changed = False
    for key, values in want.items():
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ | winreg.KEY_WRITE) as k:
            for name, val in values.items():
                try:
                    cur = winreg.QueryValueEx(k, name)[0]
                except OSError:
                    cur = None
                if cur != val:
                    winreg.SetValueEx(k, name, 0, winreg.REG_SZ, val)
                    changed = True
    if changed:
        try:
            import ctypes
            ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)   # SHCNE_ASSOCCHANGED
        except Exception:
            pass
    return changed
