"""Raster helpers for the daily art: noise, light, glow and colour.

Everything that should look photographic (nebulae, a galaxy's disk, the
merger) is drawn as light: points of flux are added into a float image,
blurred into a glow, then tone-mapped down to 8 bits. Only numpy and Pillow,
so it runs on a stock Actions runner.
"""

from __future__ import annotations

import base64
import io

import numpy as np
from PIL import Image

# --------------------------------------------------------------------------- colour


def hex_rgb(color: str) -> np.ndarray:
    color = color.lstrip("#")
    return np.array([int(color[i : i + 2], 16) for i in (0, 2, 4)], float) / 255.0


def rgb_hex(rgb) -> str:
    r, g, b = (int(round(255 * min(max(float(v), 0.0), 1.0))) for v in rgb)
    return f"#{r:02X}{g:02X}{b:02X}"


def mix(a, b, t: float) -> np.ndarray:
    return np.asarray(a, float) * (1 - t) + np.asarray(b, float) * t


def star_color(temp: np.ndarray | float) -> np.ndarray:
    """Approximate colour of a star of temperature `temp` (K), normalised to max 1."""
    t = np.clip(np.asarray(temp, float), 2500, 30000)[..., None] / 100.0
    hot = np.maximum(t - 60, 1e-6)
    r = np.where(t <= 66, 1.0, np.clip(1.292936 * hot**-0.1332047, 0, 1))
    g = np.where(t <= 66, np.clip(0.3900816 * np.log(t) - 0.6318414, 0, 1), np.clip(1.129891 * hot**-0.0755148, 0, 1))
    b = np.where(t >= 66, 1.0, np.clip(0.5432068 * np.log(np.maximum(t - 10, 1e-6)) - 1.1962541, 0, 1))
    rgb = np.concatenate([r, g, b], axis=-1)
    return rgb / rgb.max(axis=-1, keepdims=True)


def wavelength_rgb(lam: float) -> np.ndarray:
    """A soft, slightly desaturated colour for a visible wavelength in angstroms (violet to red)."""
    nm = lam / 10.0
    if nm < 440:
        rgb = (0.5 * (440 - nm) / 60 + 0.2, 0.1, 1.0)
    elif nm < 490:
        rgb = (0.0, (nm - 440) / 50, 1.0)
    elif nm < 510:
        rgb = (0.0, 1.0, -(nm - 510) / 20)
    elif nm < 580:
        rgb = ((nm - 510) / 70, 1.0, 0.0)
    elif nm < 645:
        rgb = (1.0, -(nm - 645) / 65, 0.0)
    else:
        rgb = (1.0, 0.15, 0.25)
    return mix(rgb, (0.88, 0.88, 0.9), 0.3)


# --------------------------------------------------------------------------- noise and blur


def box_blur(img: np.ndarray, radius: int, axis: int) -> np.ndarray:
    if radius < 1:
        return img
    pad = [(0, 0)] * img.ndim
    pad[axis] = (radius + 1, radius)
    padded = np.pad(img, pad, mode="edge")
    c = np.cumsum(padded, axis=axis)
    n = img.shape[axis]
    hi = np.take(c, np.arange(2 * radius + 1, 2 * radius + 1 + n), axis=axis)
    lo = np.take(c, np.arange(0, n), axis=axis)
    return (hi - lo) / (2 * radius + 1)


def blur(img: np.ndarray, sigma: float) -> np.ndarray:
    """Gaussian blur, approximated by three box blurs in each direction."""
    if sigma <= 0.3:
        return img
    radius = max(1, int(round((np.sqrt(4 * sigma**2 + 1) - 1) / 2)))
    out = img
    for _ in range(3):
        out = box_blur(box_blur(out, radius, 0), radius, 1)
    return out


def upsample(grid: np.ndarray, w: int, h: int) -> np.ndarray:
    return np.asarray(Image.fromarray(grid.astype(np.float32), "F").resize((w, h), Image.BICUBIC), float)


def fbm(rng: np.random.Generator, w: int, h: int, scale: float, octaves: int = 6, gain: float = 0.5) -> np.ndarray:
    """Fractal noise in [0, 1]: smooth on `scale` pixels, with finer detail on top."""
    total = np.zeros((h, w))
    amp, norm, s = 1.0, 0.0, scale
    for _ in range(octaves):
        gw, gh = max(2, int(w / s) + 3), max(2, int(h / s) + 3)
        total += amp * upsample(rng.random((gh, gw)), w, h)
        norm += amp
        amp *= gain
        s /= 2.0
    total /= norm
    lo, hi = np.percentile(total, 1), np.percentile(total, 99)
    return np.clip((total - lo) / (hi - lo + 1e-9), 0, 1)


# --------------------------------------------------------------------------- light


def splat(img: np.ndarray, x: np.ndarray, y: np.ndarray, rgb: np.ndarray) -> None:
    """Add point sources at sub-pixel positions (bilinear), rgb shaped (n, 3) or (3,)."""
    h, w = img.shape[:2]
    rgb = np.broadcast_to(np.asarray(rgb, float), (len(x), 3))
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    idx, wts = [], []
    for dx, dy, wt in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xi, yi = x0 + dx, y0 + dy
        ok = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
        idx.append(yi[ok] * w + xi[ok])
        wts.append(rgb[ok] * wt[ok, None])
    idx, wts = np.concatenate(idx), np.concatenate(wts)
    flat = img.reshape(-1, 3)
    for c in range(3):
        flat[:, c] += np.bincount(idx, weights=wts[:, c], minlength=h * w)


def bloom(img: np.ndarray, sigmas=(1.2, 4.0, 12.0), weights=(0.9, 0.55, 0.35)) -> np.ndarray:
    return img + sum(w * blur(img, s) for s, w in zip(sigmas, weights))


def tonemap(img: np.ndarray, exposure: float = 1.0) -> np.ndarray:
    """Soft film-like curve that keeps hues in bright cores instead of clipping to white too early."""
    x = np.maximum(img * exposure, 0)
    lum = x.max(axis=-1, keepdims=True)
    mapped = 1 - np.exp(-lum)
    # Desaturate toward white only in the very brightest parts.
    out = x / (lum + 1e-9) * mapped
    white = np.clip(lum - 1.2, 0, None) / (lum + 1.0)
    return np.clip(out * (1 - white) + white * mapped, 0, 1)


def to_image(rgb01: np.ndarray, alpha01: np.ndarray | None = None) -> Image.Image:
    rgb8 = np.uint8(np.clip(rgb01 * 255 + 0.5, 0, 255))
    if alpha01 is None:
        return Image.fromarray(rgb8, "RGB")
    a8 = np.uint8(np.clip(alpha01 * 255 + 0.5, 0, 255))
    return Image.fromarray(np.dstack([rgb8, a8]), "RGBA")


def data_uri(img: Image.Image, fmt: str = "WEBP", quality: int = 80) -> str:
    buf = io.BytesIO()
    if fmt == "JPEG":
        img.convert("RGB").save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
        mime = "image/jpeg"
    else:
        img.save(buf, "WEBP", quality=quality, method=6, alpha_quality=90)
        mime = "image/webp"
    return f"data:{mime};base64,{base64.b64encode(buf.getvalue()).decode('ascii')}"
