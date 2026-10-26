"""The daily art: a new hero sky, galaxy merger and aurora footer every day.

Each day (Arizona time) has a seed. The art is drawn from it, so a day's
images are stable across the hourly refreshes and change at midnight; a
visitor can also roll a new universe by opening a pre-filled issue
(.github/workflows/reroll.yml), which bumps data/reroll.json.

The images are heavy and change daily, so they do not live on main: they are
force-pushed as a single commit to the `daily-art` branch (no history piles
up) under versioned file names, and the README points at today's names.

    python scripts/daily.py [--published VERSION] [--out build/daily]
    python scripts/daily.py bump-roll        # used by the reroll workflow

With --published equal to today's version, nothing is drawn and only the
README links are checked; otherwise the art is drawn into --out with a
manifest.json, for the workflow to publish before it pushes the README.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import html
import json
import math
import random
import sys
import urllib.parse
from pathlib import Path

import hero
import merger
import readme
import refresh
from svgkit import ROOT, C, Fonts, document, esc

REPO = "tanmay-starslab/tanmay-starslab"
ART_BRANCH = "daily-art"
RAW = f"https://raw.githubusercontent.com/{REPO}/{ART_BRANCH}"
ROLL_FILE = ROOT / "data" / "reroll.json"
MAX_ROLLS = 30  # per day, so a flood of issues cannot turn into a flood of commits
REROLL_TITLE = "reroll the universe"
REROLL_URL = (f"https://github.com/{REPO}/issues/new?" + urllib.parse.urlencode({
    "title": REROLL_TITLE,
    "body": "Press **Submit new issue** and a bot draws a new sky, galaxy and merger for the profile "
            "(it closes this issue for you, usually within two minutes).",
}))


# --------------------------------------------------------------------------- seeds and versions


def today() -> dt.date:
    return dt.datetime.now(refresh.MST).date()


def roll_count(day: dt.date) -> int:
    """How many times today's universe has been re-rolled (0 if never)."""
    try:
        state = json.loads(ROLL_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    return int(state.get("count", 0)) if state.get("date") == day.isoformat() else 0


def bump_roll(day: dt.date) -> int:
    """Count one more roll for `day`; returns the new count, or 0 if today's limit is reached."""
    count = roll_count(day)
    if count >= MAX_ROLLS:
        return 0
    ROLL_FILE.parent.mkdir(parents=True, exist_ok=True)
    ROLL_FILE.write_text(json.dumps({"date": day.isoformat(), "count": count + 1}) + "\n", encoding="utf-8")
    return count + 1


def universe_key(day: dt.date, roll: int) -> str:
    return day.isoformat() + (f"r{roll}" if roll else "")


def seed_for(key: str) -> int:
    return int.from_bytes(hashlib.sha256(f"{REPO}/{key}".encode()).digest()[:6], "big")


def version_for(key: str, entry: dict | None) -> str:
    """Changes when the universe or NASA's picture changes; names the published files."""
    apod_tag = hashlib.sha256(json.dumps([(entry or {}).get(k) for k in ("date", "title", "credit")]).encode())
    return f"{key}-{apod_tag.hexdigest()[:6]}"


# --------------------------------------------------------------------------- footer


def moon_disk(phase: float, r: float) -> str:
    """Tonight's moon: lit limb plus an elliptical terminator (as the sky badge, but large and glowing)."""
    k = math.cos(2 * math.pi * phase)
    waxing = phase < 0.5
    limb = f"M0,{-r} A{r},{r} 0 0 {1 if waxing else 0} 0,{r}"
    term = f"A{abs(k) * r:.2f},{r} 0 0 {(0 if waxing else 1) if k > 0 else (1 if waxing else 0)} 0,{-r} Z"
    return (f'<circle r="{r * 3.2:.1f}" fill="url(#moonglow)"/><circle r="{r}" fill="#26262C"/>'
            f'<path d="{limb} {term}" fill="#FFF3D6"/>')


def footer(seed: int, day: dt.date) -> str:
    W, H = 1200, 170
    r = random.Random(seed)
    phase, lit, name = refresh.moon_tonight(day)
    stars, tw = [], 0
    for i in range(110):
        x, y = r.uniform(0, W), r.uniform(0, 112)
        attrs = ""
        if r.random() < 0.22:
            attrs = f' class="tw" style="animation-duration:{r.uniform(2.4, 5.6):.1f}s;animation-delay:{-r.uniform(0, 5):.1f}s"'
        stars.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r.choice([0.5, 0.6, 0.8, 1.0, 1.3])}" '
                     f'fill="{r.choice([C.ink, C.ink, C.glow, C.violet_hi])}" opacity="{r.uniform(0.35, 0.95):.2f}"{attrs}/>')
    hues = [C.teal, C.violet, C.rose, C.gold, C.violet_hi]
    r.shuffle(hues)
    ribbons, grads = [], []
    for i, color in enumerate(hues[:3]):
        amp, y0, dur = r.uniform(10, 22), r.uniform(34, 68), r.uniform(24, 44)
        wl1, wl2 = r.choice([400, 600, 1200]), r.choice([200, 240, 300])
        pts = []
        for x in range(0, 2 * W + 1, 20):
            y = y0 + amp * math.sin(2 * math.pi * x / wl1 + i) + 8 * math.sin(2 * math.pi * x / wl2 + 2 * i)
            pts.append(f"{x},{y:.1f}")
        d = "M" + " L".join(pts) + f" L{2 * W},{y0 + 90:.0f} L0,{y0 + 90:.0f} Z"
        ribbons.append(f'<g class="rib" style="animation-duration:{dur:.0f}s"><path d="{d}" fill="url(#a{i})" filter="url(#blur)"/></g>')
        grads.append(f'<linearGradient id="a{i}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{color}" stop-opacity="{r.uniform(0.4, 0.6):.2f}"/>'
                     f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></linearGradient>')
    trees, x = [], 0.0
    while x < W:
        h = r.uniform(14, 36)
        trees.append(f"M{x:.0f},{H} L{x + 9:.0f},{H - h:.0f} L{x + 18:.0f},{H}")
        x += r.uniform(10, 18)
    dome_x = r.choice([r.uniform(120, 360), r.uniform(840, 1080)])
    moon_x = r.uniform(380, 820)
    hill = r.uniform(30, 50)
    body = (
        "<defs>"
        f'<linearGradient id="fsky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{C.sky}"/>'
        f'<stop offset="1" stop-color="{C.sky_top}"/></linearGradient>'
        f'<radialGradient id="moonglow"><stop offset="0" stop-color="#FFF3D6" stop-opacity="{0.08 + 0.22 * lit:.2f}"/>'
        f'<stop offset="1" stop-color="#FFF3D6" stop-opacity="0"/></radialGradient>'
        + "".join(grads)
        + '<filter id="blur" x="-5%" y="-50%" width="110%" height="200%"><feGaussianBlur stdDeviation="7"/></filter>'
        "</defs>"
        f'<rect width="{W}" height="{H}" rx="22" fill="url(#fsky)"/>'
        + "".join(stars)
        + f'<g transform="translate({moon_x:.0f} {r.uniform(30, 46):.0f}) rotate({r.uniform(-30, 30):.0f})">{moon_disk(phase, 11)}</g>'
        + "".join(ribbons)
        + f'<path d="M0,{H - 18} Q300,{H - hill:.0f} 600,{H - 22} T1200,{H - r.uniform(22, 40):.0f} V{H} H0 Z" fill="#09090B"/>'
        + f'<path d="{" ".join(trees)}" fill="#050506"/>'
        + f'<g transform="translate({dome_x:.0f} {H - 40})"><rect x="-30" y="0" width="60" height="30" fill="#050506"/>'
        f'<path d="M-34,2 A34,34 0 0 1 34,2 Z" fill="#0D0D10"/><rect class="slit" x="-5" y="-30" width="10" height="30" fill="{C.glow}" opacity=".5"/></g>'
    )
    css = ("@keyframes tw{0%,100%{opacity:.95}50%{opacity:.12}}.tw{animation:tw 4s ease-in-out infinite}"
           "@keyframes rib{to{transform:translateX(-600px)}}.rib{animation:rib 30s linear infinite}"
           "@keyframes slit{0%,100%{opacity:.25}50%{opacity:.7}}.slit{animation:slit 4s ease-in-out infinite}")
    clip = f'<clipPath id="clip"><rect width="{W}" height="{H}" rx="22"/></clipPath>'
    return document(W, H, f'{clip}<g clip-path="url(#clip)">{body}</g>', None, css,
                    title=f"An aurora over an observatory under tonight's {name}")


# --------------------------------------------------------------------------- caption plaque


def fit(fonts: Fonts, face: str, text: str, size: float, width: float) -> str:
    """Trim `text` with an ellipsis until it fits `width` at `size`."""
    if fonts.width(face, text, size) <= width:
        return text
    while text and fonts.width(face, text + "…", size) > width:
        text = text[:-1].rstrip()
    return text + "…"


def plaque(entry: dict | None, facts: dict, version: str, roll: int) -> str:
    """Museum-label captions under the two sky panels: NASA's picture and today's simulated merger."""
    fonts = Fonts()
    W, H = 1200, 128
    r = random.Random(version)
    cells = []
    if entry:
        when = dt.date.fromisoformat(entry["date"])
        kind = "video" if entry.get("kind") in ("video", "youtube") else "picture"
        cells.append((
            f"{when.day} {when:%B %Y} · NASA's {kind} of the day",
            entry["title"],
            f"© {entry['credit']}" if entry.get("credit") else "click the picture for the story",
        ))
    else:
        cells.append(("NASA's picture of the day", "resting today", ""))
    spin = "one disk spins against the orbit" if facts["retrograde"] else "both disks spin with the orbit"
    cells.append((
        "simulated today" + (f" · re-rolled {roll}×" if roll else ""),
        f"two galaxies merge, mass ratio 1 : {facts['q']:.2f}",
        f"{spin} · click it to roll a new one",
    ))
    parts = []
    for i, (label, title, note) in enumerate(cells):
        cx = 300 + 600 * i
        parts.append(fonts.text(cx, 38, label, "it", 17, C.muted, "middle"))
        parts.append(fonts.text(cx, 74, fit(fonts, "rm", title, 28, 540), "rm", 28, C.ink, "middle"))
        parts.append(fonts.text(cx, 104, fit(fonts, "it", note, 17, 540), "it", 17, C.violet_hi, "middle"))
    dots = "".join(
        f'<circle class="tw" cx="{r.uniform(14, W - 14):.0f}" cy="{r.uniform(10, H - 10):.0f}" r="{r.choice([0.6, 0.8, 1.0])}" '
        f'fill="{r.choice([C.glow, C.violet_hi, C.ink])}" style="animation-duration:{r.uniform(2.5, 6):.1f}s;'
        f'animation-delay:{-r.uniform(0, 6):.1f}s"/>' for _ in range(26)
    )
    body = (
        f'<defs><linearGradient id="div" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{C.edge}" stop-opacity="0"/>'
        f'<stop offset=".5" stop-color="{C.violet}"/><stop offset="1" stop-color="{C.edge}" stop-opacity="0"/></linearGradient></defs>'
        f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="20" fill="{C.panel}" stroke="{C.edge}" stroke-width="1.2"/>'
        + dots + f'<rect class="pulse" x="599" y="18" width="2" height="{H - 36}" fill="url(#div)"/>' + "".join(parts)
    )
    css = ("@keyframes tw{0%,100%{opacity:.8}50%{opacity:.08}}.tw{animation:tw 4s ease-in-out infinite}"
           "@keyframes pulse{0%,100%{opacity:.35}50%{opacity:1}}.pulse{animation:pulse 5s ease-in-out infinite}")
    title = " | ".join(" — ".join(x for x in cell if x) for cell in cells)
    return document(W, H, body, fonts, css, title=title)


# --------------------------------------------------------------------------- README


def listing(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def readme_blocks(manifest: dict, entry: dict | None) -> dict[str, str]:
    v = manifest["version"]
    hf, mf = manifest["hero"], manifest["merger"]
    hero_alt = (f"Today's generated sky: a quasar at redshift {hf['z_qso']:.2f} shines through the halo of a "
                f"{hf['arms']}-armed spiral galaxy at redshift {hf['z_abs']:.2f}, and its light is drawn as a spectrum "
                f"showing the galaxy's {listing(hf['lines'])} absorption lines.")
    merger_alt = (f"Today's simulated galaxy merger: two disk galaxies with mass ratio 1 to {mf['q']:.2f} collide, "
                  f"throw out tidal tails and merge. Click to roll a new universe.")
    if entry:
        photo = (f'  <a href="{esc(entry.get("link") or "https://science.nasa.gov/apod/")}">'
                 f'<img src="{esc(entry["image"])}" width="48%" alt="{esc(entry.get("alt") or entry["title"])}"></a>\n')
    else:
        photo = ""
    sky = (
        '<p align="center">\n'
        + photo
        + f'  <a href="{esc(REROLL_URL)}"><img src="{RAW}/merger-{v}.webp" width="48%" alt="{esc(merger_alt)}"></a>\n'
        f'  <img src="{RAW}/plaque-{v}.svg" width="97%" alt="{esc(html.unescape(manifest["plaque_title"]))}">\n'
        "</p>\n"
        f'<p align="center"><a href="{esc(REROLL_URL)}"><img src="assets/chips/reroll.svg" height="40" '
        'alt="Roll a new universe"></a></p>'
    )
    return {
        "HERO": f'<img src="{RAW}/hero-{v}.svg" width="100%" alt="{esc(hero_alt)}">',
        "APOD": sky,
        "FOOTER": f'<img src="{RAW}/footer-{v}.svg" width="100%" alt="{esc(manifest["footer_title"])}">',
    }


def build(out: Path, day: dt.date, roll: int, entry: dict | None) -> dict:
    key = universe_key(day, roll)
    seed = seed_for(key)
    version = version_for(key, entry)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.iterdir():
        if old.is_file():
            old.unlink()
    hero_svg, hero_facts = hero.build(seed)
    (out / f"hero-{version}.svg").write_text(hero_svg, encoding="utf-8")
    merger_facts = merger.render(seed, out / f"merger-{version}.webp")
    plaque_svg = plaque(entry, merger_facts, version, roll)
    (out / f"plaque-{version}.svg").write_text(plaque_svg, encoding="utf-8")
    footer_svg = footer(seed, day)
    (out / f"footer-{version}.svg").write_text(footer_svg, encoding="utf-8")
    manifest = {
        "version": version, "day": day.isoformat(), "roll": roll, "seed": seed,
        "hero": hero_facts, "merger": {k: v for k, v in merger_facts.items() if k != "bytes"},
        "plaque_title": plaque_svg.split("<title>", 1)[1].split("</title>", 1)[0],
        "footer_title": html.unescape(footer_svg.split("<title>", 1)[1].split("</title>", 1)[0]),
        "apod": {k: (entry or {}).get(k) for k in ("date", "title")},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    (out / "README.md").write_text(
        f"# Daily art for {REPO}\n\nRebuilt every day by `.github/workflows/refresh.yml` (see `scripts/daily.py`) "
        "and force-pushed here as a single commit, so this branch never accumulates history.\n",
        encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", nargs="?", default="build", choices=["build", "bump-roll", "version"])
    ap.add_argument("--published", default="", help="manifest.json currently on the art branch")
    ap.add_argument("--out", default=str(ROOT / "build" / "daily"))
    ap.add_argument("--day", help="YYYY-MM-DD (default: today in Arizona)")
    args = ap.parse_args()
    day = dt.date.fromisoformat(args.day) if args.day else today()

    if args.command == "bump-roll":
        n = bump_roll(day)
        print(n)
        return 0 if n else 3

    entry = json.loads((ROOT / "data" / "cache" / "apod.json").read_text(encoding="utf-8"))
    roll = roll_count(day)
    version = version_for(universe_key(day, roll), entry)
    if args.command == "version":
        print(version)
        return 0

    published = json.loads(args.published) if args.published.strip() else None
    out = Path(args.out)
    if published and published.get("version") == version:
        print(f"daily art {version} is already published")
        manifest = published
    else:
        print(f"drawing daily art {version} (published: {published and published.get('version')})")
        manifest = build(out, day, roll, entry)
        for f in sorted(out.iterdir()):
            print(f"  {f.name}: {f.stat().st_size / 1000:.0f} kB")
    changed = readme.update(readme_blocks(manifest, entry))
    print("README updated" if changed else "README unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
