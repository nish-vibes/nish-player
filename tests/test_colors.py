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

    # Lux (JAMM Lux): only overrides names the palette has, valid hexes, dark appearance underneath
    hexok = lambda c: isinstance(c, str) and len(c) == 7 and c[0] == "#" and int(c[1:], 16) >= 0  # noqa: E731
    assert set(theme.LUX) <= set(theme.PALETTE), set(theme.LUX) - set(theme.PALETTE)
    assert set(theme.LUX_GROUPS) == set(theme.GROUPS)
    assert all(hexok(c) for c in theme.LUX.values())
    assert all(hexok(c) for cols in theme.LUX_GROUPS.values() for c in cols)
    assert len(theme.LUX_TRACKS) == len(theme.TRACK_PAIRS) and all(hexok(c) for p in theme.LUX_TRACKS for c in p)
    theme.set_mode("lux")
    assert theme.MODE == "lux" and theme.BG == "#0d0d0d" and theme.ACTION == "#fe8b48" and theme.ACCENT == "#ffd2b4"
    assert theme.TEXT2 == theme.PALETTE["TEXT2"][0] or theme.TEXT2 == theme.LUX["TEXT2"]
    assert theme.GREEN == theme.PALETTE["GREEN"][0]          # not overridden: the dark value
    theme.set_mode("nonsense")
    assert theme.MODE == "dark" and theme.ACTION == theme.PALETTE["ACCENT"][0]
    ok("Lux: JAMM Lux colours over the dark palette; Play and Export in orange, selected in peach")

    # every UPPER_CASE name a module takes from "from theme import *" exists in theme
    # (catches typos and colours removed from the canvas before the app runs into them)
    known = set(dir(theme)) | set(dir(__builtins__))
    for f in sorted(ROOT.glob("*.py")):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        if f.name != "theme.py" and not any(isinstance(n, ast.ImportFrom) and n.module == "theme" for n in tree.body):
            continue        # (theme.py itself is checked too: its colour names are made at import)
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
