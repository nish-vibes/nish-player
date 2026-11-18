"""The Split dialog's choice row, drawn on one canvas (the design needs shapes Tk widgets can't do):

    Original | [x] Karaoke | [x] Stems  (4 | 6) | cog
      Auto 440    Auto 440 tab      Auto 440 tab

- Karaoke and Stems are independent, so they have square check boxes (round marks would mean
  "one of these"). How many stems is a small 4 | 6 switch inside the Stems tile.
- YouTube always keeps the original: that tile is plain text ("always kept"), not a control.
  For a file on this computer it is a check box ("copy → project").
- Each choice has an Auto 440 tab hanging from its bottom edge, with its own check box:
  not available = dimmed; off = outlined; on = accent tint, joined to the choice.
  The Original's Auto 440 is its own small button under the tile (a tuned copy).
- Accent only: amber is kept for warnings.
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
        return {"original": (0, u), "karaoke": (u + GAP, 2 * u + GAP),
                "stems_group": (2 * u + 2 * GAP, 4 * u + 2 * GAP), "cog": (w - COG_W, w)}

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
        on_any_stem = bool(out.get("stems") or out.get("stems6"))

        # tabs that are "off" are tucked under their choice: draw them first
        tabs = [("karaoke", cols["karaoke"], bool(out.get("karaoke")), bool(tune.get("karaoke"))),
                ("stems", cols["stems_group"], on_any_stem, bool(tune.get("stems")))]
        for key, (x0, x1), mk, on in tabs:
            if not (mk and on):
                self._tab(key, x0, x1, mk, False)

        # Original
        x0, x1 = cols["original"]
        if is_file:
            self._tile("original", x0, x1, bool(out.get("original")), "Original", "copy → project")
        else:
            self._plain(x0, x1, "Original", "always kept")
        # Karaoke
        x0, x1 = cols["karaoke"]
        self._tile("karaoke", x0, x1, bool(out.get("karaoke")), "Karaoke", "MP3 320")
        # Stems: check box + 4 | 6
        gx0, gx1 = cols["stems_group"]
        six = bool(out.get("stems6"))
        note = ("6 · adds guitar and piano" if six else "4 · vocals, drums, bass, other") if on_any_stem \
            else "vocals, drums, bass…"
        self._tile("stems_box", gx0, gx1, on_any_stem, "Stems", note)
        self._count_switch(gx1, on_any_stem, six)
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

    def _box(self, x, y, on, size=12, faded=False):
        """A square check box with its top-left corner at x, y."""
        T = theme
        ring = T.ACCENT if on else T.CONTROL
        if faded:
            ring = blend(ring, self.bgc, 0.6)
        pts = _round_points(x, y, x + size, y + size, (3, 3, 3, 3))
        self.create_polygon(pts, smooth=True, fill=T.ACCENT if on else "", outline=ring, width=1.5)
        if on:
            k = size / 12
            self.create_line(x + 3 * k, y + 6.2 * k, x + 5.2 * k, y + 8.4 * k, x + 9.2 * k, y + 3.8 * k,
                             fill=T.ACCENT_TXT, width=2, capstyle="round", joinstyle="round")

    def _tile(self, key, x0, x1, on, title, note):
        T = theme
        pts = _round_points(x0 + 0.5, 0.5, x1 - 0.5, TILE_H - 0.5, (8, 8, 8, 8))
        self.create_polygon(pts, smooth=True, fill=T.ACCENT_TINT if on else T.PANEL,
                            outline=T.ACCENT if on else T.BORDER2)
        self._box(x0 + 11, 11, on)
        self.create_text(x0 + 30, 17, text=title, anchor="w", fill=T.TEXT if on else T.SOFT,
                         font=(T.UI, 10, "bold"))
        nf = (T.UI, 9)
        right = x1 - 70 if key == "stems_box" else x1
        self.create_text(x0 + 11, 36, text=self._fit(note, nf, x1 - x0 - 16), anchor="w",
                         fill=T.ACCENT_SOFT if on else T.DIM, font=nf)
        self.hits.append((x0, 0, right, TILE_H, ("toggle", key)))

    def _plain(self, x0, x1, title, note):
        """Not a choice: YouTube always keeps the original."""
        T = theme
        pts = _round_points(x0 + 0.5, 0.5, x1 - 0.5, TILE_H - 0.5, (8, 8, 8, 8))
        self.create_polygon(pts, smooth=True, fill=self.bgc, outline=T.BORDER)
        self.create_text(x0 + 11, 17, text=title, anchor="w", fill=T.SOFT, font=(T.UI, 10, "bold"))
        self.create_text(x0 + 11, 36, text=note, anchor="w", fill=T.DIM, font=(T.UI, 9))

    def _count_switch(self, gx1, on, six):
        """4 | 6 inside the Stems tile, at the right of its title. Clicking a number also ticks Stems."""
        T = theme
        w, h = 26, 20
        x1 = gx1 - 10
        x0 = x1 - 2 * w
        y0 = 7
        self.create_polygon(_round_points(x0, y0, x1, y0 + h, (6, 6, 6, 6)), smooth=True,
                            fill=T.FIELD, outline=T.BORDER2)
        for i, (key, label) in enumerate((("stems", "4"), ("stems6", "6"))):
            sx0 = x0 + i * w
            picked = on and (six == (key == "stems6"))
            if picked:
                self.create_polygon(_round_points(sx0 + 2, y0 + 2, sx0 + w - 2, y0 + h - 2, (4, 4, 4, 4)),
                                    smooth=True, fill=T.ACCENT, outline="")
            fg = T.ACCENT_TXT if picked else (T.SOFT if on else T.DIM)
            self.create_text(sx0 + w / 2, y0 + h / 2, text=label, fill=fg, font=(T.UI, 9, "bold"))
            self.hits.append((sx0, 0, sx0 + w, TILE_H, ("toggle", key)))

    def _tab(self, key, x0, x1, made, on):
        T = theme
        f = (T.UI, 8, "bold")
        tw = self._text_w("Auto 440", f)
        w = 8 + 10 + 5 + tw + 9
        cx = (x0 + x1) / 2
        nudge = 2 if (self.hover == key and made) else 0
        tx0, tx1 = cx - w / 2, cx + w / 2
        ty0, ty1 = TILE_H - 1 + nudge, TILE_H - 1 + TAB_H + nudge
        if not made:
            border, bg, fg = (blend(c, self.bgc, 0.6) for c in (T.BORDER2, T.POPOVER, T.MUTED))
        elif on:
            border, bg, fg = T.ACCENT, T.ACCENT_TINT, T.ACCENT_SOFT
        else:
            border, bg, fg = T.BORDER2, T.POPOVER, T.MUTED
        pts = _round_points(tx0, ty0, tx1, ty1, (0, 0, 8, 8))
        self.create_polygon(pts, smooth=True, fill=bg, outline=border)
        if on:   # joined to the choice: cover the choice's border where the tab meets it
            self.create_line(tx0 + 1, ty0, tx1 - 1, ty0, fill=bg, width=2)
        my = (ty0 + ty1) / 2 + 1
        self._box(tx0 + 8, my - 5, on and made, size=10, faded=not made)
        self.create_text(tx0 + 8 + 10 + 5, my, text="Auto 440", anchor="w", fill=fg, font=f)
        if made:
            self.hits.append((tx0, ty0, tx1, ty1 + 2, ("tune", key)))

    def _orig_button(self, x0, x1, on):
        T = theme
        f = (T.UI, 8, "bold")
        tw = self._text_w("Auto 440", f)
        w = 8 + 10 + 5 + tw + 10
        cx = (x0 + x1) / 2
        nudge = 2 if self.hover == "original" else 0
        bx0, bx1 = cx - w / 2, cx + w / 2
        by0, by1 = TILE_H + 4 + nudge, TILE_H + 22 + nudge
        self.create_polygon(_round_points(bx0, by0, bx1, by1, (9, 9, 9, 9)), smooth=True,
                            fill=T.ACCENT_TINT if on else T.PANEL, outline=T.ACCENT if on else T.BORDER2)
        my = (by0 + by1) / 2
        self._box(bx0 + 8, my - 5, on, size=10)
        self.create_text(bx0 + 8 + 10 + 5, my + 1, text="Auto 440", anchor="w",
                         fill=T.ACCENT_SOFT if on else T.SOFT, font=f)
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
