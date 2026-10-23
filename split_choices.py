"""The Split dialog's choice row, drawn on one canvas (the design needs shapes Tk widgets can't do):

    Original | Karaoke | [ 4 Stems (o) 6 Stems ] | cog
      Auto 440     Auto 440 tab        Auto 440 tab

- Round marks on every choice; the two stem choices sit in one box with a small link piece between
  them (filled while a stem choice is on), so it reads as "one or the other".
- Each choice has an Auto 440 tab hanging from its bottom edge, with a lamp after the text:
  not available = dimmed; off = dotted orange outline tucked under the choice's border;
  on = filled, joined to the choice, plus a dotted orange line just inside the choice's border.
- The Original's Auto 440 is its own small button under the tile (copy and/or Auto440 version).
- YouTube always keeps the original: that tile is striped and can't be unticked.
"""
import tkinter as tk

import theme
from theme import blend

TILE_H = 52
TAB_H = 20
HEIGHT = TILE_H + TAB_H + 6
GAP = 6
COG_W = 40


def _round_points(x0, y0, x1, y1, r):
    """Points for a smooth polygon: a rectangle with rounded corners (r = (tl, tr, br, bl))."""
    import math
    tl, tr, br, bl = r
    pts = []
    for (cx, cy, rad, start) in ((x0 + tl, y0 + tl, tl, 180), (x1 - tr, y0 + tr, tr, 270),
                                 (x1 - br, y1 - br, br, 0), (x0 + bl, y1 - bl, bl, 90)):
        if rad <= 0:
            pts += [cx, cy, cx, cy]          # a doubled point keeps the corner sharp when smoothed
            continue
        for k in range(7):
            a = math.radians(start + k * 15)
            pts += [cx + rad * math.cos(a), cy + rad * math.sin(a)]
    return pts


class ChoiceRow(tk.Canvas):
    def __init__(self, parent, on_toggle, on_tune, on_cog, bg):
        super().__init__(parent, height=HEIGHT, bg=bg, highlightthickness=0, bd=0)
        self.on_toggle, self.on_tune, self.on_cog = on_toggle, on_tune, on_cog
        self.bgc = bg
        self.state = None
        self.hits = []          # (x0, y0, x1, y1, action)
        self.hover = None       # the tab under the mouse (nudged down a little)
        self._imgs = []
        self.bind("<Configure>", lambda e: self.draw())
        self.bind("<Button-1>", self._click)
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda e: self._set_hover(None))

    # ----- public -----
    def set_state(self, is_file, out, tune):
        self.state = (bool(is_file), dict(out), dict(tune))
        self.draw()

    # ----- geometry -----
    def columns(self):
        w = max(200, self.winfo_width())
        u = (w - COG_W - 3 * GAP) / 4
        return {"original": (0, u), "karaoke": (u + GAP, 2 * u + GAP), "stems_group": (2 * u + 2 * GAP, 4 * u + 2 * GAP),
                "cog": (w - COG_W, w)}

    # ----- drawing -----
    def draw(self):
        self.delete("all")
        self.hits = []
        self._imgs = []
        if not self.state:
            return
        is_file, out, tune = self.state
        cols = self.columns()
        T = theme
        on_any_stem = out.get("stems") or out.get("stems6")

        def made(k):
            return (not is_file and k == "original") or bool(out.get(k))

        # tabs that are "off" are tucked under their choice: draw them first
        tabs = [("karaoke", cols["karaoke"], bool(out.get("karaoke")), bool(tune.get("karaoke"))),
                ("stems", cols["stems_group"], bool(on_any_stem), bool(tune.get("stems")))]
        for key, (x0, x1), mk, on in tabs:
            if not (mk and on):
                self._tab(key, x0, x1, mk, False)

        # Original
        x0, x1 = cols["original"]
        locked = not is_file
        self._tile("original", x0, x1, made("original"), locked, radius=(8, 8, 8, 8),
                   title="Original", note="always kept" if locked else "copy → project", border=True,
                   inset=False)
        # Karaoke
        x0, x1 = cols["karaoke"]
        self._tile("karaoke", x0, x1, made("karaoke"), False, radius=(8, 8, 8, 8), title="Karaoke",
                   note="MP3 320", border=True, inset=made("karaoke") and bool(tune.get("karaoke")))
        # Stems: one box, two halves, a link piece in the middle
        gx0, gx1 = cols["stems_group"]
        mid = (gx0 + gx1) / 2
        self._tile("stems", gx0, mid, made("stems"), False, radius=(8, 0, 0, 8), title="4 Stems",
                   note="High Quality", border=False, inset=False)
        self._tile("stems6", mid, gx1, made("stems6"), False, radius=(0, 8, 8, 0), title="6 Stems",
                   note="More control", border=False, inset=False)
        self.create_polygon(_round_points(gx0, 0.5, gx1 - 0.5, TILE_H - 0.5, (8, 8, 8, 8)), smooth=True,
                            fill="", outline=T.ACCENT if on_any_stem else T.BORDER2, width=1)
        if on_any_stem and tune.get("stems"):
            self._inset(gx0, gx1)
        self.create_polygon(_round_points(mid - 6, TILE_H / 2 - 7, mid + 6, TILE_H / 2 + 7, (6, 6, 6, 6)),
                            smooth=True, fill=T.ACCENT if on_any_stem else T.PANEL,
                            outline=T.ACCENT if on_any_stem else T.BORDER2)
        # cog
        cx0, cx1 = cols["cog"]
        self.create_polygon(_round_points(cx0, 0.5, cx1 - 0.5, TILE_H - 0.5, (6, 6, 6, 6)), smooth=True,
                            fill=T.BTN, outline=T.BORDER2)
        img = theme.photo("cog", T.SOFT, 18)
        self._imgs.append(img)
        self.create_image((cx0 + cx1) / 2, TILE_H / 2, image=img)
        self.hits.append((cx0, 0, cx1, TILE_H, ("cog",)))

        # tabs that are on sit on top, joined to their choice
        for key, (x0, x1), mk, on in tabs:
            if mk and on:
                self._tab(key, x0, x1, True, True)
        # the Original's own Auto 440 button
        x0, x1 = cols["original"]
        self._orig_button(x0, x1, bool(tune.get("original")))

    def _tile(self, key, x0, x1, on, locked, radius, title, note, border, inset):
        T = theme
        bg = T.ACCENT_TINT if on else T.PANEL
        pts = _round_points(x0 + 0.5, 0.5, x1 - 0.5, TILE_H - 0.5, radius)
        if locked and on:     # YouTube's original: always kept, shown striped
            img = theme.striped(int(x1 - x0), TILE_H, T.ACCENT_TINT, T.ACCENT_BAND, radius[0])
            self._imgs.append(img)
            self.create_image(x0, 0, image=img, anchor="nw")
            self.create_polygon(pts, smooth=True, fill="", outline=T.CONTROL, dash=(4, 3))
        else:
            self.create_polygon(pts, smooth=True, fill=bg,
                                outline=(T.ACCENT if on else T.BORDER2) if border else "")
        if inset:
            self._inset(x0, x1)
        # round mark + title + note
        mx, my = x0 + 17, 17
        ring = T.ACCENT if on else T.CONTROL
        self.create_oval(mx - 6, my - 6, mx + 6, my + 6, outline=ring, width=2)
        if on:
            self.create_oval(mx - 3, my - 3, mx + 3, my + 3, fill=T.ACCENT, outline="")
        self.create_text(mx + 12, my, text=title, anchor="w", fill=T.TEXT if on else T.SOFT,
                         font=(T.UI, 10, "bold"))
        nf = (T.UI, 9)
        self.create_text(x0 + 11, 36, text=self._fit(note, nf, x1 - x0 - 16), anchor="w",
                         fill=T.ACCENT_SOFT if on and not locked else T.DIM, font=nf)
        if not locked:
            self.hits.append((x0, 0, x1, TILE_H, ("toggle", key)))

    def _inset(self, x0, x1):
        self.create_polygon(_round_points(x0 + 4, 4, x1 - 4, TILE_H - 4, (5, 5, 5, 5)), smooth=True, fill="",
                            outline=theme.WARN, dash=(1, 2))

    def _lamp(self, x, y, on):
        T = theme
        if on:
            glow = blend(T.LAMP, self.bgc, 0.65)
            self.create_oval(x - 6, y - 6, x + 6, y + 6, fill=glow, outline="")
        self.create_oval(x - 3, y - 3, x + 3, y + 3, fill=T.LAMP if on else T.CONTROL, outline="")

    def _tab(self, key, x0, x1, made, on):
        T = theme
        f = (T.UI, 8, "bold")
        tw = self._text_w("Auto 440", f)
        w = 9 + tw + 5 + 6 + 7
        cx = (x0 + x1) / 2
        nudge = 2 if (self.hover == key and made) else 0
        tx0, tx1 = cx - w / 2, cx + w / 2
        ty0, ty1 = TILE_H - 1 + nudge, TILE_H - 1 + TAB_H + nudge
        if not made:
            border, bg, fg, dash = T.BORDER2, T.POPOVER, T.MUTED, None
            fade = 0.6
            border, bg, fg = (blend(c, self.bgc, fade) for c in (border, bg, fg))
        elif on:
            border, bg, fg, dash = T.WARN, T.AMBER_BADGE, T.WARN, None
        else:
            border, bg, fg, dash = T.WARN, T.POPOVER, T.MUTED, (1, 2)
        pts = _round_points(tx0, ty0, tx1, ty1, (0, 0, 8, 8))
        kw = {"dash": dash} if dash else {}
        self.create_polygon(pts, smooth=True, fill=bg, outline=border, **kw)
        if on:   # joined to the choice: cover the choice's border where the tab meets it
            self.create_line(tx0 + 1, ty0, tx1 - 1, ty0, fill=bg, width=2)
        self.create_text(tx0 + 9, (ty0 + ty1) / 2 + 1, text="Auto 440", anchor="w", fill=fg, font=f)
        if made:
            self._lamp(tx0 + 9 + tw + 5 + 3, (ty0 + ty1) / 2 + 1, on)
        else:
            self.create_oval(tx0 + 9 + tw + 5, (ty0 + ty1) / 2 - 2, tx0 + 9 + tw + 11, (ty0 + ty1) / 2 + 4,
                             fill=blend(T.CONTROL, self.bgc, 0.6), outline="")
        if made:
            self.hits.append((tx0, ty0, tx1, ty1 + 2, ("tune", key)))

    def _orig_button(self, x0, x1, on):
        T = theme
        f = (T.UI, 8, "bold")
        tw = self._text_w("Auto 440", f)
        w = 4 + 11 + 5 + tw + 5 + 6 + 8
        cx = (x0 + x1) / 2
        nudge = 2 if self.hover == "original" else 0
        bx0, bx1 = cx - w / 2, cx + w / 2
        by0, by1 = TILE_H + 4 + nudge, TILE_H + 22 + nudge
        border = T.WARN if on else T.AMBER_BORDER
        self.create_polygon(_round_points(bx0, by0, bx1, by1, (9, 9, 9, 9)), smooth=True,
                            fill=T.AMBER_BADGE if on else T.PANEL, outline=border,
                            **({} if on else {"dash": (1, 2)}))
        my = (by0 + by1) / 2
        mx = bx0 + 4 + 5.5
        self.create_oval(mx - 5, my - 5, mx + 5, my + 5, outline=border, width=1.5)
        if on:
            self.create_oval(mx - 2.5, my - 2.5, mx + 2.5, my + 2.5, fill=T.WARN, outline="")
        self.create_text(mx + 5.5 + 5, my + 1, text="Auto 440", anchor="w", fill=T.WARN if on else T.SOFT, font=f)
        self._lamp(mx + 5.5 + 5 + tw + 5 + 3, my + 1, on)
        self.hits.append((bx0, by0, bx1, by1 + 2, ("tune", "original")))

    def _fit(self, text, f, width):
        """The text, shortened with an ellipsis if it doesn't fit."""
        if self._text_w(text, f) <= width:
            return text
        while len(text) > 1 and self._text_w(text + "…", f) > width:
            text = text[:-1]
        return text.rstrip() + "…"

    def _text_w(self, text, f):
        tid = self.create_text(-1000, -1000, text=text, font=f, anchor="w")
        b = self.bbox(tid)
        self.delete(tid)
        return (b[2] - b[0]) if b else 6 * len(text)

    # ----- input -----
    def _hit(self, x, y):
        # tabs and the small button first: they overlap the tiles' edges
        for x0, y0, x1, y1, act in sorted(self.hits, key=lambda h: h[4][0] != "tune"):
            if x0 <= x <= x1 and y0 <= y <= y1:
                return act
        return None

    def _click(self, e):
        act = self._hit(e.x, e.y)
        if not act:
            return
        if act[0] == "toggle":
            self.on_toggle(act[1])
        elif act[0] == "tune":
            self.on_tune(act[1])
        elif act[0] == "cog":
            self.on_cog()

    def _motion(self, e):
        act = self._hit(e.x, e.y)
        self.configure(cursor="hand2" if act else "")
        self._set_hover(act[1] if act and act[0] == "tune" else None)

    def _set_hover(self, key):
        if key != self.hover:
            self.hover = key
            self.draw()
