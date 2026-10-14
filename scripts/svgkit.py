"""Shared helpers for every SVG in this profile.

Text is set in Latin Modern, the OpenType Computer Modern of LaTeX. GitHub
renders README SVGs through <img>, which blocks external font requests, so
each SVG embeds a WOFF2 subset of only the glyphs it uses.
"""

from __future__ import annotations

import base64
import html
import io
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "assets" / "fonts"

FACES = {
    "rm": ("lmroman12-regular.otf", "LMRoman", "normal", "normal"),
    "it": ("lmroman12-italic.otf", "LMRoman", "italic", "normal"),
    "bf": ("lmroman12-bold.otf", "LMRoman", "normal", "bold"),
    "tt": ("lmmono10-regular.otf", "LMMono", "normal", "normal"),
}

FALLBACK = "'Latin Modern Roman', 'CMU Serif', Georgia, serif"


class C:
    """The palette: a deep-space night with violet and gold light."""

    sky = "#0B1030"
    sky_top = "#151E52"
    panel = "#0F1736"
    ink = "#E8EBF7"
    muted = "#9AA2C6"
    faint = "#263063"
    violet = "#8B7BF5"
    violet_hi = "#B7ADFF"
    gold = "#E6B566"
    glow = "#F6D9A6"
    teal = "#5FD6C4"
    rose = "#F08BA6"
    disc = "#EEF0FA"


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


class Fonts:
    """Records which glyphs each face needs, measures text, emits @font-face CSS."""

    _cache: dict[str, TTFont] = {}

    def __init__(self) -> None:
        self.used: dict[str, set[str]] = {}

    @classmethod
    def _font(cls, face: str) -> TTFont:
        if face not in cls._cache:
            cls._cache[face] = TTFont(FONT_DIR / FACES[face][0])
        return cls._cache[face]

    def use(self, face: str, text: str) -> str:
        self.used.setdefault(face, set()).update(str(text))
        return str(text)

    def width(self, face: str, text: str, size: float) -> float:
        font = self._font(face)
        cmap = font.getBestCmap()
        hmtx = font["hmtx"]
        upm = font["head"].unitsPerEm
        total = 0
        for ch in str(text):
            glyph = cmap.get(ord(ch))
            total += hmtx[glyph][0] if glyph else upm * 0.5
        return total * size / upm

    def family(self, face: str) -> str:
        return f"'{FACES[face][1]}', {FALLBACK}"

    def style(self, face: str, size: float, fill: str, extra: str = "") -> str:
        _, _, style, weight = FACES[face]
        return (
            f'font-family="{esc(self.family(face))}" font-size="{size:g}" '
            f'font-style="{style}" font-weight="{weight}" fill="{fill}" {extra}'
        ).strip()

    def text(self, x: float, y: float, content: str, face: str, size: float, fill: str,
             anchor: str = "start", extra: str = "") -> str:
        self.use(face, content)
        return (
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
            f"{self.style(face, size, fill, extra)}>{esc(content)}</text>"
        )

    def css(self) -> str:
        rules = []
        for face, chars in sorted(self.used.items()):
            filename, family, style, weight = FACES[face]
            opts = subset.Options()
            opts.flavor = "woff2"
            opts.layout_features = ["kern", "liga", "lnum"]
            opts.name_IDs = []
            opts.notdef_outline = True
            opts.hinting = False
            opts.drop_tables = [*opts.drop_tables, "FFTM"]  # FontForge timestamp; not needed
            sub = subset.Subsetter(options=opts)
            sub.populate(text="".join(sorted(set(chars) | {" "})))
            # Fixed timestamps keep the output byte-identical between runs.
            font = TTFont(FONT_DIR / filename, recalcTimestamp=False)
            sub.subset(font)
            buf = io.BytesIO()
            font.flavor = "woff2"
            font.save(buf)
            data = base64.b64encode(buf.getvalue()).decode("ascii")
            rules.append(
                "@font-face{"
                f"font-family:'{family}';font-style:{style};font-weight:{weight};"
                f"src:url(data:font/woff2;base64,{data}) format('woff2');"
                "}"
            )
        return "".join(rules)


REDUCED_MOTION = "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"


def document(width: int, height: int, body: str, fonts: Fonts | None = None, css: str = "", title: str = "") -> str:
    head = f"<title>{esc(title)}</title>" if title else ""
    font_css = fonts.css() if fonts else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">'
        f"{head}<style>{font_css}{css}{REDUCED_MOTION}</style>{body}</svg>\n"
    )


def write(path: Path, content: str) -> bool:
    """Write only when the content changed, so scheduled runs commit only real updates."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True
