"""Colours, fonts, icons and small widgets shared by the NiSH Player windows."""
import math
import sys

import customtkinter as ctk

# ---------- colours (from the design) ----------
BG, HEADER, PANEL, LANE_BG, CARD = "#111316", "#16191d", "#15181c", "#171a1f", "#15181c"
BORDER, BORDER2, BTN, BTN_HOVER = "#23272d", "#2c3138", "#1c2025", "#252a31"
TEXT, TEXT2, SOFT, MUTED, DIM = "#eef0f3", "#d6d9de", "#b9bec6", "#8a919b", "#6b727c"
ACCENT, ACCENT_HOVER, ACCENT_TXT, ACCENT_SOFT = "#7c9cff", "#94afff", "#0f1114", "#9fb4ff"
GREEN, GREEN_TXT, GREEN_BG, GREEN_BORDER = "#5fd0a4", "#9fe3c6", "#14211c", "#2f6b55"
RED, RED_TXT, RED_BG, RED_BORDER = "#ff4d4d", "#ff8a8a", "#3a1c1c", "#6b2a2a"
AMBER, AMBER_TXT, AMBER_BG, AMBER_BORDER = "#e8c45a", "#f0d68a", "#2a2414", "#6b5520"
MUTE_ON = ("#4a2626", "#e07b7b", "#ffb3b3")
SOLO_ON = ("#4a3f1c", "#e8c45a", "#ffe08a")
TRACK_COLORS = [("#7c9cff", "#33405e"), ("#f2a65a", "#5a4430"), ("#5fd0a4", "#2c5246"),
                ("#e07bb8", "#55344a"), ("#c4b46a", "#4d4831"), ("#8fc3e0", "#344a57"),
                ("#b48cf2", "#45385e"), ("#e08a7b", "#553530")]
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
    key = (name, color, size)
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
        d.arc([S * .12, S * .12, S * .88, S * .88], 0, 360, fill=(255, 255, 255, 40), width=w)
        d.arc([S * .12, S * .12, S * .88, S * .88], a, a + 100, fill=color, width=w)
    elif name == "grip":  # six dots
        r = S * .085
        for cx in (S * .36, S * .64):
            for cy in (S * .2, S * .5, S * .8):
                d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
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
    elif name == "chevron":  # small ▾
        d.line([(S * .22, S * .38), (S * .5, S * .66), (S * .78, S * .38)], fill=color, width=w + 2,
               joint="curve")
    elif name == "project":  # a page with a little waveform
        d.rounded_rectangle([S * .18, S * .08, S * .82, S * .92], radius=S * .1, outline=color, width=w)
        for x, h in ((.34, .12), (.44, .24), (.54, .16), (.64, .08)):
            d.line([(S * x, S * (.5 - h)), (S * x, S * (.5 + h))], fill=color, width=max(3, w - 2))
    elif name == "box_on":
        d.rounded_rectangle([S * .08, S * .08, S * .92, S * .92], radius=S * .2, fill=color)
        d.line([(S * .26, S * .52), (S * .43, S * .7), (S * .75, S * .32)], fill="#0f1114", width=w + 2,
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
