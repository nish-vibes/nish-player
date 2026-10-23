"""Colours, fonts, icons and small widgets shared by the NiSH Player windows."""
import math
import sys

import customtkinter as ctk

# ---------- colours ----------
# Every colour has a job and a (dark, light) pair; the same names as the design canvas's colour
# system. set_mode() switches all of them (and the copies other modules made with "from theme import").
PALETTE = {
    # surfaces
    "BG": ("#111316", "#f3f4f6"), "HEADER": ("#16191d", "#ffffff"), "PANEL": ("#15181c", "#ffffff"),
    "LANE_BG": ("#171a1f", "#fafbfc"), "CARD": ("#15181c", "#ffffff"), "POPOVER": ("#1a1d22", "#ffffff"),
    "FIELD": ("#0f1114", "#ffffff"), "BTN": ("#1c2025", "#f1f3f6"), "BTN_HOVER": ("#252a31", "#e8ebf0"),
    "SEPARATOR": ("#262b31", "#e6e9ee"), "THUMB": ("#2a2f36", "#eceef2"),
    "SELECTED": ("#1a2030", "#edf1ff"), "SELECTED_WAVE": ("#171c26", "#f5f7ff"),
    "DROP_HOT": ("#182033", "#eef2ff"), "RANGE_IDLE": ("#22272f", "#e9ecf0"),
    # lines and controls
    "BORDER": ("#23272d", "#e1e4ea"), "BORDER2": ("#2c3138", "#d2d7df"), "BORDER_POP": ("#343a42", "#cdd3dc"),
    "CONTROL": ("#4a515b", "#a0a8b4"), "CONTROL2": ("#3a414a", "#c3c9d2"), "SWITCH_OFF": ("#3a3f47", "#c9cfd8"),
    "KNOB": ("#d6d9de", "#6b7380"), "KNOB_HOVER": ("#ffffff", "#2a2f37"), "SWITCH_KNOB": ("#e6e8eb", "#ffffff"),
    "GRIP": ("#5a616b", "#9aa2ad"),
    # text
    "TEXT": ("#eef0f3", "#14171c"), "TEXT2": ("#d6d9de", "#2a2f37"), "SOFT": ("#b9bec6", "#454d58"),
    "BTN_TXT": ("#a8aeb7", "#454d58"), "MUTED": ("#8a919b", "#5b6370"), "FILE_TXT": ("#7d848e", "#6b7380"),
    "DIM": ("#6b727c", "#6b7380"),
    # accent
    "ACCENT": ("#7c9cff", "#3d5fd9"), "ACCENT_HOVER": ("#94afff", "#2f4fc7"), "ACCENT_TXT": ("#0f1114", "#ffffff"),
    "ACCENT_SOFT": ("#9fb4ff", "#3350c2"), "ACCENT_TINT": ("#1d2333", "#eaeeff"),
    "ACCENT_TINT_HOVER": ("#232b40", "#dfe6ff"), "ACCENT_SEL": ("#33405e", "#d3ddff"),
    "ACCENT_SEL_HOVER": ("#3c4b6e", "#c4d1fb"), "ACCENT_LINE": ("#34508a", "#a9bbf5"),
    "ACCENT_BAND": ("#26365a", "#d7e0ff"), "CHIP_ACCENT": ("#222a40", "#e3e9ff"),
    "CHIP_ACCENT_TXT": ("#b8c7ff", "#2e49b0"), "CHIP": ("#2a2e34", "#eceef2"),
    "BAND_ON": ("#2a3a60", "#c9d6ff"), "BAND_OFF": ("#2a2f37", "#dfe2e8"),
    "PLAYHEAD": ("#ffffff", "#14171c"),
    # Auto 440 green
    "GREEN": ("#5fd0a4", "#1f9a6d"), "GREEN_TXT": ("#9fe3c6", "#126b4b"), "GREEN_BG": ("#14211c", "#e9f7f0"),
    "GREEN_BORDER": ("#2f6b55", "#93d5b8"), "GREEN_TRACK": ("#23362e", "#cbeadc"),
    # clip / mute red
    "RED": ("#ff4d4d", "#d92b2b"), "RED_TXT": ("#ff8a8a", "#b02222"), "RED_BG": ("#3a1c1c", "#fde6e6"),
    "RED_BORDER": ("#6b2a2a", "#eba3a3"), "CLIP_OFF": ("#4a2a2a", "#f1d4d4"),
    # beta / warning amber
    "AMBER": ("#e8c45a", "#8a5d00"), "AMBER_TXT": ("#f0d68a", "#6e4a00"), "AMBER_BG": ("#2a2414", "#fff6dc"),
    "AMBER_BORDER": ("#6b5520", "#e2c470"), "AMBER_BADGE": ("#3a3220", "#fbefcb"),
    # master fader
    "SLOT": ("#0f1114", "#e1e4ea"), "FADER_CAP": ("#e6e8eb", "#ffffff"), "FADER_CAP_EDGE": ("#9aa0a8", "#8a929e"),
    "FADER_CAP_MARK": ("#0f1114", "#14171c"),
}
GROUPS = {   # colours that come in sets
    "MUTE_ON": (("#4a2626", "#fde6e6"), ("#e07b7b", "#d96060"), ("#ffb3b3", "#a12a2a")),
    "SOLO_ON": (("#4a3f1c", "#fff0c4"), ("#e8c45a", "#c99a1a"), ("#ffe08a", "#6e4a00")),
}
TRACK_PAIRS = [   # (strong, soft) per lane, as (dark, light)
    (("#7c9cff", "#3d5fd9"), ("#33405e", "#c9d4fa")), (("#f2a65a", "#cf7a20"), ("#5a4430", "#f5d8b8")),
    (("#5fd0a4", "#1f9a6d"), ("#2c5246", "#bfe6d6")), (("#e07bb8", "#c24d8c"), ("#55344a", "#e79bc3")),
    (("#c4b46a", "#dec334"), ("#4d4831", "#e8e0a5")), (("#8fc3e0", "#2f88b8"), ("#344a57", "#c4e1f0")),
    (("#b48cf2", "#7a52d6"), ("#45385e", "#dccdf7")), (("#e08a7b", "#c65a47"), ("#553530", "#f5cfc8")),
]
MODE = "dark"
STAR_MODULES = ("__main__", "app", "youtube_ui", "settings_menu", "project_ui", "smoketest")


def _values(mode):
    i = 0 if mode == "dark" else 1
    v = {k: pair[i] for k, pair in PALETTE.items()}
    v.update({k: tuple(c[i] for c in cols) for k, cols in GROUPS.items()})
    v["TRACK_COLORS"] = [(s[i], d[i]) for s, d in TRACK_PAIRS]
    return v


def set_mode(mode):
    """Switch every colour to the dark or light palette (also in modules that copied the names)."""
    global MODE
    MODE = "light" if mode == "light" else "dark"
    vals = _values(MODE)
    g = globals()
    g.update(vals)
    for name in STAR_MODULES:
        mod = sys.modules.get(name)
        if mod is not None:
            for k, v in vals.items():
                if hasattr(mod, k):
                    setattr(mod, k, v)
    try:
        ctk.set_appearance_mode(MODE)
    except Exception:
        pass


globals().update(_values("dark"))
HEAD_W = 300   # width of the track header column
UI = "Segoe UI" if sys.platform == "win32" else "DejaVu Sans"
MONO = "Consolas" if sys.platform == "win32" else "DejaVu Sans Mono"


def font(size=13, weight="normal", mono=False):
    return ctk.CTkFont(family=MONO if mono else UI, size=size, weight=weight)


def fmt_time(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def cents_text(c, decimals=0):
    if decimals and abs(c) >= 0.05:
        return f"{c:+.{decimals}f} ct".replace("-", "−")
    r = int(math.floor(abs(c) + 0.5)) * (1 if c >= 0 else -1)
    return f"{r:+d} ct".replace("-", "−") if r else "0 ct"


def blend(c1, c2, t):
    """Mix two #rrggbb colours (t=0 -> c1, t=1 -> c2)."""
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


# Master fader law: the scale marks sit at equal steps, like the design.
FADER_POINTS = [(0.0, -60.0), (0.2, -24.0), (0.4, -12.0), (0.6, -6.0), (0.8, 0.0), (1.0, 6.0)]


def fader_db(pos):
    if pos <= 0.001:
        return -math.inf
    for (p0, d0), (p1, d1) in zip(FADER_POINTS, FADER_POINTS[1:]):
        if pos <= p1:
            return d0 + (d1 - d0) * (pos - p0) / (p1 - p0)
    return 6.0


def db_pos(db):
    if db <= -60:
        return 0.0
    for (p0, d0), (p1, d1) in zip(FADER_POINTS, FADER_POINTS[1:]):
        if db <= d1:
            return p0 + (p1 - p0) * (db - d0) / (d1 - d0)
    return 1.0


# ---------- icons (drawn, so they look the same on every PC) ----------
_ICONS = {}


def icon(name, color, size=16):
    key = (name, color, size, MODE)
    if key in _ICONS:
        return _ICONS[key]
    from PIL import Image, ImageDraw
    S = size * 4
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    w = max(4, S // 9)  # stroke width
    if name == "play":
        d.polygon([(S * .28, S * .16), (S * .28, S * .84), (S * .86, S * .5)], fill=color)
    elif name == "pause":
        d.rounded_rectangle([S * .24, S * .18, S * .42, S * .82], radius=S * .04, fill=color)
        d.rounded_rectangle([S * .58, S * .18, S * .76, S * .82], radius=S * .04, fill=color)
    elif name == "back":
        d.rectangle([S * .2, S * .2, S * .2 + w, S * .8], fill=color)
        d.polygon([(S * .8, S * .2), (S * .8, S * .8), (S * .32, S * .5)], fill=color)
    elif name == "loop":
        d.arc([S * .16, S * .2, S * .84, S * .8], 20, 320, fill=color, width=w)
        d.polygon([(S * .6, S * .06), (S * .86, S * .27), (S * .56, S * .38)], fill=color)
    elif name == "export":
        d.line([(S * .5, S * .12), (S * .5, S * .62)], fill=color, width=w)
        d.polygon([(S * .26, S * .44), (S * .74, S * .44), (S * .5, S * .72)], fill=color)
        d.line([(S * .16, S * .86), (S * .84, S * .86)], fill=color, width=w)
    elif name == "check":
        d.line([(S * .16, S * .52), (S * .4, S * .76), (S * .86, S * .26)], fill=color, width=w + 2,
               joint="curve")
    elif name == "pencil":
        d.line([(S * .24, S * .76), (S * .74, S * .26)], fill=color, width=w + 2)
        d.polygon([(S * .12, S * .88), (S * .18, S * .66), (S * .34, S * .82)], fill=color)
    elif name == "compact":       # two lines with arrows squeezing in (as in the design)
        u = S / 24
        for a, b in (((4, 9), (20, 9)), ((4, 15), (20, 15))):
            d.line([(a[0] * u, a[1] * u), (b[0] * u, b[1] * u)], fill=color, width=w)
        d.line([(9 * u, 4 * u), (12 * u, 7 * u), (15 * u, 4 * u)], fill=color, width=w, joint="curve")
        d.line([(9 * u, 20 * u), (12 * u, 17 * u), (15 * u, 20 * u)], fill=color, width=w, joint="curve")
    elif name == "close":
        d.line([(S * .24, S * .24), (S * .76, S * .76)], fill=color, width=w)
        d.line([(S * .76, S * .24), (S * .24, S * .76)], fill=color, width=w)
    elif name == "dot":
        d.ellipse([S * .2, S * .2, S * .8, S * .8], fill=color)
    elif name == "warn":
        d.polygon([(S * .5, S * .08), (S * .94, S * .88), (S * .06, S * .88)], outline=color, width=w)
        d.line([(S * .5, S * .36), (S * .5, S * .6)], fill=color, width=w)
        d.ellipse([S * .45, S * .68, S * .55, S * .78], fill=color)
    elif name.startswith("spin"):  # loading circle, 12 frames
        a = int(name[4:]) * 30
        d.arc([S * .12, S * .12, S * .88, S * .88], 0, 360,
              fill=(255, 255, 255, 40) if MODE == "dark" else (0, 0, 0, 34), width=w)
        d.arc([S * .12, S * .12, S * .88, S * .88], a, a + 100, fill=color, width=w)
    elif name == "grip":  # six dots
        r = S * .085
        for cx in (S * .36, S * .64):
            for cy in (S * .2, S * .5, S * .8):
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    elif name == "split":         # one line splitting into three (the Split… button)
        u = S / 24

        def curve(p0, p1, p2, p3, n=14):
            pts = []
            for i in range(n + 1):
                t = i / n
                x = (1 - t) ** 3 * p0[0] + 3 * (1 - t) ** 2 * t * p1[0] + 3 * (1 - t) * t * t * p2[0] + t ** 3 * p3[0]
                y = (1 - t) ** 3 * p0[1] + 3 * (1 - t) ** 2 * t * p1[1] + 3 * (1 - t) * t * t * p2[1] + t ** 3 * p3[1]
                pts.append((x * u, y * u))
            return pts
        d.line([(3 * u, 12 * u), (21 * u, 12 * u)], fill=color, width=w)
        d.line(curve((9, 12), (13, 12), (14, 5), (21, 5)), fill=color, width=w, joint="curve")
        d.line(curve((9, 12), (13, 12), (14, 19), (21, 19)), fill=color, width=w, joint="curve")
    elif name == "file":          # a document with a note on it
        u = S / 24
        d.line([(14 * u, 3 * u), (7 * u, 3 * u), (5 * u, 5 * u), (5 * u, 19 * u), (7 * u, 21 * u), (17 * u, 21 * u),
                (19 * u, 19 * u), (19 * u, 8 * u), (14 * u, 3 * u), (14 * u, 8 * u), (19 * u, 8 * u)],
               fill=color, width=w, joint="curve")
        d.line([(10 * u, 17.5 * u), (10 * u, 11.5 * u), (15 * u, 10.5 * u), (15 * u, 16.5 * u)], fill=color, width=w)
        d.ellipse([7.7 * u, 16.2 * u, 10.3 * u, 18.8 * u], fill=color)
        d.ellipse([12.7 * u, 15.2 * u, 15.3 * u, 17.8 * u], fill=color)
    elif name == "folder":
        u = S / 24
        d.line([(3 * u, 7 * u), (3 * u, 19 * u), (21 * u, 19 * u), (21 * u, 8.5 * u), (11.5 * u, 8.5 * u),
                (9.5 * u, 5.5 * u), (3 * u, 5.5 * u), (3 * u, 7 * u)], fill=color, width=w, joint="curve")
    elif name == "wave":          # waveform bars (like the logo)
        for x, h in ((4, 4), (8, 12), (12, 18), (16, 10), (20, 4)):
            d.line([(x * S / 24, (12 - h / 2) * S / 24), (x * S / 24, (12 + h / 2) * S / 24)], fill=color, width=w)
    elif name == "youtube":
        d.rounded_rectangle([S * .06, S * .2, S * .94, S * .8], radius=S * .18, outline=color, width=w)
        d.polygon([(S * .42, S * .36), (S * .42, S * .64), (S * .66, S * .5)], fill=color)
    elif name == "cog":
        cx = cy = S / 2
        for k in range(8):
            a = k * math.pi / 4
            d.line([(cx + math.cos(a) * S * .22, cy + math.sin(a) * S * .22),
                    (cx + math.cos(a) * S * .44, cy + math.sin(a) * S * .44)], fill=color, width=int(w * 1.6))
        d.ellipse([S * .2, S * .2, S * .8, S * .8], fill=color)
        d.ellipse([S * .38, S * .38, S * .62, S * .62], fill=(0, 0, 0, 0))
    elif name == "sun":
        cx = cy = S / 2
        d.ellipse([S * .32, S * .32, S * .68, S * .68], fill=color)
        for k in range(8):
            a = k * math.pi / 4
            d.line([(cx + math.cos(a) * S * .28, cy + math.sin(a) * S * .28),
                    (cx + math.cos(a) * S * .44, cy + math.sin(a) * S * .44)], fill=color, width=w)
    elif name == "moon":
        d.ellipse([S * .14, S * .14, S * .82, S * .82], fill=color)
        d.ellipse([S * .34, S * .04, S * .98, S * .66], fill=(0, 0, 0, 0))
    elif name == "chevron":  # small ▾
        d.line([(S * .22, S * .38), (S * .5, S * .66), (S * .78, S * .38)], fill=color, width=w + 2,
               joint="curve")
    elif name == "project":  # a page with a little waveform
        d.rounded_rectangle([S * .18, S * .08, S * .82, S * .92], radius=S * .1, outline=color, width=w)
        for x, h in ((.34, .12), (.44, .24), (.54, .16), (.64, .08)):
            d.line([(S * x, S * (.5 - h)), (S * x, S * (.5 + h))], fill=color, width=max(3, w - 2))
    elif name == "box_on":
        d.rounded_rectangle([S * .08, S * .08, S * .92, S * .92], radius=S * .2, fill=color)
        d.line([(S * .26, S * .52), (S * .43, S * .7), (S * .75, S * .32)], fill=ACCENT_TXT, width=w + 2,
               joint="curve")
    elif name == "box_off":
        d.rounded_rectangle([S * .08, S * .08, S * .92, S * .92], radius=S * .2, outline=color, width=w)
    img = img.resize((size * 2, size * 2), Image.LANCZOS)
    _ICONS[key] = ctk.CTkImage(light_image=img, dark_image=img, size=(size, size))
    return _ICONS[key]


class ToolButton(ctk.CTkButton):
    def __init__(self, master, text, command=None, width=None, height=36, primary=False, **kw):
        opts = dict(text=text, command=command, height=height, corner_radius=8, font=font(13),
                    fg_color=ACCENT if primary else BTN, hover_color=ACCENT_HOVER if primary else BTN_HOVER,
                    text_color=ACCENT_TXT if primary else TEXT2, border_width=0 if primary else 1,
                    border_color=BORDER2)
        if width:
            opts["width"] = width
        if primary:
            opts["font"] = font(13, "bold")
        opts.update(kw)
        super().__init__(master, **opts)


# ---------------------------------------------------------------------------


def no_image(label):
    """CTkLabel keeps its old picture when given image=None; this really removes it."""
    label.configure(image=None)
    try:
        label._label.configure(image="")
    except Exception:
        pass
