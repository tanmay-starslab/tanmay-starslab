"""Build the static animated SVGs for the profile.

    python scripts/build_static.py

Everything here is wordless or nearly so: the hero, the typing line, the
link chips, the tool orbits and the aurora footer. (The pixel-art GIFs come
from make_pixel_gifs.py, the galaxy merger from make_merger.py.) Animations are CSS keyframes, which GitHub plays inside
<img>; each file also honours prefers-reduced-motion.
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


# --------------------------------------------------------------------------- hero

HERO_W, HERO_H = 1200, 420
QSO = (1095.0, 62.0)
PRISM = (275.0, 298.0)
GAL = (560.0, 150.0)
HALO_R = 120.0
SX0, SX1 = 60.0, 1140.0
SY_TOP, SY_BASE = 322.0, 396.0
LMIN, LMAX = 1000.0, 2900.0
EMISSION = [(1025.7, 0.3, 9), (1215.7, 1.25, 16), (1240.0, 0.35, 9), (1400.0, 0.2, 16),
            (1549.0, 0.62, 20), (1909.0, 0.3, 26), (2798.0, 0.42, 34)]
ABSORPTION = [(1031.9, 1.6, 1.1), (1037.6, 1.0, 1.1), (1393.8, 1.1, 1.1), (1402.8, 0.7, 1.1),
              (1548.2, 1.8, 0.9), (1550.8, 1.2, 0.9), (2796.4, 2.2, 1.6), (2803.5, 1.7, 1.6)]


def wl_x(lam: float) -> float:
    f = (math.log(lam) - math.log(LMIN)) / (math.log(LMAX) - math.log(LMIN))
    return SX0 + f * (SX1 - SX0)


def quasar_spectrum() -> tuple[str, str]:
    """Observed spectrum and unabsorbed continuum, as SVG path data."""
    rng = random.Random(1216)
    n = 1400
    lams = [LMIN * (LMAX / LMIN) ** (i / (n - 1)) for i in range(n)]
    forest = [(rng.uniform(1005, 1212), rng.uniform(0.2, 1.5), rng.uniform(1.0, 2.0)) for _ in range(48)]
    flux, model = [], []
    for lam in lams:
        f = (lam / 1450.0) ** -0.55
        for c, a, s in EMISSION:
            f += a * math.exp(-0.5 * ((lam - c) / s) ** 2)
        model.append(f)
        tau = sum(t * math.exp(-0.5 * ((lam - c) / s) ** 2) for c, t, s in forest)
        tau += sum(t * math.exp(-0.5 * ((lam - c) / s) ** 2) for c, t, s in ABSORPTION)
        flux.append(max(f * math.exp(-tau) + rng.gauss(0, 0.018), 0.0))
    top = max(model)
    to_d = lambda fs, step=1: "M" + " L".join(  # noqa: E731
        f"{wl_x(lam):.1f},{SY_BASE - v / top * (SY_BASE - SY_TOP):.1f}" for lam, v in list(zip(lams, fs))[::step]
    )
    return to_d(flux), to_d(model, 7)


def spiral_galaxy(rng: random.Random) -> str:
    dots = []
    for i in range(720):
        arm = i % 2
        t = rng.random() ** 0.8
        theta = t * 3.3 * math.pi + arm * math.pi
        r = 10 + 98 * t + rng.gauss(0, 3 + 7 * t)
        ang = theta + rng.gauss(0, 0.16)
        x, y = r * math.cos(ang), r * math.sin(ang)
        color = C.glow if r < 26 else rng.choice([C.violet_hi, C.ink, "#9FB6FF", C.violet_hi])
        dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rng.choice([0.7, 0.9, 1.1, 1.4]) * 1.3:.2f}" '
                    f'fill="{color}" opacity="{rng.uniform(0.35, 0.95):.2f}"/>')
    for _ in range(160):  # bulge
        x, y = rng.gauss(0, 9), rng.gauss(0, 9)
        dots.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="1.3" fill="{C.glow}" opacity="{rng.uniform(0.4, 0.9):.2f}"/>')
    gx, gy = GAL
    return (
        f'<circle cx="{gx}" cy="{gy}" r="{HALO_R}" fill="url(#halo)"/>'
        f'<circle cx="{gx}" cy="{gy}" r="{HALO_R}" fill="none" stroke="{C.muted}" stroke-opacity=".45" '
        f'stroke-dasharray="2 6"/>'
        f'<g transform="translate({gx} {gy}) rotate(-18) scale(1 0.42)">'
        f'<ellipse rx="118" ry="118" fill="url(#disk)"/>'
        f'<g class="spin">{"".join(dots)}</g>'
        f'<circle r="16" fill="url(#core)"/></g>'
    )


def hero() -> str:
    rng = random.Random(42)
    stars, star_css = starfield(rng, HERO_W, 310, 230, 6)
    (qx, qy), (px, py), (gx, gy) = QSO, PRISM, GAL
    dx, dy = px - qx, py - qy
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    t = (gx - qx) * ux + (gy - qy) * uy
    b = math.hypot(gx - (qx + t * ux), gy - (qy + t * uy))
    half = math.sqrt(max(HALO_R**2 - b**2, 0))
    f_in, f_out = (t - half) / length, (t + half) / length
    spec, model = quasar_spectrum()

    defs = f"""<defs>
<radialGradient id="sky" cx="50%" cy="35%" r="75%"><stop offset="0" stop-color="{C.sky_top}"/><stop offset="1" stop-color="{C.sky}"/></radialGradient>
<radialGradient id="nebV"><stop offset="0" stop-color="{C.violet}" stop-opacity=".30"/><stop offset="1" stop-color="{C.violet}" stop-opacity="0"/></radialGradient>
<radialGradient id="nebT"><stop offset="0" stop-color="{C.teal}" stop-opacity=".16"/><stop offset="1" stop-color="{C.teal}" stop-opacity="0"/></radialGradient>
<radialGradient id="nebR"><stop offset="0" stop-color="{C.rose}" stop-opacity=".16"/><stop offset="1" stop-color="{C.rose}" stop-opacity="0"/></radialGradient>
<radialGradient id="halo"><stop offset="0" stop-color="{C.violet}" stop-opacity=".20"/><stop offset=".7" stop-color="{C.violet}" stop-opacity=".07"/><stop offset="1" stop-color="{C.violet}" stop-opacity="0"/></radialGradient>
<radialGradient id="disk"><stop offset="0" stop-color="{C.violet_hi}" stop-opacity=".35"/><stop offset="1" stop-color="{C.violet_hi}" stop-opacity="0"/></radialGradient>
<radialGradient id="core"><stop offset="0" stop-color="#FFFFFF"/><stop offset=".35" stop-color="{C.glow}" stop-opacity=".9"/><stop offset="1" stop-color="{C.glow}" stop-opacity="0"/></radialGradient>
<radialGradient id="qso"><stop offset="0" stop-color="{C.glow}" stop-opacity=".95"/><stop offset="1" stop-color="{C.glow}" stop-opacity="0"/></radialGradient>
<linearGradient id="tail" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="104" y2="-36"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></linearGradient>
<linearGradient id="specfade" x1="0" x2="1"><stop offset="0" stop-color="{C.violet}"/><stop offset=".55" stop-color="{C.violet_hi}"/><stop offset="1" stop-color="{C.gold}"/></linearGradient>
</defs>"""

    nebulae = (
        '<g class="neb" style="animation-duration:34s"><circle cx="300" cy="120" r="260" fill="url(#nebV)"/></g>'
        '<g class="neb" style="animation-duration:46s;animation-delay:-12s"><circle cx="880" cy="230" r="300" fill="url(#nebT)"/></g>'
        '<g class="neb" style="animation-duration:40s;animation-delay:-20s"><circle cx="1040" cy="40" r="220" fill="url(#nebR)"/></g>'
    )
    shooting = []
    for x0, y0, dur, delay in ((1020, 40, 9, 1.5), (760, 20, 13, 6), (420, 60, 17, 10)):
        shooting.append(
            f'<g transform="translate({x0} {y0})"><g class="ss" style="animation-duration:{dur}s;animation-delay:{delay}s">'
            f'<line x1="0" y1="0" x2="104" y2="-36" stroke="url(#tail)" stroke-width="1.6" stroke-linecap="round"/>'
            f'<circle r="1.7" fill="#FFFFFF"/></g></g>'
        )
    sight = (
        f'<line x1="{qx}" y1="{qy}" x2="{px}" y2="{py}" stroke="{C.glow}" stroke-opacity=".45" stroke-width="1.2"/>'
        f'<circle cx="{qx}" cy="{qy}" r="30" fill="url(#qso)" class="pulse"/>'
        f'<path d="M{qx - 18},{qy} H{qx + 18} M{qx},{qy - 18} V{qy + 18}" stroke="{C.glow}" stroke-width=".9" stroke-opacity=".8"/>'
        f'<circle cx="{qx}" cy="{qy}" r="3.4" fill="#FFFFFF"/>'
        + "".join(f'<circle class="ph" cx="{qx}" cy="{qy}" r="2.8" fill="{C.glow}" style="animation-delay:{i * 1.25:.2f}s"/>' for i in range(3))
        + f'<path d="M{px},{py - 10} L{px + 10},{py + 8} L{px - 10},{py + 8} Z" fill="{C.sky}" stroke="{C.ink}" stroke-width="1.3" stroke-linejoin="round"/>'
    )
    spectrum = (
        f'<line x1="{SX0}" y1="{SY_BASE + 6}" x2="{SX1}" y2="{SY_BASE + 6}" stroke="{C.faint}"/>'
        f'<path d="{model}" fill="none" stroke="{C.muted}" stroke-opacity=".5" stroke-dasharray="4 5"/>'
        f'<path class="spec" d="{spec}" pathLength="1000" fill="none" stroke="url(#specfade)" stroke-width="1.6" stroke-linejoin="round"/>'
    )
    css = (
        star_css
        + "@keyframes neb{from{transform:translate(0,0)}to{transform:translate(46px,-16px)}}"
        ".neb{animation:neb 40s ease-in-out infinite alternate}"
        "@keyframes spin{to{transform:rotate(-360deg)}}.spin{animation:spin 110s linear infinite}"
        "@keyframes ss{0%{transform:translate(0,0);opacity:0}1.5%{opacity:1}9%{transform:translate(-300px,104px);opacity:0}"
        "100%{transform:translate(-300px,104px);opacity:0}}.ss{opacity:0;animation:ss 11s ease-in infinite}"
        "@keyframes pulse{0%,100%{opacity:.95}50%{opacity:.55}}.pulse{animation:pulse 2.6s ease-in-out infinite}"
        "@keyframes ph{0%{transform:translate(0,0);opacity:0}5%{opacity:1}"
        f"{f_in * 100:.1f}%{{opacity:1}}{f_out * 100:.1f}%{{opacity:.3}}96%{{opacity:.3}}"
        f"100%{{transform:translate({dx:.1f}px,{dy:.1f}px);opacity:0}}}}"
        ".ph{opacity:0;animation:ph 3.8s linear infinite}"
        "@keyframes spec{0%{stroke-dashoffset:1000;opacity:1}42%{stroke-dashoffset:0;opacity:1}"
        "84%{stroke-dashoffset:0;opacity:1}94%{stroke-dashoffset:0;opacity:0}100%{stroke-dashoffset:1000;opacity:0}}"
        ".spec{stroke-dasharray:1000;stroke-dashoffset:0;animation:spec 14s linear infinite}"
    )
    body = (
        defs
        + f'<rect width="{HERO_W}" height="{HERO_H}" rx="22" fill="url(#sky)"/>'
        + f'<clipPath id="clip"><rect width="{HERO_W}" height="{HERO_H}" rx="22"/></clipPath>'
        + f'<g clip-path="url(#clip)">{nebulae}</g>'
        + stars + "".join(shooting) + spiral_galaxy(rng) + sight + spectrum
    )
    return document(HERO_W, HERO_H, body, None, css,
                    title="Animated space scene: light from a quasar crosses a spinning galaxy's halo and becomes a spectrum")


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
    if kind == "email":
        return (f'<g fill="none" stroke="{s}" stroke-width="1.6" stroke-linejoin="round">'
                f'<rect x="-10" y="-7" width="20" height="14" rx="2"/><path d="M-10,-6 L0,2 L10,-6"/></g>')
    icon = icon_inner({"scholar": "googlescholar", "linkedin": "linkedin-plain"}[kind], 20)
    return f'<g fill="{s}">{icon}</g>'


CHIPS = [("website", "website"), ("scholar", "scholar"), ("linkedin", "linkedin"), ("email", "email")]


def chip(kind: str, label: str) -> str:
    fonts = Fonts()
    size = 20
    w = 56 + fonts.width("rm", label, size) + 20
    h = 44
    body = (
        f'<rect x="1" y="1" width="{w - 2:.1f}" height="{h - 2}" rx="21" fill="{C.panel}" stroke="#2A3466" stroke-width="1.2"/>'
        f'<g transform="translate(30 22)">{chip_icon(kind)}</g>'
        + fonts.text(52, 29, label, "rm", size, C.ink)
    )
    return document(round(w), h, body, fonts, title=label)


# --------------------------------------------------------------------------- tool orbits

TOOLS_W, TOOLS_H = 1200, 660
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


# --------------------------------------------------------------------------- footer


def footer() -> str:
    W, H = 1200, 230
    rng = random.Random(11)
    stars, star_css = starfield(rng, W, 150, 120, 5)
    ribbons = []
    for i, (color, amp, y0, dur) in enumerate(((C.teal, 18, 70, 26), (C.violet, 24, 95, 34), (C.rose, 14, 60, 42))):
        pts = []
        for x in range(0, 2 * W + 1, 20):
            y = y0 + amp * math.sin(2 * math.pi * x / 600 + i) + 8 * math.sin(2 * math.pi * x / 240 + 2 * i)
            pts.append(f"{x},{y:.1f}")
        d = "M" + " L".join(pts) + f" L{2 * W},{y0 + 90} L0,{y0 + 90} Z"
        ribbons.append(f'<g class="rib" style="animation-duration:{dur}s"><path d="{d}" fill="url(#a{i})" filter="url(#blur)"/></g>')
    # Treeline and an observatory dome.
    trees = []
    x = 0.0
    while x < W:
        h = rng.uniform(14, 34)
        trees.append(f"M{x:.0f},{H} L{x + 9:.0f},{H - h:.0f} L{x + 18:.0f},{H}")
        x += rng.uniform(10, 18)
    dome_x = 930
    body = (
        "<defs>"
        f'<linearGradient id="fsky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{C.sky}"/>'
        f'<stop offset="1" stop-color="{C.sky_top}"/></linearGradient>'
        + "".join(f'<linearGradient id="a{i}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{c}" stop-opacity=".55"/>'
                  f'<stop offset="1" stop-color="{c}" stop-opacity="0"/></linearGradient>'
                  for i, c in enumerate((C.teal, C.violet, C.rose)))
        + '<filter id="blur" x="-5%" y="-50%" width="110%" height="200%"><feGaussianBlur stdDeviation="7"/></filter>'
        "</defs>"
        f'<rect width="{W}" height="{H}" rx="22" fill="url(#fsky)"/>'
        + stars + "".join(ribbons)
        + f'<path d="M0,{H - 18} Q300,{H - 46} 600,{H - 22} T1200,{H - 30} V{H} H0 Z" fill="#080C24"/>'
        + f'<path d="{" ".join(trees)}" fill="#060918"/>'
        + f'<g transform="translate({dome_x} {H - 40})"><rect x="-30" y="0" width="60" height="30" fill="#060918"/>'
        f'<path d="M-34,2 A34,34 0 0 1 34,2 Z" fill="#0A0F2C"/><rect class="slit" x="-5" y="-30" width="10" height="30" fill="{C.glow}" opacity=".5"/></g>'
    )
    css = (star_css
           + "@keyframes rib{to{transform:translateX(-600px)}}.rib{animation:rib 30s linear infinite}"
           "@keyframes slit{0%,100%{opacity:.25}50%{opacity:.7}}.slit{animation:slit 4s ease-in-out infinite}")
    clip = f'<clipPath id="clip"><rect width="{W}" height="{H}" rx="22"/></clipPath>'
    return document(W, H, f'{clip}<g clip-path="url(#clip)">{body}</g>', None, css,
                    title="Aurora over an observatory")


def main() -> None:
    outputs = {
        ASSETS / "hero.svg": hero(),
        ASSETS / "typing.svg": typing(),
        ASSETS / "tools.svg": tools(),
        ASSETS / "footer.svg": footer(),
    }
    for kind, label in CHIPS:
        outputs[ASSETS / "chips" / f"{kind}.svg"] = chip(kind, label)
    for path, content in outputs.items():
        if write(path, content):
            print(f"wrote {path.relative_to(ROOT)} ({len(content) / 1000:.0f} kB)")


if __name__ == "__main__":
    main()
