"""Build the static (rarely changing) SVGs: the hero banner and the link buttons.

The hero is the profile's one orchestrated moment: light from a background
quasar crosses a galaxy's circumgalactic medium and lands in a spectrograph,
and the spectrum draws itself with the absorption lines labelled the way a
paper labels them.

    python scripts/build_static.py
"""

from __future__ import annotations

import math
import random

from svgkit import ROOT, THEMES, Fonts, Theme, document, esc, write

ASSETS = ROOT / "assets"

W, H = 1200, 462

# Typewriter phrases, completing "I study ...". Small caps carry ionisation
# stages (O vi, Mg ii), as in the literature.
PHRASES = [
    [("rm", "the gas between galaxies.")],
    [("rm", "quasar absorption lines.")],
    [("rm", "O "), ("sc", "vi"), ("rm", " in the gas of galaxy groups.")],
    [("rm", "how the outer halo of a galaxy rotates.")],
    [("rm", "mock spectra from TNG50 and SIMBA.")],
    [("rm", "Bayesian classification of supernovae.")],
]

# Rest-frame lines (Å). Emission: (centre, amplitude, sigma). Absorption
# doublets from a single intervening absorber: (label, [(centre, tau)], sigma).
EMISSION = [(1025.7, 0.3, 9), (1215.7, 1.25, 16), (1240.0, 0.35, 9), (1400.0, 0.2, 16),
            (1549.0, 0.62, 20), (1909.0, 0.3, 26), (2798.0, 0.42, 34)]
ABSORBERS = [
    ([("rm", "O "), ("sc", "vi")], [(1031.9, 1.6), (1037.6, 1.0)], 1.1),
    ([("rm", "Si "), ("sc", "iv")], [(1393.8, 1.1), (1402.8, 0.7)], 1.1),
    ([("rm", "C "), ("sc", "iv")], [(1548.2, 1.8), (1550.8, 1.2)], 0.9),
    ([("rm", "Mg "), ("sc", "ii")], [(2796.4, 2.2), (2803.5, 1.7)], 1.6),
]
LMIN, LMAX = 1000.0, 2900.0

# Spectrum panel geometry.
SX0, SX1 = 64, 1136
SY_TOP, SY_BASE = 318, 420

QSO = (1116.0, 70.0)
GAL = (880.0, 128.0)
HALO_R = 88.0
SLIT = (762.0, 262.0)

DRAW_DELAY, DRAW_DUR = 0.8, 5.2


def wl_to_x(lam: float) -> float:
    f = (math.log(lam) - math.log(LMIN)) / (math.log(LMAX) - math.log(LMIN))
    return SX0 + f * (SX1 - SX0)


def synth_spectrum() -> tuple[list[tuple[float, float]], list[tuple[float, float]]]:
    """A quasar spectrum: power-law continuum, broad emission, Ly𝛼 forest, metal doublets.

    Returns the observed spectrum and the unabsorbed model, both in panel pixels.
    """
    rng = random.Random(1216)
    n = 1500
    lams = [LMIN * (LMAX / LMIN) ** (i / (n - 1)) for i in range(n)]
    forest = [(rng.uniform(1005, 1212), rng.uniform(0.2, 1.5), rng.uniform(1.0, 2.0)) for _ in range(48)]
    flux, model = [], []
    for lam in lams:
        f = (lam / 1450.0) ** -0.55
        for c, a, s in EMISSION:
            f += a * math.exp(-0.5 * ((lam - c) / s) ** 2)
        model.append(f)
        tau = 0.0
        for c, t, s in forest:
            tau += t * math.exp(-0.5 * ((lam - c) / s) ** 2)
        for _, comps, s in ABSORBERS:
            for c, t in comps:
                tau += t * math.exp(-0.5 * ((lam - c) / s) ** 2)
        f *= math.exp(-tau)
        f += rng.gauss(0, 0.018)
        flux.append(max(f, 0.0))
    fmax = max(model)
    to_px = lambda fs: [(wl_to_x(lam), SY_BASE - f / fmax * (SY_BASE - SY_TOP)) for lam, f in zip(lams, fs)]  # noqa: E731
    return to_px(flux), to_px(model)


def path_fraction(points: list[tuple[float, float]], x: float) -> float:
    """Fraction of the polyline's length drawn by the time it reaches x."""
    total = 0.0
    upto = None
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        total += math.hypot(x1 - x0, y1 - y0)
        if upto is None and x1 >= x:
            upto = total
    return (upto or total) / total


def starfield(theme: Theme, rng: random.Random) -> tuple[str, str]:
    stars, css = [], []
    count = 150 if theme.name == "dark" else 80
    for i in range(count):
        x, y = rng.uniform(0, W), rng.uniform(0, 330)
        # Keep the name block and the galaxy readable.
        if 40 < x < 760 and 70 < y < 290 and rng.random() < 0.7:
            continue
        r = rng.choice([0.5, 0.6, 0.7, 0.8, 1.0, 1.3]) if theme.name == "dark" else rng.choice([0.5, 0.6, 0.8])
        op = rng.uniform(0.35, 0.95) if theme.name == "dark" else rng.uniform(0.25, 0.55)
        fill = theme.ink if theme.name == "light" else rng.choice([theme.ink, theme.ink, theme.glow, "#B9C4FF"])
        cls = ""
        if theme.name == "dark" and i % 9 == 0:
            cls = f' class="tw" style="animation-duration:{rng.uniform(2.6, 5.5):.2f}s;animation-delay:{rng.uniform(0, 4):.2f}s"'
        stars.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{fill}" opacity="{op:.2f}"{cls}/>')
    css.append("@keyframes tw{0%,100%{opacity:.95}50%{opacity:.15}}.tw{animation:tw 4s ease-in-out infinite}")
    return "".join(stars), "".join(css)


def galaxy(theme: Theme) -> str:
    gx, gy = GAL
    halo_fill = "#8B7BF5" if theme.name == "dark" else theme.accent
    core = theme.glow
    disk = "#C9CFFF" if theme.name == "dark" else theme.ink
    return f"""
<defs>
  <radialGradient id="halo" cx="50%" cy="50%" r="50%">
    <stop offset="0" stop-color="{halo_fill}" stop-opacity="{0.16 if theme.name == 'dark' else 0.10}"/>
    <stop offset="0.7" stop-color="{halo_fill}" stop-opacity="{0.06 if theme.name == 'dark' else 0.04}"/>
    <stop offset="1" stop-color="{halo_fill}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="disk" cx="50%" cy="50%" r="50%">
    <stop offset="0" stop-color="{core}" stop-opacity="1"/>
    <stop offset="0.25" stop-color="{disk}" stop-opacity="0.75"/>
    <stop offset="1" stop-color="{disk}" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="qso" cx="50%" cy="50%" r="50%">
    <stop offset="0" stop-color="{core}" stop-opacity="0.9"/>
    <stop offset="1" stop-color="{core}" stop-opacity="0"/>
  </radialGradient>
</defs>
<circle cx="{gx}" cy="{gy}" r="{HALO_R}" fill="url(#halo)"/>
<circle cx="{gx}" cy="{gy}" r="{HALO_R}" fill="none" stroke="{theme.muted}" stroke-opacity="0.55"
        stroke-width="1" stroke-dasharray="2 5"/>
<g transform="translate({gx} {gy}) rotate(-17)">
  <ellipse rx="74" ry="17" fill="url(#disk)"/>
  <path d="M-8,-3 C 20,-14 52,-10 66,2" fill="none" stroke="{disk}" stroke-opacity="0.35" stroke-width="1.4"/>
  <path d="M8,3 C -20,14 -52,10 -66,-2" fill="none" stroke="{disk}" stroke-opacity="0.35" stroke-width="1.4"/>
  <ellipse rx="9" ry="4.5" fill="{core}" opacity="0.95"/>
</g>"""


def sightline(theme: Theme, fonts: Fonts) -> tuple[str, str]:
    (qx, qy), (sx, sy), (gx, gy) = QSO, SLIT, GAL
    dx, dy = sx - qx, sy - qy
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    # Impact parameter: perpendicular from galaxy centre to the sightline.
    t = (gx - qx) * ux + (gy - qy) * uy
    fx, fy = qx + t * ux, qy + t * uy
    # Where the sightline enters/leaves the halo, as fractions of its length.
    b = math.hypot(gx - fx, gy - fy)
    half = math.sqrt(max(HALO_R**2 - b**2, 0))
    f_in, f_out = (t - half) / length, (t + half) / length

    line = theme.glow if theme.name == "dark" else theme.gold
    parts = [
        f'<line x1="{qx}" y1="{qy}" x2="{sx}" y2="{sy}" stroke="{line}" stroke-opacity="0.55" stroke-width="1.2"/>',
        f'<line x1="{gx}" y1="{gy}" x2="{fx:.1f}" y2="{fy:.1f}" stroke="{theme.muted}" stroke-width="1" stroke-dasharray="3 3"/>',
        fonts.text((gx + fx) / 2 + 9, (gy + fy) / 2 + 4, "b", "it", 17, theme.muted),
        # Quasar: core, glow, diffraction spikes.
        f'<circle cx="{qx}" cy="{qy}" r="24" fill="url(#qso)" opacity="{0.9 if theme.name == "dark" else 0.35}"/>',
        f'<path d="M{qx - 15},{qy} H{qx + 15} M{qx},{qy - 15} V{qy + 15}" stroke="{theme.glow}" stroke-width="0.9" stroke-opacity="0.8"/>',
        f'<circle cx="{qx}" cy="{qy}" r="3.2" fill="{theme.glow if theme.name == "dark" else theme.gold}"/>',
        # A prism disperses the light into the spectrum below.
        f'<path d="M{sx},{sy - 9} L{sx + 9},{sy + 8} L{sx - 9},{sy + 8} Z" fill="{theme.sky}" stroke="{theme.ink}" stroke-width="1.3" stroke-linejoin="round"/>',
    ]
    parts.append(fonts.text(qx - 30, qy - 26, "background quasar", "it", 16, theme.muted, "end"))
    parts.append(fonts.text(gx - 38, gy - HALO_R - 12, "circumgalactic medium", "it", 16, theme.muted, "middle"))

    # Photon packets travel the sightline; inside the halo some light is absorbed.
    pulse_fill = theme.glow if theme.name == "dark" else theme.gold
    for i in range(3):
        parts.append(
            f'<circle class="ph" cx="{qx}" cy="{qy}" r="2.6" fill="{pulse_fill}" '
            f'style="animation-delay:{i * 1.3:.1f}s"/>'
        )
    css = (
        "@keyframes ph{"
        f"0%{{transform:translate(0,0);opacity:0}}"
        f"6%{{opacity:1}}"
        f"{f_in * 100:.1f}%{{opacity:1}}"
        f"{f_out * 100:.1f}%{{opacity:.3}}"
        f"96%{{opacity:.3}}"
        f"100%{{transform:translate({dx:.1f}px,{dy:.1f}px);opacity:0}}"
        "}"
        ".ph{opacity:0;animation:ph 3.9s linear infinite}"
    )
    return "".join(parts), css


def spectrum(theme: Theme, fonts: Fonts) -> tuple[str, str]:
    pts, model = synth_spectrum()
    d = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    dm = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in model[::6])
    parts = [
        f'<line x1="{SX0}" y1="{SY_BASE + 6}" x2="{SX1}" y2="{SY_BASE + 6}" stroke="{theme.faint}" stroke-width="1"/>',
    ]
    for lam in (1000, 1200, 1500, 2000):
        x = wl_to_x(lam)
        parts.append(f'<line x1="{x:.1f}" y1="{SY_BASE + 6}" x2="{x:.1f}" y2="{SY_BASE + 12}" stroke="{theme.muted}" stroke-width="1"/>')
        parts.append(fonts.text(x, SY_BASE + 29, f"{lam:,}".replace(",", " "), "rm", 14, theme.muted, "middle"))
    parts.append(
        fonts.rich(SX1, SY_BASE + 29, [("rm", "rest wavelength "), ("math", "\U0001D706"), ("rm", " (Å)")], 14, theme.muted, "end")
    )
    # The continuum fit: what the quasar would look like with no gas in the way.
    parts.append(
        f'<path d="{dm}" fill="none" stroke="{theme.muted}" stroke-opacity="0.7" stroke-width="1" stroke-dasharray="4 4"/>'
    )
    parts.append(
        f'<path class="spec" d="{d}" pathLength="1000" fill="none" stroke="{theme.accent}" '
        f'stroke-width="1.5" stroke-linejoin="round"/>'
    )

    css = [
        "@keyframes draw{from{stroke-dashoffset:1000}to{stroke-dashoffset:0}}",
        f".spec{{stroke-dasharray:1000;stroke-dashoffset:0;animation:draw {DRAW_DUR}s linear {DRAW_DELAY}s both}}",
        "@keyframes lid{from{opacity:0;transform:translateY(5px)}to{opacity:1;transform:none}}",
        ".lid{animation:lid .6s ease-out both}",
    ]

    # Line IDs: ticks above each doublet component, joined, label on top.
    def local_top(lam_lo: float, lam_hi: float) -> float:
        xs = (wl_to_x(lam_lo), wl_to_x(lam_hi))
        return min(y for x, y in pts if xs[0] <= x <= xs[1])

    for label, comps, _ in ABSORBERS:
        lo, hi = comps[0][0], comps[-1][0]
        top = local_top(lo - 25, hi + 25) - 8
        xs = [wl_to_x(c) for c, _ in comps]
        delay = DRAW_DELAY + DRAW_DUR * path_fraction(pts, xs[-1])
        g = [f'<g class="lid" style="animation-delay:{delay:.2f}s">']
        for x in xs:
            g.append(f'<line x1="{x:.1f}" y1="{top:.1f}" x2="{x:.1f}" y2="{top - 9:.1f}" stroke="{theme.ink}" stroke-width="1"/>')
        g.append(f'<line x1="{xs[0]:.1f}" y1="{top - 9:.1f}" x2="{xs[-1]:.1f}" y2="{top - 9:.1f}" stroke="{theme.ink}" stroke-width="1"/>')
        g.append(fonts.rich(sum(xs) / len(xs), top - 16, label, 16, theme.ink, "middle"))
        g.append("</g>")
        parts.append("".join(g))

    # The Ly𝛼 forest gets one bracket: the lines are too many to tick.
    fx0, fx1 = wl_to_x(1010), wl_to_x(1205)
    delay = DRAW_DELAY + DRAW_DUR * path_fraction(pts, fx1)
    parts.append(
        f'<g class="lid" style="animation-delay:{delay:.2f}s">'
        + fonts.rich((fx0 + fx1) / 2, SY_TOP - 6, [("rm", "Ly"), ("math", "\U0001D6FC"), ("rm", " forest")], 16, theme.ink, "middle")
        + f'<path d="M{fx0:.1f},{SY_TOP + 4} V{SY_TOP - 1} H{fx1:.1f} V{SY_TOP + 4}" fill="none" stroke="{theme.ink}" stroke-width="1"/>'
        + "</g>"
    )
    return "".join(parts), "".join(css)


def typewriter(theme: Theme, fonts: Fonts, x0: float, y: float, size: float) -> tuple[str, str]:
    prefix = [("rm", "I study ")]
    px = x0 + fonts.rich_width(prefix, size)
    slot, type_dt, erase_dt, lead = 5.6, 0.05, 0.022, 0.35
    total = slot * len(PHRASES)
    pct = lambda t: f"{t / total * 100:.4f}%"  # noqa: E731

    body = [fonts.rich(x0, y, prefix, size, theme.ink, extra='class="tw-line"')]
    css = [
        ".tc{visibility:hidden;animation-timing-function:step-end;animation-iteration-count:infinite;"
        f"animation-duration:{total}s}}.tc.on{{visibility:visible}}"
    ]
    caret_steps: list[tuple[float, float]] = []
    kf_id = 0
    for i, segs in enumerate(PHRASES):
        chars = [(face, ch) for face, text in segs for ch in text]
        start = i * slot + lead
        end = (i + 1) * slot - 0.45
        spans = []
        offset = 0.0
        for k, (face, ch) in enumerate(chars):
            t_on = start + k * type_dt
            t_off = end - k * erase_dt  # backspace: last character goes first
            css.append(
                f"@keyframes k{kf_id}{{0%{{visibility:hidden}}{pct(t_on)}{{visibility:visible}}"
                f"{pct(t_off)}{{visibility:hidden}}100%{{visibility:hidden}}}}"
            )
            fonts.use(face, ch)
            fam = esc(fonts.family(face))
            cls = "tc on" if i == 0 else "tc"
            spans.append(
                f'<tspan class="{cls}" style="animation-name:k{kf_id}" font-family="{fam}">{esc(ch)}</tspan>'
            )
            offset += fonts.width(face, ch, size)
            caret_steps.append((t_on, offset))
            caret_steps.append((t_off, offset - fonts.width(face, ch, size)))
            kf_id += 1
        body.append(
            f'<text class="tw-line" x="{px:.1f}" y="{y:.1f}" font-size="{size}" fill="{theme.ink}">{"".join(spans)}</text>'
        )

    first_width = fonts.rich_width(PHRASES[0], size)
    caret_steps.sort()
    stops = ["0%{transform:translateX(0px)}"]
    stops += [f"{pct(t)}{{transform:translateX({x:.1f}px)}}" for t, x in caret_steps]
    css.append(f"@keyframes caret{{{''.join(stops)}}}")
    css.append(
        f".cm{{transform:translateX({first_width:.1f}px);animation:caret {total}s step-end infinite}}"
        "@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}.cb{animation:blink 1.05s step-end infinite}"
    )
    body.append(
        f'<g class="cm"><rect class="cb" x="{px + 2:.1f}" y="{y - size * 0.78:.1f}" width="2" '
        f'height="{size * 0.95:.1f}" fill="{theme.accent}"/></g>'
    )
    return "".join(body), "".join(css)


def hero(theme: Theme) -> str:
    fonts = Fonts()
    rng = random.Random(42)
    stars, star_css = starfield(theme, rng)
    sight, sight_css = sightline(theme, fonts)
    spec, spec_css = spectrum(theme, fonts)
    tw, tw_css = typewriter(theme, fonts, 64, 268, 28)

    body = [
        f'<rect width="{W}" height="{H}" rx="18" fill="{theme.sky}"/>',
        stars,
        galaxy(theme),
        sight,
        fonts.text(62, 134, "Tanmay Singh", "dunh", 82, theme.ink),
        fonts.text(64, 180, "School of Earth and Space Exploration, Arizona State University", "it", 21, theme.muted),
        fonts.text(64, 211, "Ph.D. candidate in astrophysics, working with Sanchayeeta Borthakur", "rm", 19, theme.muted),
        tw,
        spec,
    ]
    css = (
        ".tw-line{font-kerning:none;font-variant-ligatures:none}"
        + star_css + sight_css + spec_css + tw_css
        + "@media (prefers-reduced-motion:reduce){*{animation:none!important}}"
    )
    return document(W, H, "".join(body), fonts, css, title="Tanmay Singh: astrophysics Ph.D. candidate at Arizona State University")


# Link buttons, drawn as hyperref link boxes: the coloured rectangle LaTeX puts
# around a URL in a PDF.
LINKS = {
    "website": "Website",
    "scholar": "Google Scholar",
    "linkedin": "LinkedIn",
    "email": "Email",
    "cv": "CV (PDF)",
    "chess": "Chess.com",
}


def link_button(label: str, theme: Theme) -> str:
    fonts = Fonts()
    size = 18
    w = fonts.width("rm", label, size) + 28
    h = 36
    body = (
        f'<rect x="1" y="1" width="{w - 2:.1f}" height="{h - 2}" fill="{theme.surface}" stroke="{theme.link}" stroke-width="1.2"/>'
        + fonts.text(w / 2, 24, label, "rm", size, theme.ink, "middle")
    )
    return document(round(w), h, body, fonts, "text{font-kerning:none;font-variant-ligatures:none}", title=label)


def main() -> None:
    for theme in THEMES:
        if write(ASSETS / f"hero-{theme.name}.svg", hero(theme)):
            print(f"wrote hero-{theme.name}.svg")
        for key, label in LINKS.items():
            write(ASSETS / "links" / f"{key}-{theme.name}.svg", link_button(label, theme))


if __name__ == "__main__":
    main()
