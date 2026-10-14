"""Render assets/merger.webp: two disk galaxies on a close flyby that merge.

This is the classic restricted three-body experiment of Toomre & Toomre
(1972): each galaxy is a softened point mass, its disk is a set of massless
stars on circular orbits, and the tidal pull during the encounter throws out
long tails and a bridge. One disk is prograde in the orbital plane, the other
is tilted, so the two galaxies respond differently. A drag on the two nuclei
stands in for dynamical friction, so the pair falls back together and merges
instead of flying apart.

Run once by hand (the animation is committed); it needs numpy and Pillow:

    pip install numpy pillow
    python scripts/make_merger.py
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
# Animated WebP: full colour (no 256-colour banding) at half the size of a GIF.
OUT = ROOT / "assets" / "merger.webp"

W, H = 500, 340
EPS = 0.12  # Plummer softening of each galaxy's potential
DT = 0.008
T_START, T_END = -3.6, 11.0  # first pericentre passage at t = 0
FRAMES = 118
FADE_IN, FADE_OUT = 6, 14
VIEW = 4.6  # half-width of the field of view, in model units
ORBIT_ROT = np.radians(-70)  # turn the orbit so the approach runs across the frame
DRAG = 0.55  # dynamical-friction stand-in, acting on the nuclei near each other
TILT = np.radians(35)  # viewing angle above the orbital plane

BG = np.array([11, 16, 44], float)
COLOR_A = np.array([120, 110, 255], float)  # violet
COLOR_B = np.array([255, 170, 70], float)  # gold


def rotation(axis: str, angle: float) -> np.ndarray:
    c, s = np.cos(angle), np.sin(angle)
    if axis == "x":
        return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def disk(rng: np.random.Generator, n: int, mass: float, tilt: float, spin: float) -> tuple[np.ndarray, np.ndarray]:
    """Massless stars on circular orbits in a disk, rotated out of the orbital plane."""
    r = np.sqrt(rng.uniform(0.15**2, 1.25**2, n))
    phi = rng.uniform(0, 2 * np.pi, n)
    pos = np.stack([r * np.cos(phi), r * np.sin(phi), rng.normal(0, 0.015, n)], axis=1)
    v = np.sqrt(mass * r**2 / (r**2 + EPS**2) ** 1.5)
    vel = np.stack([-v * np.sin(phi), v * np.cos(phi), np.zeros(n)], axis=1) * spin
    rot = rotation("x", tilt) @ rotation("z", 0.6)
    return pos @ rot.T, vel @ rot.T


def parabolic(mu: float, rp: float, f: float) -> tuple[np.ndarray, np.ndarray]:
    """Relative position and velocity on a parabolic orbit at true anomaly f."""
    p = 2 * rp
    r = p / (1 + np.cos(f))
    pos = np.array([r * np.cos(f), r * np.sin(f), 0.0])
    vel = np.sqrt(mu / p) * np.array([-np.sin(f), 1 + np.cos(f), 0.0])
    return pos, vel


def nuclei_accel(centres: np.ndarray, cvel: np.ndarray, masses: np.ndarray) -> np.ndarray:
    d = centres[1] - centres[0]
    r2 = (d**2).sum() + EPS**2
    pull = d / r2**1.5
    a = np.array([masses[1] * pull, -masses[0] * pull])
    # Friction grows as the galaxies overlap, draining the orbit's energy.
    friction = DRAG * np.exp(-r2 / 1.8**2)
    return a - friction * cvel


def accel(stars: np.ndarray, centres: np.ndarray, masses: np.ndarray) -> np.ndarray:
    a = np.zeros_like(stars)
    for c, m in zip(centres, masses):
        d = c - stars
        r2 = (d**2).sum(axis=1) + EPS**2
        a += m * d / r2[:, None] ** 1.5
    return a


def time_of_true_anomaly(f: float, rp: float, mu: float) -> float:
    """Barker's equation for a parabola: time since pericentre."""
    d = np.tan(f / 2)
    return np.sqrt(2 * rp**3 / mu) * (d + d**3 / 3)


def simulate():
    rng = np.random.default_rng(1972)
    m1 = m2 = 1.0
    mu, rp = m1 + m2, 1.1
    # Find the true anomaly whose time matches T_START.
    fs = np.linspace(-3.0, 0, 20000)
    f0 = fs[np.argmin(np.abs([time_of_true_anomaly(f, rp, mu) - T_START for f in fs]))]
    rel_pos, rel_vel = parabolic(mu, rp, f0)
    centres = np.array([-rel_pos * m2 / mu, rel_pos * m1 / mu])
    cvel = np.array([-rel_vel * m2 / mu, rel_vel * m1 / mu])
    masses = np.array([m1, m2])

    pa, va = disk(rng, 2600, m1, tilt=np.radians(8), spin=1.0)  # near-prograde: long tails
    pb, vb = disk(rng, 2200, m2, tilt=np.radians(62), spin=1.0)
    stars = np.concatenate([pa + centres[0], pb + centres[1]])
    svel = np.concatenate([va + cvel[0], vb + cvel[1]])
    which = np.concatenate([np.zeros(len(pa), int), np.ones(len(pb), int)])

    steps = int((T_END - T_START) / DT)
    every = max(steps // FRAMES, 1)
    snapshots = []
    acc_s = accel(stars, centres, masses)
    acc_c = nuclei_accel(centres, cvel, masses)
    for step in range(steps):
        # Kick-drift-kick leapfrog for both galaxies and all stars.
        svel += 0.5 * DT * acc_s
        cvel += 0.5 * DT * acc_c
        stars += DT * svel
        centres += DT * cvel
        acc_s = accel(stars, centres, masses)
        acc_c = nuclei_accel(centres, cvel, masses)
        svel += 0.5 * DT * acc_s
        cvel += 0.5 * DT * acc_c
        if step % every == 0 and len(snapshots) < FRAMES:
            snapshots.append((stars.copy(), centres.copy()))
    return snapshots, which


def background() -> np.ndarray:
    bg = np.tile(BG, (H, W, 1))
    rng = np.random.default_rng(7)
    for _ in range(140):
        x, y = rng.integers(0, W), rng.integers(0, H)
        bg[y, x] = np.clip(bg[y, x] + rng.uniform(40, 150), 0, 255)
    return bg


def render(stars: np.ndarray, centres: np.ndarray, which: np.ndarray, bg: np.ndarray, fade: float) -> Image.Image:
    view = rotation("x", -TILT) @ rotation("z", ORBIT_ROT)
    p = stars @ view.T
    c = centres @ view.T
    scale = W / (2 * VIEW)
    px = (p[:, 0] * scale + W / 2).astype(int)
    py = (H / 2 - p[:, 1] * scale).astype(int)
    img = np.zeros((H, W, 3))
    for k, color in ((0, COLOR_A), (1, COLOR_B)):
        sel = (which == k) & (px >= 0) & (px < W) & (py >= 0) & (py < H)
        counts = np.zeros((H, W))
        np.add.at(counts, (py[sel], px[sel]), 1.0)
        img += counts[:, :, None] * color[None, None, :] / 255.0
    # Bright galactic nuclei.
    for cx, cy, color in ((c[0, 0], c[0, 1], COLOR_A), (c[1, 0], c[1, 1], COLOR_B)):
        x, y = int(cx * scale + W / 2), int(H / 2 - cy * scale)
        if 0 <= x < W and 0 <= y < H:
            img[max(y - 1, 0) : y + 2, max(x - 1, 0) : x + 2] += 6 * color / 255.0
    # Tone-map each channel separately so the two galaxies keep their hues.
    sharp = 1 - np.exp(-1.6 * img)
    glow_src = Image.fromarray(np.uint8(np.clip(sharp * 255, 0, 255)))
    glow = np.asarray(glow_src.filter(ImageFilter.GaussianBlur(5)), float) / 255.0
    light = sharp * 0.9 + glow * 2.2
    out = bg + 255 * light * fade
    return Image.fromarray(np.uint8(np.clip(out, 0, 255)))


def main() -> None:
    snapshots, which = simulate()
    bg = background()
    frames = []
    n = len(snapshots)
    for i, (stars, centres) in enumerate(snapshots):
        fade = min(1.0, (i + 1) / FADE_IN, (n - i) / FADE_OUT)
        frames.append(render(stars, centres, which, bg, max(fade, 0.0)))
    # Rounded corners, transparent outside, to match the other panels on the page.
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, H - 1), radius=18, fill=255)
    frames = [Image.merge("RGBA", (*f.split(), mask)) for f in frames]
    durations = [70] * n
    durations[-1] = 400
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(OUT, save_all=True, append_images=frames[1:], duration=durations, loop=0, quality=74, method=6)
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size / 1e6:.2f} MB, {n} frames)")


if __name__ == "__main__":
    main()
