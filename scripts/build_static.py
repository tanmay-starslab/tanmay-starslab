"""Build the static animated SVGs for the profile.

    python scripts/build_static.py

Everything here is wordless or nearly so: the typing line, the link chips
and the tool orbits. (The pixel-art GIFs come from make_pixel_gifs.py; the
hero, the galaxy merger and the footer change daily and come from daily.py.)
Animations are CSS keyframes, which GitHub plays inside <img>; each file also
honours prefers-reduced-motion.
"""

from __future__ import annotations

import math
import random
import re

from svgkit import ROOT, Fonts, C, document, esc, write

ASSETS = ROOT / "assets"
ICONS = ASSETS / "icons"


# --------------------------------------------------------------------------- shared pieces


def starfield(rng: random.Random, w: float, h: float, n: int, twinkle_every: int = 7,
              avoid=None) -> tuple[str, str]:
    stars = []
    for i in range(n):
        x, y = rng.uniform(0, w), rng.uniform(0, h)
        if avoid and avoid(x, y):
            continue
        r = rng.choice([0.5, 0.6, 0.7, 0.9, 1.1, 1.4])
        fill = rng.choice([C.ink, C.ink, C.glow, C.violet_hi])
        op = rng.uniform(0.35, 0.95)
        cls = ""
        if i % twinkle_every == 0:
            cls = (f' class="tw" style="animation-duration:{rng.uniform(2.4, 5.6):.2f}s;'
                   f'animation-delay:{-rng.uniform(0, 5):.2f}s"')
        stars.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{fill}" opacity="{op:.2f}"{cls}/>')
    css = "@keyframes tw{0%,100%{opacity:.95}50%{opacity:.12}}.tw{animation:tw 4s ease-in-out infinite}"
    return "".join(stars), css


def icon_inner(name: str, size: float) -> str:
    """A devicon/simple-icons SVG, scaled to `size` and centred on the origin."""
    raw = (ICONS / f"{name}.svg").read_text(encoding="utf-8")
    raw = re.sub(r"<\?xml.*?\?>|<title>.*?</title>", "", raw, flags=re.S)
    vb = re.search(r'viewBox="([^"]+)"', raw).group(1).split()
    vx, vy, vw, vh = (float(v) for v in vb)
    inner = re.sub(r"^.*?<svg[^>]*>|</svg>\s*$", "", raw.strip(), flags=re.S)
    k = size / max(vw, vh)
    return (f'<g transform="translate({-size / 2:.2f} {-size / 2:.2f}) scale({k:.4f}) '
            f'translate({-vx:g} {-vy:g})">{inner}</g>')


# --------------------------------------------------------------------------- typing line

PHRASES = [
    "tracing quasar light through galaxies",
    "turning simulations into spectra",
    "debugging at 3 a.m.",
    "git push origin main",
]


def typing() -> str:
    fonts = Fonts()
    W, H, size = 1200, 64, 30
    prefix = "> "
    widest = max(fonts.width("tt", prefix + p, size) for p in PHRASES)
    x0 = (W - widest) / 2
    px = x0 + fonts.width("tt", prefix, size)
    y = 42
    slot, type_dt, erase_dt, lead = 5.2, 0.055, 0.025, 0.3
    total = slot * len(PHRASES)
    pct = lambda t: f"{t / total * 100:.4f}%"  # noqa: E731
    css = [
        ".tc{visibility:hidden;animation-timing-function:step-end;animation-iteration-count:infinite;"
        f"animation-duration:{total}s}}.tc.on{{visibility:visible}}"
    ]
    body = [fonts.text(x0, y, prefix, "tt", size, C.violet)]
    caret = []
    kf = 0
    for i, phrase in enumerate(PHRASES):
        start, end = i * slot + lead, (i + 1) * slot - 0.4
        spans, offset = [], 0.0
        for k, ch in enumerate(phrase):
            t_on = start + k * type_dt
            t_off = end - k * erase_dt  # backspace: the last character goes first
            css.append(f"@keyframes k{kf}{{0%{{visibility:hidden}}{pct(t_on)}{{visibility:visible}}"
                       f"{pct(t_off)}{{visibility:hidden}}100%{{visibility:hidden}}}}")
            fonts.use("tt", ch)
            spans.append(f'<tspan class="tc{" on" if i == 0 else ""}" style="animation-name:k{kf}">{esc(ch)}</tspan>')
            w = fonts.width("tt", ch, size)
            offset += w
            caret += [(t_on, offset), (t_off, offset - w)]
            kf += 1
        body.append(f'<text x="{px:.1f}" y="{y}" {fonts.style("tt", size, C.violet)} '
                    f'style="font-kerning:none;font-variant-ligatures:none">{"".join(spans)}</text>')
    caret.sort()
    stops = "0%{transform:translateX(0px)}" + "".join(f"{pct(t)}{{transform:translateX({x:.1f}px)}}" for t, x in caret)
    css.append(f"@keyframes caret{{{stops}}}")
    first = fonts.width("tt", PHRASES[0], size)
    css.append(f".cm{{transform:translateX({first:.1f}px);animation:caret {total}s step-end infinite}}"
               "@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}.cb{animation:blink 1s step-end infinite}")
    body.append(f'<g class="cm"><rect class="cb" x="{px + 2:.1f}" y="{y - 24}" width="13" height="28" fill="{C.violet}" opacity=".85"/></g>')
    return document(W, H, "".join(body), fonts, "".join(css), title="; ".join(PHRASES))


# --------------------------------------------------------------------------- link chips


def chip_icon(kind: str) -> str:
    s = C.violet_hi
    if kind == "website":
        return (f'<g fill="none" stroke="{s}" stroke-width="1.6"><circle r="9"/><ellipse rx="4" ry="9"/>'
                f'<path d="M-9,0 H9 M-7.5,-5 H7.5 M-7.5,5 H7.5"/></g>')
    if kind == "reroll":
        pips = "".join(f'<circle cx="{x}" cy="{y}" r="1.6"/>' for x, y in ((-4.5, -4.5), (0, 0), (4.5, 4.5), (4.5, -4.5), (-4.5, 4.5)))
        return (f'<g class="roll"><rect x="-10" y="-10" width="20" height="20" rx="4.5" fill="none" stroke="{C.gold}" '
                f'stroke-width="1.6"/><g fill="{C.gold}">{pips}</g></g>')
    if kind == "email":
        return (f'<g fill="none" stroke="{s}" stroke-width="1.6" stroke-linejoin="round">'
                f'<rect x="-10" y="-7" width="20" height="14" rx="2"/><path d="M-10,-6 L0,2 L10,-6"/></g>')
    icon = icon_inner({"scholar": "googlescholar", "linkedin": "linkedin-plain"}[kind], 20)
    return f'<g fill="{s}">{icon}</g>'


CHIPS = [("website", "website"), ("scholar", "scholar"), ("linkedin", "linkedin"), ("email", "email")]


REROLL_CSS = ("@keyframes roll{0%,78%{transform:rotate(0)}88%{transform:rotate(200deg)}100%{transform:rotate(180deg)}}"
              ".roll{animation:roll 6s cubic-bezier(.3,.7,.3,1) infinite}")


def chip(kind: str, label: str) -> str:
    fonts = Fonts()
    size = 20
    w = 56 + fonts.width("rm", label, size) + 20
    h = 44
    body = (
        f'<rect x="1" y="1" width="{w - 2:.1f}" height="{h - 2}" rx="21" fill="{C.panel}" stroke="{C.edge}" stroke-width="1.2"/>'
        f'<g transform="translate(30 22)">{chip_icon(kind)}</g>'
        + fonts.text(52, 29, label, "rm", size, C.ink)
    )
    return document(round(w), h, body, fonts, REROLL_CSS if kind == "reroll" else "", title=label)


# --------------------------------------------------------------------------- tool orbits

TOOLS_W, TOOLS_H = 1200, 570
SQUASH = 0.42
RINGS = [
    # radius, period (s), stroke colour, items: (icon file or None, glyph label)
    (175, 34, C.violet, [("python", None), ("javascript", None), ("typescript", None), ("bash-plain", None), ("latex", None)]),
    (330, 58, C.teal, [("numpy", None), (None, "SciPy"), ("pandas", None), ("matplotlib", None), ("jupyter", None),
                       (None, "astropy"), ("pytorch", None), ("scikitlearn", None)]),
    (505, 88, C.gold, [(None, "yt"), ("git", None), (None, "Trident"), ("githubactions", None), (None, "h5py"),
                       ("linux-plain", None), (None, "Manim"), ("vscode", None), (None, "Slurm"), ("opencv", None)]),
]


def tools() -> str:
    fonts = Fonts()
    rng = random.Random(7)
    cx, cy = TOOLS_W / 2, TOOLS_H / 2
    stars, star_css = starfield(rng, TOOLS_W, TOOLS_H, 170, 6)
    css = [star_css,
           "@keyframes orbit{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}",
           "@keyframes breathe{0%,100%{transform:scale(1)}50%{transform:scale(1.08)}}",
           ".sun{animation:breathe 5s ease-in-out infinite}",
           "@keyframes rays{to{transform:rotate(360deg)}}.rays{animation:rays 60s linear infinite}"]
    # Counter-rotation keeps each icon upright and undoes the squash; the
    # scale and opacity fake depth (front of the orbit is larger and brighter).
    steps = 24
    stops = []
    for j in range(steps + 1):
        phi = 360 * j / steps
        s = 1 + 0.2 * math.sin(math.radians(phi))
        op = 0.55 + 0.45 * (1 + math.sin(math.radians(phi))) / 2
        stops.append(f"{100 * j / steps:.3f}%{{transform:rotate({-phi:.1f}deg) scale({s:.3f},{s / SQUASH:.3f});opacity:{op:.3f}}}")
    css.append(f"@keyframes counter{{{''.join(stops)}}}")

    glyph_colors = [("#6E5CF0", "#3B2E9E"), ("#2BB3A0", "#156B60"), ("#D9962E", "#8A5A12")]
    rings_svg, items_svg = [], []
    for ri, (radius, period, stroke, items) in enumerate(RINGS):
        rings_svg.append(
            f'<ellipse cx="{cx}" cy="{cy}" rx="{radius}" ry="{radius * SQUASH:.1f}" fill="none" stroke="{stroke}" '
            f'stroke-opacity=".38" stroke-width="1.2" stroke-dasharray="3 7"/>'
        )
        disc_r = 31 - ri * 2
        for i, (icon, label) in enumerate(items):
            phase = 360 * i / len(items)
            delay = -period * i / len(items)
            s0 = 1 + 0.2 * math.sin(math.radians(phase))
            if icon:
                face = (f'<circle r="{disc_r}" fill="{C.disc}"/><circle r="{disc_r}" fill="none" stroke="{stroke}" '
                        f'stroke-opacity=".7" stroke-width="2"/>{icon_inner(icon, disc_r * 1.25)}')
            else:
                c1, c2 = glyph_colors[ri]
                size = min(17.0, (disc_r * 1.6) / max(fonts.width("bf", label, 1), 0.01))
                face = (f'<circle r="{disc_r}" fill="url(#g{ri})"/><circle r="{disc_r}" fill="none" stroke="{stroke}" '
                        f'stroke-opacity=".8" stroke-width="2"/>'
                        + fonts.text(0, size * 0.35, label, "bf", round(size, 1), "#FFFFFF", "middle"))
            items_svg.append(
                f'<g style="transform:rotate({phase:.1f}deg);animation:orbit {period}s linear {delay:.2f}s infinite">'
                f'<g transform="translate({radius} 0)">'
                f'<g style="transform:rotate({-phase:.1f}deg) scale({s0:.3f},{s0 / SQUASH:.3f});'
                f'animation:counter {period}s linear {delay:.2f}s infinite">{face}</g></g></g>'
            )
    defs = (
        f'<defs><radialGradient id="bg" cx="50%" cy="50%" r="70%"><stop offset="0" stop-color="{C.sky_top}"/>'
        f'<stop offset="1" stop-color="{C.sky}"/></radialGradient>'
        f'<radialGradient id="sunglow"><stop offset="0" stop-color="{C.glow}" stop-opacity=".55"/>'
        f'<stop offset="1" stop-color="{C.glow}" stop-opacity="0"/></radialGradient>'
        f'<radialGradient id="sun" cx="40%" cy="38%"><stop offset="0" stop-color="#FFFFFF"/>'
        f'<stop offset=".5" stop-color="{C.glow}"/><stop offset="1" stop-color="{C.gold}"/></radialGradient>'
        + "".join(f'<linearGradient id="g{i}" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{a}"/>'
                  f'<stop offset="1" stop-color="{b}"/></linearGradient>' for i, (a, b) in enumerate(glyph_colors))
        + "</defs>"
    )
    rays = "".join(
        f'<line x1="0" y1="-48" x2="0" y2="-70" stroke="{C.glow}" stroke-opacity=".5" stroke-width="1.4" '
        f'stroke-linecap="round" transform="rotate({a})"/>' for a in range(0, 360, 30)
    )
    sun = (f'<g transform="translate({cx} {cy})"><circle r="120" fill="url(#sunglow)"/>'
           f'<g class="rays">{rays}</g><g class="sun"><circle r="38" fill="url(#sun)"/></g></g>')
    body = (
        defs + f'<rect width="{TOOLS_W}" height="{TOOLS_H}" rx="22" fill="url(#bg)"/>' + stars
        + "".join(rings_svg) + sun
        + f'<g transform="translate({cx} {cy}) scale(1 {SQUASH})">{"".join(items_svg)}</g>'
    )
    return document(TOOLS_W, TOOLS_H, body, fonts, "".join(css),
                    title="Tools orbiting a star: Python, JavaScript, TypeScript, Bash, LaTeX; NumPy, SciPy, pandas, "
                          "Matplotlib, Jupyter, Astropy, PyTorch, scikit-learn; yt, Git, Trident, GitHub Actions, "
                          "h5py, Linux, Manim, VS Code, Slurm, OpenCV")


def main() -> None:
    outputs = {
        ASSETS / "typing.svg": typing(),
        ASSETS / "tools.svg": tools(),
    }
    for kind, label in [*CHIPS, ("reroll", "roll a new universe")]:
        outputs[ASSETS / "chips" / f"{kind}.svg"] = chip(kind, label)
    for path, content in outputs.items():
        if write(path, content):
            print(f"wrote {path.relative_to(ROOT)} ({len(content) / 1000:.0f} kB)")


if __name__ == "__main__":
    main()
