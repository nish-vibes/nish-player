"""Copy the design canvas's colours (design/colors.css) into theme.py.

    python tools/sync_colors.py          rewrite the generated block in theme.py
    python tools/sync_colors.py --check  only check; exit 1 if theme.py is out of date

Workflow: edit the swatches on the canvas's Colour system board, save its colors.css over
design/colors.css, run this script, run the tests. Colours the canvas doesn't define (hover and
pressed states, switch and fader parts) stay hand-written in theme.py, below the generated block.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSS = ROOT / "design" / "colors.css"
THEME = ROOT / "theme.py"
BEGIN = "# >>> generated from design/colors.css by tools/sync_colors.py - do not edit by hand\n"
END = "# <<< end of generated colours\n"

# theme.py name -> canvas token (--name in colors.css)
TOKENS = {
    # surfaces
    "BG": "bg", "HEADER": "header", "PANEL": "panel", "CARD": "panel", "LANE_BG": "lane", "WAVE": "wave",
    "DECK": "deck", "POPOVER": "popover", "FIELD": "field", "BTN": "button", "SEPARATOR": "separator",
    "SELECTED": "selected", "CHIP": "chip",
    # lines and controls
    "BORDER": "border", "BORDER2": "border-strong", "BORDER_POP": "border-popover", "CONTROL": "control",
    # text
    "TEXT": "text", "TEXT2": "text-2", "SOFT": "soft", "MUTED": "muted", "DIM": "dim",
    # accent
    "ACCENT": "accent", "ACCENT_TXT": "on-accent", "ACCENT_SOFT": "accent-text", "ACCENT_TINT": "accent-tint",
    "ACCENT_BAND": "accent-band", "ACCENT_TRACK": "accent-track",
    # Auto 440: warning orange, the switch, the lamp
    "WARN": "warn", "WARN_KNOB": "warn-knob", "WARN_TRACK": "warn-track", "LAMP": "lamp",
    # green (done / saved)
    "GREEN": "green", "GREEN_TXT": "green-text", "GREEN_BG": "green-bg", "GREEN_BORDER": "green-line",
    # red (clip / mute)
    "RED": "red", "RED_TXT": "red-text", "RED_BG": "red-bg", "RED_BORDER": "red-line", "CLIP_OFF": "red-off",
    # amber
    "AMBER": "amber", "AMBER_TXT": "amber-text", "AMBER_BG": "amber-bg-2", "AMBER_BORDER": "amber-line",
    "AMBER_BADGE": "amber-bg",
}


def read_css(path=CSS):
    """{token: (dark, light)} from colors.css."""
    css = path.read_text(encoding="utf-8")
    dark, light = css.split(".theme-light", 1)
    tok = lambda s: {k: v.strip().lower() for k, v in re.findall(r"--([\w-]+):\s*([^;]+);", s)}
    d, l = tok(dark), tok(light)
    return {k: (d[k], l.get(k, d[k])) for k in d}


def block(css):
    missing = sorted({t for t in TOKENS.values() if t not in css})
    if missing:
        raise SystemExit(f"design/colors.css has no {', '.join('--' + t for t in missing)}")
    lines = [BEGIN, "CANVAS_COLORS = {\n"]
    for name, t in TOKENS.items():
        lines.append(f'    "{name}": ("{css[t][0]}", "{css[t][1]}"),{" " * max(1, 14 - len(name))}# --{t}\n')
    lines.append("}\n")
    lines.append("CANVAS_TRACKS = [   # (strong, soft) per lane, as (dark, light): --track-N, --track-N-soft\n")
    n = 1
    while f"track-{n}" in css:
        s, so = css[f"track-{n}"], css[f"track-{n}-soft"]
        lines.append(f'    (("{s[0]}", "{s[1]}"), ("{so[0]}", "{so[1]}")),\n')
        n += 1
    lines += ["]\n", END]
    return "".join(lines)


def _render():
    theme = THEME.read_text(encoding="utf-8")
    a, b = theme.index(BEGIN), theme.index(END) + len(END)
    return theme, theme[:a] + block(read_css()) + theme[b:]


def main_check():
    """0 if theme.py matches design/colors.css, else 1 (used by tests/test_colors.py)."""
    theme, new = _render()
    return 0 if new == theme else 1


def main():
    theme, new = _render()
    if "--check" in sys.argv:
        if new != theme:
            print("theme.py is out of date with design/colors.css - run: python tools/sync_colors.py")
            return 1
        print("theme.py matches design/colors.css")
        return 0
    if new != theme:
        THEME.write_text(new, encoding="utf-8")
        print("theme.py updated from design/colors.css")
    else:
        print("theme.py already matches design/colors.css")
    return 0


if __name__ == "__main__":
    sys.exit(main())
