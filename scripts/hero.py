"""The hero: a quasar's light crosses a galaxy's halo and becomes a spectrum.

A new sky every day, drawn from the day's seed: the nebulae and the Milky Way
band, the galaxy (arms, pitch, bar, tilt, spin), where the quasar sits and
its redshift, how close the sightline passes the galaxy, and therefore the
absorption lines the spectrum shows. The physics is real: emission lines sit
at the quasar's redshift, the forest lies blueward of its Lyman-alpha line,
and the Mg II, Fe II and C IV lines sit at the galaxy's redshift.

Soft light (nebulae, faint stars, the galactic disk) is rendered as raster
and embedded in the SVG; everything that moves or must stay crisp is vector.
"""

from __future__ import annotations

import math
import random

import numpy as np

import skyart as sa
from svgkit import C, Fonts, document, esc

W, H = 1200, 420
PRISM_Y = 292.0
SX0, SX1, SY_TOP, SY_BASE = 60.0, 1140.0, 306.0, 378.0
LAM0, LAM1 = 3600.0, 9200.0
CYCLE = 14.0

# Rest wavelengths (angstroms).
QSO_EMISSION = [(1025.7, 0.35, 3200), (1215.7, 1.5, 3000), (1240.8, 0.4, 2600), (1400.0, 0.3, 3500),
                (1549.1, 1.05, 3400), (1908.7, 0.6, 4000), (2798.0, 0.7, 3800)]
ABSORBER = {
    "Mg II": [(2796.35, 1.0), (2803.53, 0.8)],
    "Fe II": [(2600.17, 0.6), (2586.65, 0.35), (2382.77, 0.55), (2344.21, 0.4)],
    "C IV": [(1548.20, 0.9), (1550.78, 0.65)],
    "Si IV": [(1393.76, 0.6), (1402.77, 0.4)],
    "Mg I": [(2852.96, 0.45)],
    "Ca II": [(3934.78, 0.75), (3969.59, 0.55)],
}


def wl_x(lam: float) -> float:
    return SX0 + (lam - LAM0) / (LAM1 - LAM0) * (SX1 - SX0)


# --------------------------------------------------------------------------- geometry


def layout(r: random.Random) -> dict:
    """Pick the galaxy, the quasar and a sightline that crosses the halo but misses the disk."""
    for _ in range(500):
        gx, gy = r.uniform(400, 800), r.uniform(118, 168)
        halo = r.uniform(128, 150)
        disk = r.uniform(78, 96)
        right = r.random() < 0.5 if abs(gx - 600) < 80 else gx < 600
        qx = r.uniform(930, 1135) if right else r.uniform(65, 270)
        qy = r.uniform(64, 110)
        vx, vy = gx - qx, gy - qy
        d = math.hypot(vx, vy)
        b = r.uniform(disk * 0.75 + 10, halo * 0.72)
        if b >= d:
            continue
        theta = math.atan2(vy, vx) + r.choice((-1, 1)) * math.asin(b / d)
        if math.sin(theta) <= 0.2:
            continue
        t = (PRISM_Y - qy) / math.sin(theta)
        px = qx + t * math.cos(theta)
        if 110 < px < 1090 and abs(px - qx) > 380:
            return {"G": (gx, gy), "halo": halo, "disk": disk, "Q": (qx, qy), "P": (px, PRISM_Y), "b": b}
    raise RuntimeError("no sightline found")  # pragma: no cover - 500 tries never all fail


# --------------------------------------------------------------------------- raster layers


def sky_raster(rng: np.random.Generator, pad: int) -> str:
    """Nebulae, a Milky Way band and thousands of faint stars, as one JPEG."""
    w, h = W + 2 * pad, H + 2 * pad
    yy, xx = np.mgrid[0:h, 0:w].astype(float)
    img = np.zeros((h, w, 3))
    # Base: neutral near-black, a touch lighter in the middle.
    rad = np.hypot((xx - w * 0.5) / w, (yy - h * 0.38) / h)
    img += (sa.hex_rgb(C.sky_top) * 0.7)[None, None, :] * np.clip(1 - rad * 1.4, 0, 1)[..., None]
    img += sa.hex_rgb(C.sky)[None, None, :]

    # Milky Way: a soft band with dust lanes along its spine.
    ang = math.radians(rng.uniform(-32, 32))
    cx, cy = rng.uniform(0.25, 0.75) * w, rng.uniform(0.2, 0.55) * h
    dist = (xx - cx) * -math.sin(ang) + (yy - cy) * math.cos(ang)
    sigma = rng.uniform(55, 95)
    band = np.exp(-(dist / sigma) ** 2)
    texture = sa.fbm(rng, w, h, 140, 6)
    dust = sa.fbm(rng, w, h, 90, 5)
    lane = np.exp(-((dist - rng.uniform(-12, 12)) / (sigma * 0.35)) ** 2)
    band_light = band * (0.35 + 0.65 * texture) * (1 - 0.85 * lane * np.clip(dust * 1.6 - 0.35, 0, 1))
    band_color = sa.mix(sa.hex_rgb(C.glow), [1, 1, 1], 0.3)
    img += 0.13 * band_light[..., None] * band_color

    # Two or three nebulae in the palette's colours, each patchy and wispy.
    hues = [C.violet, C.rose, C.teal, C.gold, C.violet_hi]
    rng.shuffle(hues)
    for color in hues[: rng.integers(2, 4)]:
        nx, ny = rng.uniform(0.05, 0.95) * w, rng.uniform(0.0, 0.6) * h
        rx, ry = rng.uniform(180, 380), rng.uniform(90, 200)
        blob = np.exp(-(((xx - nx) / rx) ** 2 + ((yy - ny) / ry) ** 2))
        wisps = sa.fbm(rng, w, h, rng.uniform(70, 160), 6) ** 2.2
        img += rng.uniform(0.16, 0.28) * (blob * (0.12 + 2.0 * wisps))[..., None] * sa.hex_rgb(color) ** 1.6

    # Faint stars, denser in the band.
    n = 5200
    sx, sy = rng.uniform(0, w, n), rng.uniform(0, h, n)
    keep = rng.random(n) < 0.25 + 0.75 * np.exp(-((((sx - cx) * -math.sin(ang) + (sy - cy) * math.cos(ang)) / (sigma * 1.3)) ** 2))
    sx, sy = sx[keep], sy[keep]
    temps = rng.choice([3400, 4500, 5800, 7500, 10000, 16000], len(sx), p=[.2, .25, .22, .15, .12, .06])
    flux = rng.pareto(2.2, len(sx)) * 0.12 + 0.03
    stars = np.zeros_like(img)
    sa.splat(stars, sx, sy, sa.star_color(temps) * flux[:, None])
    img += sa.bloom(stars, (0.6, 2.0), (0.6, 0.15))

    # Keep the spectrum's strip quiet so the line reads.
    fade = 1 - 0.6 * np.clip((yy - (PRISM_Y + pad - 70)) / 130, 0, 1) ** 1.5
    img *= fade[..., None]
    return sa.data_uri(sa.to_image(sa.tonemap(img, 1.35)), "JPEG", 82)


def galaxy_raster(rng: np.random.Generator, size: int) -> tuple[str, dict]:
    """A face-on spiral (rotated and tilted in the SVG), as a WebP with alpha."""
    arms = int(rng.choice([2, 2, 3, 4]))
    pitch = math.radians(rng.uniform(11, 24))
    barred = rng.random() < 0.4
    s = size / 2.0
    img = np.zeros((size, size, 3))
    scale_r = s * 0.5  # disk scale length in pixels

    def put(x, y, rgb):
        sa.splat(img, x + s, y + s, rgb)

    # Smooth old disk.
    n = 22000
    r = rng.gamma(2.0, scale_r * 0.4, n)
    phi = rng.uniform(0, 2 * np.pi, n)
    put(r * np.cos(phi), r * np.sin(phi), sa.star_color(rng.uniform(4800, 6500, n)) * 0.05)

    # Arms: logarithmic spirals with young blue light and pink star-forming knots.
    n = 30000
    k = rng.integers(0, arms, n)
    r = np.clip(rng.gamma(2.6, scale_r * 0.42, n), s * 0.1, s * 0.97)
    theta = np.log(r / (s * 0.12)) / math.tan(pitch) + 2 * np.pi * k / arms
    spread = 0.09 + 0.16 * (r / s)
    ang = theta + rng.normal(0, spread)
    put(r * np.cos(ang), r * np.sin(ang), sa.star_color(rng.uniform(8000, 22000, n)) * 0.11)
    knots = 140
    kk = rng.integers(0, arms, knots)
    kr = np.clip(rng.gamma(3.0, scale_r * 0.42, knots), s * 0.2, s * 0.92)
    kt = np.log(kr / (s * 0.12)) / math.tan(pitch) + 2 * np.pi * kk / arms + rng.normal(0, 0.08, knots)
    for x, y in zip(kr * np.cos(kt), kr * np.sin(kt)):
        m = int(rng.integers(8, 30))
        put(x + rng.normal(0, 1.6, m), y + rng.normal(0, 1.6, m), sa.hex_rgb(C.rose) * 0.22)

    # Bulge and an optional bar.
    n = 9000
    put(rng.normal(0, s * 0.07, n), rng.normal(0, s * 0.07, n), sa.star_color(rng.uniform(3600, 4600, n)) * 0.11)
    if barred:
        n = 5000
        put(rng.normal(0, s * 0.16, n), rng.normal(0, s * 0.035, n), sa.star_color(rng.uniform(3800, 5000, n)) * 0.08)

    # Dust lanes trail the arms on their inner edge.
    yy, xx = np.mgrid[0:size, 0:size].astype(float) - s
    rr = np.hypot(xx, yy) + 1e-6
    tt = np.arctan2(yy, xx)
    arm_phase = (tt - np.log(np.maximum(rr, s * 0.12) / (s * 0.12)) / math.tan(pitch) + 0.28) * arms / (2 * np.pi)
    lane = np.cos(2 * np.pi * arm_phase) ** 8 * np.clip((rr - s * 0.1) / (s * 0.2), 0, 1) * np.exp(-rr / (s * 0.7))
    patch = sa.fbm(rng, size, size, 30, 5)
    img *= np.exp(-1.6 * lane * (0.4 + patch))[..., None]

    # Fold the whole disk gently toward the page's violet so it belongs here.
    img = img * 0.85 + img.mean(axis=-1, keepdims=True) * sa.hex_rgb(C.violet_hi) * 0.25
    lit = sa.tonemap(sa.bloom(img, (1.0, 3.5, 10.0), (0.8, 0.5, 0.35)), 1.5)
    edge = np.clip(1 - (rr / s - 0.82) / 0.18, 0, 1)
    alpha = np.clip(lit.max(axis=-1) * 1.5, 0, 1) * edge
    rgb = lit / np.maximum(alpha[..., None], 1e-3) * edge[..., None]
    uri = sa.data_uri(sa.to_image(np.clip(rgb, 0, 1), alpha), "WEBP", 82)
    return uri, {"arms": arms, "pitch": round(math.degrees(pitch)), "barred": bool(barred)}


# --------------------------------------------------------------------------- spectrum


def spectrum(r: random.Random, zq: float, zabs: float) -> tuple[str, str, list[tuple[float, str]]]:
    """Observed flux as a path, the area under it, and the absorption features to label."""
    n = 1300
    lams = [LAM0 + (LAM1 - LAM0) * i / (n - 1) for i in range(n)]
    lya = 1215.67 * (1 + zq)
    forest = []
    lam = LAM0 - 40
    while lam < lya:
        lam += r.expovariate(1 / 11.0)
        forest.append((lam, r.uniform(0.2, 2.6) * r.random() ** 0.4, r.uniform(2.2, 4.0)))
    metals = []
    for ion, lines in ABSORBER.items():
        strength = r.uniform(0.6, 1.5)
        for rest, f in lines:
            c = rest * (1 + zabs)
            if LAM0 + 40 < c < LAM1 - 40 and c > lya + 15:
                metals.append((ion, c, f * strength * 3.2, r.uniform(3.6, 5.2), f))
    flux = []
    for lam in lams:
        rest = lam / (1 + zq)
        f = (rest / 1450.0) ** -0.5
        for c, a, v in QSO_EMISSION:
            sig = c * v / 3e5
            f += a * math.exp(-0.5 * ((rest - c) / sig) ** 2)
        tau = sum(t * math.exp(-0.5 * ((lam - c) / s) ** 2) for c, t, s in forest if abs(lam - c) < 8 * s)
        tau += sum(t * math.exp(-0.5 * ((lam - c) / s) ** 2) for _, c, t, s, _ in metals if abs(lam - c) < 8 * s)
        flux.append(max(f * math.exp(-tau) + r.gauss(0, 0.02), 0.0))
    shown = [v**0.6 for v in flux]
    top = max(shown) * 1.02
    pts = [(wl_x(lam), SY_BASE - v / top * (SY_BASE - SY_TOP)) for lam, v in zip(lams, shown)]
    line = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = line + f" L{SX1},{SY_BASE} L{SX0},{SY_BASE} Z"
    # Name each ion once, under its strongest line (a doublet's pair sits within a pixel or two).
    strongest = {}
    for ion, c, _, _, f in metals:
        if f > strongest.get(ion, (0, 0))[1]:
            strongest[ion] = (c, f)
    return line, area, sorted((c, ion) for ion, (c, _) in strongest.items())


# --------------------------------------------------------------------------- assembly


def build(seed: int) -> tuple[str, dict]:
    r = random.Random(seed)
    rng = np.random.default_rng(seed)
    fonts = Fonts()
    geo = layout(r)
    (gx, gy), (qx, qy), (px, py) = geo["G"], geo["Q"], geo["P"]
    halo, disk = geo["halo"], geo["disk"]
    zq = round(r.uniform(2.05, 2.9), 2)
    zabs = round(r.uniform(0.6, min(zq - 0.3, 1.95)), 2)
    incl = r.uniform(38, 68)
    pa = r.uniform(-40, 40)
    spin_dir = r.choice(("-", ""))
    spin_period = r.uniform(110, 190)
    pad = 36

    sky_uri = sky_raster(rng, pad)
    gal_size = 440
    gal_uri, morph = galaxy_raster(rng, gal_size)
    spec_line, spec_area, marks = spectrum(r, zq, zabs)

    dx, dy = px - qx, py - qy
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    t_mid = (gx - qx) * ux + (gy - qy) * uy
    half = math.sqrt(max(halo**2 - geo["b"] ** 2, 0))
    f_in, f_out = (t_mid - half) / length, (t_mid + half) / length
    hx0, hy0 = qx + ux * (t_mid - half), qy + uy * (t_mid - half)
    hx1, hy1 = qx + ux * (t_mid + half), qy + uy * (t_mid + half)

    # Rainbow for the spectrum: the axis mapped onto the visible colours (for looks; the axis runs 360-920 nm).
    stops = "".join(
        f'<stop offset="{i / 24:.3f}" stop-color="{sa.rgb_hex(sa.wavelength_rgb(4050 + 2850 * i / 24))}"/>'
        for i in range(25)
    )
    defs = (
        "<defs>"
        f'<linearGradient id="rain" gradientUnits="userSpaceOnUse" x1="{SX0}" y1="0" x2="{SX1}" y2="0">{stops}</linearGradient>'
        f'<linearGradient id="rainfade" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".42"/>'
        f'<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        f'<mask id="under"><rect x="{SX0}" y="{SY_TOP - 4}" width="{SX1 - SX0}" height="{SY_BASE - SY_TOP + 4}" fill="url(#rainfade)"/></mask>'
        f'<radialGradient id="halo"><stop offset="0" stop-color="{C.violet}" stop-opacity=".16"/>'
        f'<stop offset=".65" stop-color="{C.violet}" stop-opacity=".06"/><stop offset="1" stop-color="{C.violet}" stop-opacity="0"/></radialGradient>'
        f'<radialGradient id="qso"><stop offset="0" stop-color="#FFFFFF" stop-opacity=".95"/><stop offset=".18" stop-color="{C.glow}" stop-opacity=".7"/>'
        f'<stop offset="1" stop-color="{C.glow}" stop-opacity="0"/></radialGradient>'
        f'<linearGradient id="spike" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/>'
        f'<stop offset=".5" stop-color="#fff" stop-opacity=".9"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>'
        f'<linearGradient id="tail" x1="0" x2="1"><stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset="1" stop-color="#fff"/></linearGradient>'
        f'<clipPath id="clip"><rect width="{W}" height="{H}" rx="22"/></clipPath>'
        "</defs>"
    )

    # Crisp foreground stars, a few with diffraction spikes.
    stars, css_tw = [], []
    for i in range(130):
        x, y = r.uniform(8, W - 8), r.uniform(8, PRISM_Y - 6 if r.random() < 0.9 else H - 8)
        if math.hypot(x - gx, (y - gy) * 1.6) < disk * 1.1 or math.hypot(x - qx, y - qy) < 30:
            continue
        temp = r.choice([3600, 4800, 5800, 7500, 11000, 20000])
        col = sa.rgb_hex(sa.mix(sa.star_color(temp), [1, 1, 1], 0.35))
        rad = r.choice([0.5, 0.6, 0.7, 0.8, 1.0, 1.2, 1.5])
        op = r.uniform(0.45, 1.0)
        attrs = ""
        if r.random() < 0.3:
            attrs = f' class="tw" style="animation-duration:{r.uniform(2.2, 6.5):.1f}s;animation-delay:{-r.uniform(0, 6):.1f}s"'
        stars.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rad}" fill="{col}" opacity="{op:.2f}"{attrs}/>')
    for i in range(r.randint(4, 7)):
        x, y = r.uniform(40, W - 40), r.uniform(20, PRISM_Y - 40)
        if math.hypot(x - gx, (y - gy) * 1.6) < halo or math.hypot(x - qx, y - qy) < 60:
            continue
        L = r.uniform(9, 17)
        col = sa.rgb_hex(sa.mix(sa.star_color(r.choice([4200, 6500, 12000])), [1, 1, 1], 0.4))
        stars.append(
            f'<g transform="translate({x:.1f} {y:.1f}) rotate({r.uniform(-12, 12):.0f})" class="tw" '
            f'style="animation-duration:{r.uniform(3, 7):.1f}s;animation-delay:{-r.uniform(0, 6):.1f}s">'
            f'<rect x="{-L:.1f}" y="-.35" width="{2 * L:.1f}" height=".7" fill="url(#spike)"/>'
            f'<rect x="{-L:.1f}" y="-.35" width="{2 * L:.1f}" height=".7" fill="url(#spike)" transform="rotate(90)"/>'
            f'<circle r="1.7" fill="{col}"/><circle r="4" fill="{col}" opacity=".18"/></g>'
        )

    # Shooting stars and, some nights, a satellite.
    extras, css_extra = [], []
    for i in range(r.randint(2, 4)):
        x0, y0 = r.uniform(150, W - 150), r.uniform(20, 150)
        ang = r.uniform(18, 38) * r.choice((-1, 1))
        L, dur, delay = r.uniform(240, 380), r.uniform(8, 19), r.uniform(0, 12)
        tx, ty = -L * math.cos(math.radians(ang)) * (1 if ang > 0 else -1), L * abs(math.sin(math.radians(ang)))
        rot = math.degrees(math.atan2(ty, tx)) + 180
        css_extra.append(f"@keyframes ss{i}{{0%{{transform:translate(0,0);opacity:0}}1.5%{{opacity:1}}"
                         f"{100 * 1.1 / dur:.1f}%{{transform:translate({tx:.0f}px,{ty:.0f}px);opacity:0}}"
                         f"100%{{transform:translate({tx:.0f}px,{ty:.0f}px);opacity:0}}}}")
        extras.append(
            f'<g transform="translate({x0:.0f} {y0:.0f})"><g style="opacity:0;animation:ss{i} {dur:.1f}s ease-in {delay:.1f}s infinite">'
            f'<g transform="rotate({rot:.1f})"><rect x="0" y="-.8" width="110" height="1.6" rx=".8" fill="url(#tail)" transform="scale(-1 1)"/>'
            f'<circle r="1.8" fill="#FFFFFF"/></g></g></g>'
        )
    if r.random() < 0.65:
        sy0, sy1 = r.uniform(30, 120), r.uniform(60, 200)
        dur = r.uniform(38, 60)
        css_extra.append(f"@keyframes sat{{from{{transform:translate(-20px,{sy0:.0f}px)}}to{{transform:translate({W + 20}px,{sy1:.0f}px)}}}}"
                         ".sat{animation:sat %.0fs linear %.0fs infinite}"
                         "@keyframes blink{0%%,86%%{opacity:.25}90%%{opacity:1}94%%,100%%{opacity:.25}}"
                         ".blink{animation:blink 1.6s steps(1) infinite}" % (dur, -r.uniform(0, dur)))
        extras.append('<g class="sat"><circle class="blink" r="1.3" fill="#FFFFFF"/></g>')

    # The galaxy: rotate in its own plane, then tilt toward us.
    gal_r = disk * 1.4
    galaxy = (
        f'<circle cx="{gx:.1f}" cy="{gy:.1f}" r="{halo:.1f}" fill="url(#halo)"/>'
        f'<circle cx="{gx:.1f}" cy="{gy:.1f}" r="{halo:.1f}" fill="none" stroke="{C.muted}" stroke-opacity=".32" stroke-dasharray="2 6"/>'
        f'<g transform="translate({gx:.1f} {gy:.1f}) rotate({pa:.1f}) scale(1 {math.cos(math.radians(incl)):.3f})">'
        f'<g class="spin"><image href="{gal_uri}" x="{-gal_r:.1f}" y="{-gal_r:.1f}" width="{2 * gal_r:.1f}" height="{2 * gal_r:.1f}"/></g></g>'
    )

    # Sightline, quasar and the photons that travel down it.
    spikes = "".join(
        f'<rect x="-34" y="-.5" width="68" height="1" fill="url(#spike)" transform="rotate({a})"/>' for a in (0, 90, 45, 135)
    )
    sight = (
        f'<line x1="{qx:.1f}" y1="{qy:.1f}" x2="{px:.1f}" y2="{py:.1f}" stroke="{C.glow}" stroke-opacity=".3" stroke-width="1.1"/>'
        f'<line x1="{hx0:.1f}" y1="{hy0:.1f}" x2="{hx1:.1f}" y2="{hy1:.1f}" stroke="{C.violet_hi}" stroke-opacity=".75" '
        f'stroke-width="1.6" stroke-dasharray="1 4" stroke-linecap="round"/>'
        f'<g transform="translate({qx:.1f} {qy:.1f})"><g class="pulse"><circle r="34" fill="url(#qso)"/>'
        f'<g opacity=".8">{spikes}</g></g><circle r="2.6" fill="#FFFFFF"/></g>'
        + "".join(f'<circle class="ph" cx="{qx:.1f}" cy="{qy:.1f}" r="2.6" style="animation-delay:{i * 1.27:.2f}s"/>' for i in range(3))
        + f'<path d="M{px:.1f},{py - 11:.1f} L{px + 11:.1f},{py + 8:.1f} L{px - 11:.1f},{py + 8:.1f} Z" fill="{C.sky}" '
        f'stroke="{C.ink}" stroke-width="1.3" stroke-linejoin="round"/>'
    )
    # The sightline always runs down from the quasar, so above it is clear.
    q_label = fonts.text(min(max(qx, 60), W - 60), qy - 42, f"z = {zq:.2f}", "it", 19, C.muted, "middle")
    # The galaxy's label goes on the far side of the galaxy from the sightline.
    nx, ny = gx - (qx + ux * t_mid), gy - (qy + uy * t_mid)
    norm = math.hypot(nx, ny) or 1.0
    reach = disk * 0.95 + 26
    lx = min(max(gx + nx / norm * reach, 70), W - 70)
    ly = min(max(gy + ny / norm * reach + 6, 26), PRISM_Y - 20)
    g_label = fonts.text(lx, ly, f"z = {zabs:.2f}", "it", 19, C.violet_hi, "middle", 'opacity=".85"')

    # Spectrum: rainbow line, the light under it, and the absorber's lines named.
    labels = []
    last_x = -1e9
    for c, ion in marks:
        x = wl_x(c)
        if x - last_x < 60:
            continue
        last_x = x
        labels.append(f'<line x1="{x:.1f}" y1="{SY_BASE + 4}" x2="{x:.1f}" y2="{SY_BASE + 9}" stroke="{C.violet_hi}" stroke-opacity=".7"/>'
                      + fonts.text(x, SY_BASE + 27, ion, "rm", 17, C.violet_hi, "middle"))
    spec = (
        f'<line x1="{SX0}" y1="{SY_BASE + 4}" x2="{SX1}" y2="{SY_BASE + 4}" stroke="{C.faint}"/>'
        f'<path class="area" d="{spec_area}" fill="url(#rain)" mask="url(#under)"/>'
        f'<path class="spec" d="{spec_line}" pathLength="1000" fill="none" stroke="url(#rain)" stroke-width="1.5" stroke-linejoin="round"/>'
        f'<g class="lab">{"".join(labels)}</g>'
    )

    css = (
        "@keyframes tw{0%,100%{opacity:1}50%{opacity:.18}}.tw{animation:tw 4s ease-in-out infinite}"
        f"@keyframes drift{{from{{transform:translate(0,0)}}to{{transform:translate({-r.uniform(20, 32):.0f}px,{r.uniform(-14, 14):.0f}px)}}}}"
        ".drift{animation:drift 48s ease-in-out infinite alternate}"
        f"@keyframes spin{{to{{transform:rotate({spin_dir}360deg)}}}}.spin{{animation:spin {spin_period:.0f}s linear infinite}}"
        "@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.7;transform:scale(.88)}}.pulse{animation:pulse 2.8s ease-in-out infinite}"
        f"@keyframes ph{{0%{{transform:translate(0,0);opacity:0;fill:{C.glow}}}4%{{opacity:1}}"
        f"{f_in * 100:.1f}%{{opacity:1;fill:{C.glow}}}{f_out * 100:.1f}%{{opacity:.55;fill:{C.violet_hi}}}96%{{opacity:.55;fill:{C.violet_hi}}}"
        f"100%{{transform:translate({dx:.1f}px,{dy:.1f}px);opacity:0;fill:{C.violet_hi}}}}}"
        ".ph{opacity:0;animation:ph 3.8s linear infinite}"
        "@keyframes spec{0%{stroke-dashoffset:1000;opacity:1}40%{stroke-dashoffset:0;opacity:1}"
        "86%{stroke-dashoffset:0;opacity:1}95%{stroke-dashoffset:0;opacity:0}100%{stroke-dashoffset:1000;opacity:0}}"
        f".spec{{stroke-dasharray:1000;stroke-dashoffset:0;animation:spec {CYCLE}s linear infinite}}"
        "@keyframes area{0%,22%{opacity:0}42%,84%{opacity:1}95%,100%{opacity:0}}"
        f".area{{animation:area {CYCLE}s ease-in-out infinite}}"
        "@keyframes lab{0%,36%{opacity:0}46%,84%{opacity:1}94%,100%{opacity:0}}"
        f".lab{{animation:lab {CYCLE}s ease-in-out infinite}}"
        + "".join(css_extra) + "".join(css_tw)
    )
    body = (
        defs
        + f'<g clip-path="url(#clip)"><rect width="{W}" height="{H}" fill="{C.sky}"/>'
        f'<g class="drift"><image href="{sky_uri}" x="{-pad}" y="{-pad}" width="{W + 2 * pad}" height="{H + 2 * pad}"/></g>'
        + "".join(stars) + "".join(extras) + galaxy + sight + q_label + g_label + spec + "</g>"
    )
    facts = {"z_qso": zq, "z_abs": zabs, "impact": round(geo["b"] / halo, 2), **morph,
             "lines": sorted({ion for _, ion in marks})}
    title = (f"A quasar at redshift {zq:.2f} shines through the halo of a {morph['arms']}-armed galaxy at redshift "
             f"{zabs:.2f}; its light is drawn as a spectrum with the galaxy's absorption lines")
    return document(W, H, body, fonts, css, title=title), facts
