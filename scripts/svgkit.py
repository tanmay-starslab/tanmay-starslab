"""Shared helpers for every SVG in this profile.

All figures are set in Latin Modern (the OpenType Computer Modern that LaTeX
papers use). GitHub renders README SVGs through <img>, which blocks external
font requests, so each SVG embeds a WOFF2 subset of only the glyphs it uses.
"""

from __future__ import annotations

import base64
import html
import io
from dataclasses import dataclass
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "assets" / "fonts"

FACES = {
    "rm": ("lmroman12-regular.otf", "LMRoman", "normal", "normal"),
    "it": ("lmroman12-italic.otf", "LMRoman", "italic", "normal"),
    "bf": ("lmroman12-bold.otf", "LMRoman", "normal", "bold"),
    "sc": ("lmromancaps10-regular.otf", "LMRomanCaps", "normal", "normal"),
    "dunh": ("lmromandunh10-regular.otf", "LMRomanDunh", "normal", "normal"),
    # Greek and math symbols (Ly𝛼, 𝜆); the text faces have no Greek.
    "math": ("latinmodern-math.otf", "LMMath", "normal", "normal"),
}

FALLBACK = "'Latin Modern Roman', 'CMU Serif', 'Computer Modern', Georgia, serif"


@dataclass(frozen=True)
class Theme:
    name: str
    surface: str  # card / figure background
    sky: str  # hero background
    ink: str
    muted: str
    faint: str  # grid lines, rules
    accent: str  # the one data accent (spectrum line, highlights)
    gold: str  # quasar light; second pole of the diverging pair
    neutral: str  # diverging midpoint (draws)
    glow: str  # non-data highlight: quasar core, stars
    link: str  # hyperref-style link boxes


DARK = Theme(
    name="dark",
    surface="#0F1736",
    sky="#0E1433",
    ink="#E8EBF7",
    muted="#9AA2C6",
    faint="#263063",
    accent="#8B7BF5",
    gold="#BC7E26",
    neutral="#5D6487",
    glow="#F6D9A6",
    link="#4FD6E6",
)

LIGHT = Theme(
    name="light",
    surface="#F6F8FC",
    sky="#F6F8FC",
    ink="#141A33",
    muted="#565E80",
    faint="#D7DCEA",
    accent="#5443D1",
    gold="#A8650C",
    neutral="#7D8399",
    glow="#A8650C",
    link="#0098AD",
)

THEMES = (DARK, LIGHT)


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
            if glyph is None:
                total += upm * 0.5
            else:
                total += hmtx[glyph][0]
        return total * size / upm

    def family(self, face: str) -> str:
        return f"'{FACES[face][1]}', {FALLBACK}"

    def style(self, face: str, size: float, fill: str, extra: str = "") -> str:
        _, _, style, weight = FACES[face]
        return (
            f'font-family="{esc(self.family(face))}" font-size="{size:g}" '
            f'font-style="{style}" font-weight="{weight}" fill="{fill}" {extra}'
        ).strip()

    def text(
        self,
        x: float,
        y: float,
        content: str,
        face: str,
        size: float,
        fill: str,
        anchor: str = "start",
        extra: str = "",
    ) -> str:
        self.use(face, content)
        return (
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" '
            f"{self.style(face, size, fill, extra)}>{esc(content)}</text>"
        )

    def rich_width(self, segments: list[tuple[str, str]], size: float) -> float:
        return sum(self.width(face, text, size) for face, text in segments)

    def rich(
        self,
        x: float,
        y: float,
        segments: list[tuple[str, str]],
        size: float,
        fill: str,
        anchor: str = "start",
        extra: str = "",
    ) -> str:
        """One <text> made of differently-faced runs, e.g. [("rm", "O "), ("sc", "vi")]."""
        spans = []
        for face, content in segments:
            self.use(face, content)
            _, _, style, weight = FACES[face]
            spans.append(
                f'<tspan font-family="{esc(self.family(face))}" font-style="{style}" '
                f'font-weight="{weight}">{esc(content)}</tspan>'
            )
        return (
            f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size:g}" '
            f'fill="{fill}" {extra}>{"".join(spans)}</text>'
        )

    def css(self) -> str:
        rules = []
        for face, chars in sorted(self.used.items()):
            filename, family, style, weight = FACES[face]
            chars = set(chars) | {" "}
            opts = subset.Options()
            opts.flavor = "woff2"
            opts.layout_features = ["kern", "liga", "lnum", "onum", "smcp"]
            opts.name_IDs = []
            opts.notdef_outline = True
            opts.hinting = False
            opts.drop_tables = [*opts.drop_tables, "FFTM"]  # FontForge timestamp; not needed
            sub = subset.Subsetter(options=opts)
            sub.populate(text="".join(sorted(chars)))
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


def document(width: int, height: int, body: str, fonts: Fonts, css: str = "", title: str = "") -> str:
    head = f"<title>{esc(title)}</title>" if title else ""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{esc(title)}">'
        f"{head}<style>{fonts.css()}{css}</style>{body}</svg>\n"
    )


def write(path: Path, content: str) -> bool:
    """Write only when the content changed, so scheduled runs commit only real updates."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8") == content:
        return False
    path.write_text(content, encoding="utf-8")
    return True
