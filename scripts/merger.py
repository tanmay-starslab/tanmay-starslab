"""Two disk galaxies on a close flyby that merge, a new pair every day.

The physics is the restricted three-body experiment of Toomre & Toomre
(1972): each galaxy is a softened point mass with a bulge, its disk is a set
of massless stars on circular orbits, and the tidal pull during the
encounter throws out long tails and a bridge. A drag on the two nuclei
stands in for dynamical friction, so the pair falls back together and
merges. The day's seed picks the mass ratio, the pericentre, each disk's
tilt and spin (some days one disk is retrograde and keeps its shape), the
viewing angle and the colours. Gas clouds in the disks light up pink as the
collision compresses them: the starburst that real mergers trigger.

    python scripts/merger.py out.webp [seed]
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import skyart as sa
from svgkit import C

W, H = 540, 360
EPS = 0.12  # Plummer softening of each galaxy's potential
DT = 0.008
T_START, T_END = -3.0, 9.0  # first pericentre passage at t = 0
FRAMES = 140
FADE_IN, FADE_OUT = 8, 16
VIEW = 4.4  # half-width of the field of view, in model units

PAIRS = [
    (C.violet, C.gold),
    (C.teal, C.rose),
    ("#9FB6FF", C.glow),
    (C.violet_hi, C.teal),
    (C.rose, C.gold),
    ("#7FA8FF", C.rose),
]


def rotation(axis: str, angle: float) -> np.ndarray:
    c, s = np.cos(angle), np.sin(angle)
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def disk(rng, n: int, mass: float, tilt: float, node: float, size: float):
    """Massless stars on circular orbits, rotated out of the orbital plane.

    Half follow an exponential profile (a bright centre), half a flat one, so
    the outskirts hold enough stars to draw crisp tidal tails.
    """
    r = rng.gamma(2.0, size * 0.25, n)
    while (bad := r > size * 1.1).any():
        r[bad] = rng.gamma(2.0, size * 0.25, bad.sum())
    flat = rng.random(n) < 0.5
    r[flat] = size * np.sqrt(rng.uniform(0.1**2, 1.0, flat.sum()))
    phi = rng.uniform(0, 2 * np.pi, n)
    pos = np.stack([r * np.cos(phi), r * np.sin(phi), rng.normal(0, 0.015, n)], axis=1)
    v = np.sqrt(mass * r**2 / (r**2 + EPS**2) ** 1.5)
    vel = np.stack([-v * np.sin(phi), v * np.cos(phi), np.zeros(n)], axis=1)
    rot = rotation("z", node) @ rotation("x", tilt)
    return pos @ rot.T, vel @ rot.T, r / size


def parabolic(mu: float, rp: float, f: float):
    p = 2 * rp
    r = p / (1 + np.cos(f))
    pos = np.array([r * np.cos(f), r * np.sin(f), 0.0])
    vel = np.sqrt(mu / p) * np.array([-np.sin(f), 1 + np.cos(f), 0.0])
    return pos, vel


def accel(stars, centres, masses):
    a = np.zeros_like(stars)
    for c, m in zip(centres, masses):
        d = c - stars
        r2 = (d**2).sum(axis=1) + EPS**2
        a += m * d / r2[:, None] ** 1.5
    return a


def nuclei_accel(centres, cvel, masses, drag):
    d = centres[1] - centres[0]
    r2 = (d**2).sum() + EPS**2
    pull = d / r2**1.5
    a = np.array([masses[1] * pull, -masses[0] * pull])
    return a - drag * np.exp(-r2 / 1.8**2) * cvel


def plan(seed: int) -> dict:
    rng = np.random.default_rng(seed)
    q = float(rng.uniform(0.5, 1.0))
    tilt_b = float(rng.uniform(25, 155))
    return {
        "q": round(q, 2),
        "rp": float(rng.uniform(0.95, 1.35)),
        "tilt_a": float(rng.uniform(0, 30)),
        "tilt_b": tilt_b,
        "node_a": float(rng.uniform(0, 360)),
        "node_b": float(rng.uniform(0, 360)),
        "view_tilt": float(rng.uniform(22, 62)),
        "view_rot": float(rng.uniform(0, 360)),
        "pair": PAIRS[int(rng.integers(0, len(PAIRS)))],
        "swap": bool(rng.random() < 0.5),
        "retrograde": tilt_b > 90,
        "drag": float(rng.uniform(0.5, 0.7)),
        "spin": float(rng.uniform(-14, 14)),
        "zoom": float(rng.uniform(1.0, 1.18)),
    }


def simulate(seed: int, p: dict):
    rng = np.random.default_rng(seed + 1)
    m1, m2 = 1.0, p["q"]
    mu, rp = m1 + m2, p["rp"]
    fs = np.linspace(-3.0, 0, 20000)
    d = np.tan(fs / 2)
    times = np.sqrt(2 * rp**3 / mu) * (d + d**3 / 3)
    f0 = fs[np.argmin(np.abs(times - T_START))]
    rel_pos, rel_vel = parabolic(mu, rp, f0)
    centres = np.array([-rel_pos * m2 / mu, rel_pos * m1 / mu])
    cvel = np.array([-rel_vel * m2 / mu, rel_vel * m1 / mu])
    masses = np.array([m1, m2])

    na, nb = 4400, int(4400 * (0.55 + 0.45 * m2))
    pa, va, ra = disk(rng, na, m1, math.radians(p["tilt_a"]), math.radians(p["node_a"]), 1.3)
    pb, vb, rb = disk(rng, nb, m2, math.radians(p["tilt_b"]), math.radians(p["node_b"]), 1.3 * m2**0.4)
    stars = np.concatenate([pa + centres[0], pb + centres[1]])
    svel = np.concatenate([va + cvel[0], vb + cvel[1]])
    which = np.concatenate([np.zeros(na, int), np.ones(nb, int)])
    radius = np.concatenate([ra, rb])

    steps = int((T_END - T_START) / DT)
    every = steps / FRAMES
    snaps, next_snap = [], 0.0
    acc_s = accel(stars, centres, masses)
    acc_c = nuclei_accel(centres, cvel, masses, p["drag"])
    for step in range(steps):
        svel += 0.5 * DT * acc_s
        cvel += 0.5 * DT * acc_c
        stars += DT * svel
        centres += DT * cvel
        acc_s = accel(stars, centres, masses)
        acc_c = nuclei_accel(centres, cvel, masses, p["drag"])
        svel += 0.5 * DT * acc_s
        cvel += 0.5 * DT * acc_c
        if step >= next_snap and len(snaps) < FRAMES:
            snaps.append((stars.copy(), centres.copy()))
            next_snap += every
    return snaps, which, radius, masses


def background(seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed + 2)
    img = np.zeros((H, W, 3)) + sa.hex_rgb(C.sky)
    haze = sa.fbm(rng, W, H, 160, 5) ** 2.5
    img += 0.05 * haze[..., None] * sa.hex_rgb(C.violet)
    stars = np.zeros_like(img)
    n = 900
    temps = rng.choice([3500, 4800, 6000, 8000, 12000, 20000], n)
    sa.splat(stars, rng.uniform(0, W, n), rng.uniform(0, H, n), sa.star_color(temps) * (rng.pareto(2.5, n) * 0.25 + 0.06)[:, None])
    # A few far-off galaxies: tiny tilted smudges.
    for _ in range(7):
        x, y = rng.uniform(20, W - 20), rng.uniform(20, H - 20)
        a, e = rng.uniform(0, np.pi), rng.uniform(0.3, 0.9)
        m = 60
        u, v = rng.normal(0, 2.2, m), rng.normal(0, 2.2 * e, m)
        sa.splat(stars, x + u * np.cos(a) - v * np.sin(a), y + u * np.sin(a) + v * np.cos(a),
                 sa.star_color(rng.uniform(4000, 9000)) * 0.03)
    return img + sa.bloom(stars, (0.7, 2.2), (0.5, 0.15))


def frames(seed: int) -> tuple[list[Image.Image], dict]:
    p = plan(seed)
    snaps, which, radius, masses = simulate(seed, p)
    rng = np.random.default_rng(seed + 3)
    bg = background(seed)
    col_a, col_b = (sa.hex_rgb(c) for c in (p["pair"][::-1] if p["swap"] else p["pair"]))
    temps = np.where(radius < 0.25, rng.uniform(3800, 5200, len(which)), rng.uniform(6500, 16000, len(which)))
    natural = sa.star_color(temps)
    tint = np.where(which[:, None] == 0, col_a, col_b)
    colors = sa.mix(natural, tint, 0.8) ** 1.3
    flux = 0.5 * (0.6 + rng.pareto(3.0, len(which)) * 0.5)[:, None]
    gas = (rng.random(len(which)) < 0.05) & (radius > 0.35)
    pink = sa.hex_rgb(C.rose) * np.array([1.0, 0.75, 0.9])

    # Bulges: hot, compact clouds that ride on the nuclei.
    nbul = 700
    bul = rng.standard_normal((2, nbul, 3)) * np.array([0.09, 0.09, 0.06])
    yy, xx = np.mgrid[0:H, 0:W]
    vignette = np.clip(1.15 - np.hypot((xx - W / 2) / W, (yy - H / 2) / H) * 1.1, 0.55, 1)[..., None]

    images, burst = [], 0.0
    n = len(snaps)
    for i, (stars, centres) in enumerate(snaps):
        f = i / max(n - 1, 1)
        view = rotation("x", -math.radians(p["view_tilt"])) @ rotation("z", math.radians(p["view_rot"] + p["spin"] * f))
        zoom = 1 + (p["zoom"] - 1) * f
        scale = W / (2 * VIEW) * zoom
        com = (centres * masses[:, None]).sum(0) / masses.sum()
        P = (stars - com) @ view.T
        Cn = (centres - com) @ view.T
        px, py = P[:, 0] * scale + W / 2, H / 2 - P[:, 1] * scale

        # Starburst: grows while the nuclei are close, then fades slowly.
        sep = np.linalg.norm(centres[1] - centres[0])
        burst = burst * 0.9 + 0.1 * 2.0 * math.exp(-(sep / 1.2) ** 2)
        img = np.zeros((H, W, 3))
        sa.splat(img, px, py, colors * flux)
        clouds = np.zeros((H, W, 3))
        sa.splat(clouds, px[gas], py[gas], pink[None, :] * 0.55 * (0.1 + burst))
        img += sa.blur(clouds, 1.6) * 2.0
        for k, col in ((0, col_a), (1, col_b)):
            b = (bul[k] * (1 if k == 0 else masses[1] ** 0.5)) @ view.T
            sa.splat(img, b[:, 0] * scale + Cn[k, 0] * scale + W / 2, H / 2 - (b[:, 1] + Cn[k, 1]) * scale,
                     sa.mix(sa.star_color(4300), col, 0.3) * 0.5)
            sa.splat(img, np.array([Cn[k, 0] * scale + W / 2]), np.array([H / 2 - Cn[k, 1] * scale]),
                     sa.mix([1, 1, 1], col, 0.2) * 9.0)
        lit = sa.bloom(img, (1.0, 3.2, 10.0), (1.0, 0.75, 0.55))
        fade = max(0.0, min(1.0, (i + 1) / FADE_IN, (n - i) / FADE_OUT))
        frame = sa.tonemap(bg + lit * fade, 1.15) * vignette
        images.append(sa.to_image(frame))

    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, H - 1), radius=20, fill=255)
    images = [Image.merge("RGBA", (*fr.split(), mask)) for fr in images]
    final_sep = float(np.linalg.norm(snaps[-1][1][1] - snaps[-1][1][0]))
    return images, {"q": p["q"], "retrograde": p["retrograde"], "merged": final_sep < 0.35}


def render(seed: int, out: Path) -> dict:
    images, facts = frames(seed)
    durations = [60] * len(images)
    durations[-1] = 500
    out.parent.mkdir(parents=True, exist_ok=True)
    # method 4: method 6 is ~10x slower for a few per cent smaller.
    images[0].save(out, save_all=True, append_images=images[1:], duration=durations, loop=0, quality=72, method=4)
    return {**facts, "bytes": out.stat().st_size}


if __name__ == "__main__":
    print(render(int(sys.argv[2]) if len(sys.argv) > 2 else 1972, Path(sys.argv[1])))
