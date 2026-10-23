"""Colour tests: theme.py matches the design canvas (design/colors.css), and every colour is valid.

Run:  python tests/test_colors.py
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import sync_colors  # noqa: E402
import theme  # noqa: E402

HEX = re.compile(r"#[0-9a-f]{6}")


def ok(msg):
    print("ok:", msg)


def main():
    assert sync_colors.main_check() == 0, "theme.py is out of date with design/colors.css - run tools/sync_colors.py"
    ok("theme.py matches design/colors.css")

    both = set(theme.CANVAS_COLORS) & set(theme.APP_COLORS)
    assert not both, f"defined both from the canvas and by hand: {both}"
    for name, pair in theme.PALETTE.items():
        assert len(pair) == 2 and all(HEX.fullmatch(c) for c in pair), (name, pair)
    for name, sets in theme.GROUPS.items():
        assert all(len(p) == 2 and all(HEX.fullmatch(c) for c in p) for p in sets), (name, sets)
    for strong, soft in theme.TRACK_PAIRS:
        assert all(HEX.fullmatch(c) for c in strong + soft), (strong, soft)
    ok(f"{len(theme.CANVAS_COLORS)} canvas colours + {len(theme.APP_COLORS)} app-only colours, "
       f"{len(theme.TRACK_PAIRS)} track colours: all valid (dark, light) pairs")

    for mode in ("light", "dark"):
        theme.set_mode(mode)
        i = 0 if mode == "dark" else 1
        assert theme.BG == theme.PALETTE["BG"][i] and theme.TRACK_COLORS[0][0] == theme.TRACK_PAIRS[0][0][i]
    ok("set_mode switches every colour")

    # every UPPER_CASE name a module takes from "from theme import *" exists in theme
    # (catches typos and colours removed from the canvas before the app runs into them)
    known = set(dir(theme)) | set(dir(__builtins__))
    for f in sorted(ROOT.glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        if not any(isinstance(n, ast.ImportFrom) and n.module == "theme" for n in tree.body):
            continue
        own = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                own.add(n.id)
            elif isinstance(n, (ast.Import, ast.ImportFrom)):
                own.update((a.asname or a.name).split(".")[0] for a in n.names)
            elif isinstance(n, (ast.FunctionDef, ast.ClassDef)):
                own.add(n.name)
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
                and n.id.isupper() and len(n.id) > 1}
        missing = used - own - known
        assert not missing, f"{f.name} uses names theme.py doesn't have: {sorted(missing)}"
    ok("every colour name used in the app exists")
    print("COLOUR TESTS PASSED")


if __name__ == "__main__":
    main()
