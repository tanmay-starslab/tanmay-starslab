"""Draw the pixel-art GIFs: a coder at a desk, a waving astronaut, a cat and
the small section icons (planet, chart, telescope).

Everything is drawn here from rectangles, lines and character grids on a
tiny canvas, then scaled up with nearest-neighbour so the pixels stay crisp.
Backgrounds are transparent, so the sprites sit on light and dark pages.

    pip install pillow
    python scripts/make_pixel_gifs.py
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "pixel"

PAL = {
    "K": (27, 31, 59), "N": (21, 30, 82), "n": (13, 18, 52), "M": (43, 47, 74), "m": (70, 76, 112),
    "V": (139, 123, 245), "v": (91, 75, 196), "u": (183, 173, 255),
    "G": (230, 181, 102), "g": (185, 119, 42), "W": (244, 245, 251), "w": (201, 205, 224),
    "S": (224, 169, 126), "s": (185, 127, 89), "H": (42, 30, 26),
    "B": (122, 78, 45), "b": (87, 54, 31), "T": (95, 214, 196), "R": (240, 139, 166),
    "J": (46, 58, 110), "j": (32, 40, 80), "P": (91, 179, 106), "p": (62, 127, 74),
}


class Canvas:
    def __init__(self, w: int, h: int) -> None:
        self.w, self.h = w, h
        self.px: list[list[tuple | None]] = [[None] * w for _ in range(h)]

    def dot(self, x: int, y: int, c: str | tuple | None) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            self.px[y][x] = PAL[c] if isinstance(c, str) else c

    def rect(self, x: int, y: int, w: int, h: int, c) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.dot(xx, yy, c)

    def line(self, x0: float, y0: float, x1: float, y1: float, c, t: int = 1) -> None:
        n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
        for i in range(n + 1):
            x = round(x0 + (x1 - x0) * i / n)
            y = round(y0 + (y1 - y0) * i / n)
            self.rect(x - (t - 1) // 2, y - (t - 1) // 2, t, t, c)

    def disc(self, cx: float, cy: float, r: float, c) -> None:
        for y in range(int(cy - r - 1), int(cy + r + 2)):
            for x in range(int(cx - r - 1), int(cx + r + 2)):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    self.dot(x, y, c)

    def grid(self, x: int, y: int, rows: list[str]) -> None:
        """Paint a character grid; '.' is transparent."""
        for j, row in enumerate(rows):
            for i, ch in enumerate(row):
                if ch != ".":
                    self.dot(x + i, y + j, ch)

    def outline(self, c: str = "K") -> "Canvas":
        """A one-pixel outline around everything drawn, so pale sprites read on white."""
        edge = [(x, y) for y in range(self.h) for x in range(self.w) if self.px[y][x] is None and any(
            0 <= x + dx < self.w and 0 <= y + dy < self.h and self.px[y + dy][x + dx] is not None
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))]
        for x, y in edge:
            self.dot(x, y, c)
        return self

    def image(self, scale: int) -> Image.Image:
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        for y, row in enumerate(self.px):
            for x, c in enumerate(row):
                if c is not None:
                    img.putpixel((x, y), (*c, 255))
        return img.resize((self.w * scale, self.h * scale), Image.Resampling.NEAREST)


def save_gif(frames: list[Image.Image], path: Path, ms: int | list[int]) -> None:
    """Save RGBA frames as a GIF with one transparent palette slot."""
    def pixels(img: Image.Image) -> list[tuple]:
        raw = img.tobytes()
        return [tuple(raw[i : i + 4]) for i in range(0, len(raw), 4)]

    colors: dict[tuple, int] = {}
    data = [pixels(f) for f in frames]
    for px in data:
        for c in px:
            if c[3] and c[:3] not in colors:
                colors[c[:3]] = len(colors) + 1
    palette = [0, 0, 0] + [v for c in colors for v in c]
    indexed = []
    for f, px in zip(frames, data):
        p = Image.new("P", f.size, 0)
        p.putpalette(palette + [0] * (768 - len(palette)))
        p.putdata([colors[c[:3]] if c[3] else 0 for c in px])
        indexed.append(p)
    path.parent.mkdir(parents=True, exist_ok=True)
    indexed[0].save(path, save_all=True, append_images=indexed[1:], duration=ms, loop=0,
                    transparency=0, disposal=2, optimize=False)
    print(f"wrote {path.relative_to(ROOT)} ({path.stat().st_size / 1000:.0f} kB, {len(frames)} frames)")


# --------------------------------------------------------------------------- coder at a desk


def coder_frames() -> list[Image.Image]:
    rng = random.Random(5)
    # A long column of "code" lines the screen scrolls through.
    code = []
    for _ in range(40):
        indent = rng.choice([0, 0, 2, 2, 4, 6])
        parts, x = [], indent
        for _ in range(rng.randint(1, 3)):
            ln = rng.randint(2, 7)
            if x + ln > 19:
                break
            parts.append((x, ln, rng.choice("VVTGRwu")))
            x += ln + 1
        code.append(parts)
    stars = [(47, 4), (52, 8), (58, 3), (66, 11), (49, 14), (61, 15), (55, 12), (68, 5)]
    frames = []
    for f in range(12):
        c = Canvas(74, 56)
        # Window with the night sky.
        c.rect(43, 1, 29, 21, "M")
        c.rect(44, 2, 27, 19, "N")
        for i, (sx, sy) in enumerate(stars):
            if (i + f) % 4 != 0:
                c.dot(sx, sy, "W" if (i + f) % 3 else "u")
        c.disc(65, 7, 3.2, "G")
        c.disc(66.5, 6, 2.6, "N")  # crescent
        if 4 <= f <= 6:  # shooting star
            hx = 60 - (f - 4) * 6
            c.line(hx, 3 + (f - 4) * 2, hx + 4, 1 + (f - 4) * 2, "u")
            c.dot(hx, 3 + (f - 4) * 2, "W")
        c.rect(57, 2, 1, 19, "M")
        c.rect(44, 11, 27, 1, "M")
        c.rect(42, 21, 31, 2, "m")  # sill
        # Desk.
        c.rect(1, 38, 42, 2, "B")
        c.rect(1, 40, 42, 1, "b")
        c.rect(3, 41, 2, 13, "b")
        c.rect(38, 41, 2, 13, "b")
        # Monitor with scrolling code.
        c.rect(7, 15, 24, 19, "M")
        c.rect(8, 16, 22, 17, "n")
        for row in range(8):
            parts = code[(row + f) % len(code)]
            for x, ln, col in parts:
                c.rect(9 + x, 17 + row * 2, ln, 1, col)
        if f % 2 == 0:  # blinking cursor
            c.rect(9 + 4, 17 + 7 * 2, 2, 1, "W")
        c.rect(18, 34, 3, 3, "M")
        c.rect(15, 37, 9, 1, "M")
        # Keyboard and mug with steam.
        c.rect(24, 37, 11, 1, "w")
        c.rect(3, 33, 4, 5, "W")
        c.rect(7, 34, 1, 2, "W")
        c.rect(4, 34, 2, 1, "R")
        # Chair.
        c.rect(58, 22, 2, 20, "K")
        c.rect(46, 41, 14, 2, "K")
        c.rect(52, 43, 2, 7, "K")
        c.rect(47, 50, 12, 1, "K")
        c.dot(47, 51, "m"), c.dot(58, 51, "m")
        # Person, side view, facing the screen.
        c.rect(47, 28, 9, 13, "V")  # hoodie
        c.rect(47, 28, 2, 13, "v")
        c.rect(40, 40, 11, 3, "J")  # thigh
        c.rect(39, 42, 3, 10, "J")  # shin
        c.rect(36, 52, 6, 2, "K")  # shoe
        c.rect(45, 17, 9, 4, "H")  # hair
        c.rect(51, 20, 3, 6, "H")
        c.rect(45, 21, 6, 6, "S")  # face
        c.rect(44, 23, 1, 2, "S")  # nose
        c.rect(50, 22, 1, 2, "s")  # ear
        c.dot(46, 22, "K")  # eye
        c.rect(45, 26, 5, 1, "s")
        c.rect(49, 27, 3, 1, "S")  # neck
        # Typing arms: the hands take turns.
        up = f % 2
        c.line(49, 30, 42, 35, "v", 2)
        c.line(42, 35, 35, 36 - up, "V", 2)
        c.rect(33, 36 - up, 2, 2, "S")
        c.line(52, 31, 44, 36, "V", 2)
        c.rect(29, 37 - (1 - up), 2, 1, "S")
        c.outline()
        # Steam goes on after the outline, so it stays a soft wisp.
        for k in range(3):
            y = 31 - k * 2 - (f % 3)
            x = 4 + ((f + k) % 2)
            if y > 24:
                c.dot(x, y, "w")
        frames.append(c.image(5))
    return frames


# --------------------------------------------------------------------------- waving astronaut


def astronaut_frames() -> list[Image.Image]:
    frames = []
    for f in range(6):
        c = Canvas(30, 30)
        bob = 1 if f in (2, 3) else 0
        y0 = 1 + bob
        # Backpack, suit, legs.
        c.rect(8, 15 + y0, 14, 9, "w")
        c.rect(9, 14 + y0, 12, 10, "W")
        c.rect(12, 17 + y0, 4, 3, "V")
        c.dot(17, 18 + y0, "G"), c.dot(18, 18 + y0, "R")
        c.rect(10, 24 + y0, 4, 4, "W")
        c.rect(16, 24 + y0, 4, 4, "W")
        c.rect(10, 27 + y0, 4, 1, "m"), c.rect(16, 27 + y0, 4, 1, "m")
        # Helmet and visor.
        c.disc(15, 8 + y0, 7.4, "W")
        c.disc(14, 8.5 + y0, 5, "v")
        c.rect(11, 6 + y0, 2, 2, "u")
        c.dot(16, 11 + y0, "V")
        # Left arm resting; right arm waves through three angles.
        c.line(9, 16 + y0, 6, 22 + y0, "W", 3)
        angle = [-60, -35, -10, -35, -60, -85][f]
        ex = 21 + 5 * math.cos(math.radians(angle))
        ey = 16 + y0 + 5 * math.sin(math.radians(angle))
        c.line(20, 16 + y0, ex, ey, "W", 3)
        c.disc(ex, ey - 0.5, 1.6, "w")
        frames.append(c.outline().image(4))
    return frames


# --------------------------------------------------------------------------- cat

CAT = [
    "..m...m.....",
    "..mm.mm.....",
    ".mmmmmmm....",
    ".mGmmmGm....",
    ".mmmRmmm....",
    "..mmmmm.....",
    "..mmmmmm....",
    ".mmmmmmmm...",
    ".mmmmmmmm...",
    ".mmmmmmmmm..",
    ".mmmmmmmmm..",
    ".mm.mm.mmm..",
]


def cat_frames() -> list[Image.Image]:
    frames = []
    tails = [[(10, 10), (12, 8), (12, 6)], [(10, 10), (13, 9), (14, 7)], [(10, 10), (13, 10), (15, 9)],
             [(10, 10), (13, 9), (14, 7)]]
    for f in range(8):
        c = Canvas(20, 16)
        rows = [r for r in CAT]
        if f == 5:  # blink
            rows[3] = ".mmmmmmm...."
        c.grid(2, 3, rows)
        pts = tails[f % 4]
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            c.line(2 + ax, 3 + ay, 2 + bx, 3 + by, "m", 1)
        if f % 4 < 2:  # a star twinkles above
            c.dot(16, 2, "G"), c.dot(15, 2, "g"), c.dot(17, 2, "g"), c.dot(16, 1, "g"), c.dot(16, 3, "g")
        frames.append(c.outline().image(4))
    return frames


# --------------------------------------------------------------------------- section icons


def planet_frames() -> list[Image.Image]:
    frames = []
    for f in range(8):
        c = Canvas(22, 22)
        a = 2 * math.pi * f / 8
        mx, my = 11 + 9.5 * math.cos(a), 11 + 3.5 * math.sin(a)
        behind = math.sin(a) < 0
        if behind:
            c.disc(mx, my, 1.3, "w")
        ring = [(11 + 9.5 * math.cos(t), 11 + 2.6 * math.sin(t) + 0.35 * 9.5 * math.cos(t) * 0.3)
                for t in (2 * math.pi * k / 80 for k in range(80))]
        for x, y in ring:
            if y < 11:
                c.dot(round(x), round(y), "v")
        c.disc(11, 11, 5.6, "G")
        c.rect(7, 9, 9, 1, "g")
        c.rect(6, 13, 10, 1, "g")
        for x, y in ring:
            if y >= 11:
                c.dot(round(x), round(y), "V")
        if not behind:
            c.disc(mx, my, 1.3, "W")
        frames.append(c.outline().image(3))
    return frames


def chart_frames() -> list[Image.Image]:
    heights = [3, 6, 4, 8, 5, 10]
    frames = []
    for f in range(8):
        c = Canvas(22, 22)
        c.rect(2, 3, 18, 13, "M")
        c.rect(3, 4, 16, 11, "n")
        grow = min(1.0, (f + 1) / 6)
        for i, h in enumerate(heights):
            hh = max(1, round(h * grow))
            c.rect(4 + i * 2 + i // 2, 14 - hh, 2, hh, "V" if i < 5 else "G")
        c.rect(9, 16, 4, 2, "M")
        c.rect(6, 18, 10, 1, "M")
        frames.append(c.outline().image(3))
    return frames


def telescope_frames() -> list[Image.Image]:
    frames = []
    for f in range(6):
        c = Canvas(22, 22)
        c.line(5, 15, 15, 7, "W", 3)
        c.line(14, 8, 17, 5, "V", 3)
        c.line(9, 13, 6, 20, "m", 1)
        c.line(9, 13, 12, 20, "m", 1)
        c.line(9, 13, 9, 20, "m", 1)
        big = f % 3 == 0
        c.dot(19, 2, "G")
        if big:
            c.dot(18, 2, "g"), c.dot(20, 2, "g"), c.dot(19, 1, "g"), c.dot(19, 3, "g")
        c.dot(3, 4, "u" if f % 2 else "w")
        frames.append(c.outline().image(3))
    return frames


def main() -> None:
    save_gif(coder_frames(), OUT / "coder.gif", 150)
    save_gif(astronaut_frames(), OUT / "astronaut.gif", 160)
    save_gif(cat_frames(), OUT / "cat.gif", [220, 220, 220, 220, 220, 120, 220, 220])
    save_gif(planet_frames(), OUT / "planet.gif", 140)
    save_gif(chart_frames(), OUT / "chart.gif", [120] * 7 + [1400])
    save_gif(telescope_frames(), OUT / "telescope.gif", 260)


if __name__ == "__main__":
    main()
