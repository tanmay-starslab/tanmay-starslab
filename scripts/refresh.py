"""Refresh the live parts of the profile: the activity figure, NASA's picture
and the sky badges (tonight's moon, sunset in Tempe).

Each source is fetched independently. A source that fails keeps its last
good data from data/cache/, so one flaky API never blanks a section.

    GITHUB_TOKEN=... python scripts/refresh.py
"""

from __future__ import annotations

import datetime as dt
import html
import json
import math
import os
import sys
import urllib.request

import apod
import readme
from svgkit import ROOT, C, Fonts, document, esc, write

USER = "tanmay-starslab"
CACHE = ROOT / "data" / "cache"
GENERATED = ROOT / "assets" / "generated"
UA = "tanmay-starslab-profile-readme (+https://github.com/tanmay-starslab)"
THIN = " "


# --------------------------------------------------------------------------- fetching


def http(url: str, data: bytes | None = None, headers: dict | None = None, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def cached(name: str, fetch):
    """Run fetch(); on success store the result, on failure fall back to the stored copy."""
    path = CACHE / f"{name}.json"
    try:
        value = fetch()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        return value
    except Exception as exc:  # noqa: BLE001 - any failure means "use the cache"
        # An Actions annotation, so a fallback shows up on the run page instead of passing silently.
        print(f"::warning title={name} fetch failed::{exc!r}; using cached data", file=sys.stderr)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
        return None


GITHUB_QUERY = """
query($login: String!) {
  user(login: $login) {
    pullRequests { totalCount }
    repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) { totalCount }
    contributionsCollection {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
  }
}
"""


def fetch_github() -> dict:
    token = os.environ.get("STATS_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("no STATS_TOKEN or GITHUB_TOKEN in the environment")
    body = json.dumps({"query": GITHUB_QUERY, "variables": {"login": USER}}).encode()
    out = json.loads(http(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    ))
    if out.get("errors"):
        raise RuntimeError(out["errors"])
    user = out["data"]["user"]
    calendar = user["contributionsCollection"]["contributionCalendar"]
    return {
        "pull_requests": user["pullRequests"]["totalCount"],
        "repo_count": user["repositories"]["totalCount"],
        "total_contributions": calendar["totalContributions"],
        "days": [[d["date"], d["contributionCount"]] for w in calendar["weeks"] for d in w["contributionDays"]],
    }


APOD_STILL = GENERATED / "apod-still.jpg"


def fetch_apod() -> dict:
    """Today's entry from NASA's APOD feed (see apod.py); video days get a still frame."""
    return apod.fetch(APOD_STILL, "assets/generated/apod-still.jpg")


# --------------------------------------------------------------------------- the activity figure


def num(n: int) -> str:
    """SI-style digit grouping with a thin space: 3 151."""
    return f"{n:,}".replace(",", THIN)


def stats_figure(gh: dict) -> str:
    """Rolling-digit counters over a weekly activity line that draws itself."""
    fonts = Fonts()
    W, H, size = 1200, 228, 60
    days = gh["days"]
    active = sum(1 for _, c in days if c > 0)
    weeks = [sum(c for _, c in days[i : i + 7]) for i in range(0, len(days), 7)]
    counters = [
        (gh["total_contributions"], "contributions this year"),
        (active, "active days"),
        (gh["pull_requests"], "pull requests"),
        (gh["repo_count"], "public repositories"),
    ]
    cycle = 16.0
    css = [
        f"@keyframes draw{{0%{{stroke-dashoffset:1000}}22%{{stroke-dashoffset:0}}100%{{stroke-dashoffset:0}}}}"
        f".line{{stroke-dasharray:1000;animation:draw {cycle}s cubic-bezier(.3,.6,.3,1) infinite}}"
        f"@keyframes area{{0%,8%{{opacity:0}}26%,100%{{opacity:1}}}}.area{{animation:area {cycle}s ease-out infinite}}"
        "@keyframes peak{0%,100%{transform:scale(1);opacity:.9}50%{transform:scale(1.8);opacity:.25}}"
        ".peak{transform-box:fill-box;transform-origin:center;animation:peak 2s ease-in-out infinite}"
    ]
    defs = [
        f'<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{C.sky_top}"/>'
        f'<stop offset="1" stop-color="{C.sky}"/></linearGradient>'
        f'<linearGradient id="fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{C.violet}" stop-opacity=".45"/>'
        f'<stop offset="1" stop-color="{C.violet}" stop-opacity="0"/></linearGradient>'
        f'<linearGradient id="stroke" x1="0" x2="1"><stop offset="0" stop-color="{C.violet}"/>'
        f'<stop offset="1" stop-color="{C.gold}"/></linearGradient>'
    ]
    parts = []
    digit_w = fonts.width("rm", "0", size)
    col = 0
    for i, (value, label) in enumerate(counters):
        cx, base = 150 + 300 * i, 84
        text = num(value)
        x = cx - fonts.width("rm", text, size) / 2
        for ch in text:
            if not ch.isdigit():
                fonts.use("rm", ch)
                x += fonts.width("rm", ch, size)
                continue
            d = int(ch)
            final = (20 + d) * size
            defs.append(f'<clipPath id="c{col}"><rect x="{x - 2:.1f}" y="{base - size * 0.82:.1f}" '
                        f'width="{digit_w + 4:.1f}" height="{size * 1.04:.1f}"/></clipPath>')
            stack = "".join(
                fonts.text(x, base + k * size, str(k % 10), "rm", size, C.ink) for k in range(30)
            )
            delay = 0.25 + 0.09 * col
            css.append(
                f"@keyframes r{col}{{0%,{delay / cycle * 100:.2f}%{{transform:translateY(0)}}"
                f"{(delay + 2.2) / cycle * 100:.2f}%,100%{{transform:translateY(-{final}px)}}}}"
            )
            parts.append(
                f'<g clip-path="url(#c{col})"><g style="transform:translateY(-{final}px);'
                f'animation:r{col} {cycle}s cubic-bezier(.2,.75,.25,1) infinite">{stack}</g></g>'
            )
            x += digit_w
            col += 1
        parts.append(fonts.text(cx, base + 36, label, "it", 20, C.muted, "middle"))

    # Weekly contributions, drawn like a spectrum.
    x0, x1, y0, y1 = 70, 1130, 140, 206
    top = max(weeks) or 1
    pts = [(x0 + (x1 - x0) * i / (len(weeks) - 1), y1 - (y1 - y0) * v / top) for i, v in enumerate(weeks)]
    d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f}" + "".join(
        f" C{(ax + bx) / 2:.1f},{ay:.1f} {(ax + bx) / 2:.1f},{by:.1f} {bx:.1f},{by:.1f}"
        for (ax, ay), (bx, by) in zip(pts, pts[1:])
    )
    pk = max(range(len(weeks)), key=lambda i: weeks[i])
    parts.append(f'<line x1="{x0}" y1="{y1}" x2="{x1}" y2="{y1}" stroke="{C.faint}"/>')
    parts.append(f'<path class="area" d="{d} L{x1},{y1} L{x0},{y1} Z" fill="url(#fill)"/>')
    parts.append(f'<path class="line" d="{d}" pathLength="1000" fill="none" stroke="url(#stroke)" stroke-width="2.4" stroke-linejoin="round"/>')
    parts.append(f'<circle class="peak" cx="{pts[pk][0]:.1f}" cy="{pts[pk][1]:.1f}" r="6" fill="{C.gold}"/>')
    parts.append(f'<circle cx="{pts[pk][0]:.1f}" cy="{pts[pk][1]:.1f}" r="3.5" fill="#FFFFFF"/>')

    body = (f'<defs>{"".join(defs)}</defs><rect width="{W}" height="{H}" rx="22" fill="url(#bg)"/>' + "".join(parts))
    title = ", ".join(f"{num(v)} {label}" for v, label in counters)
    return document(W, H, body, fonts, "".join(css), title=f"GitHub activity: {title}")


# --------------------------------------------------------------------------- README blocks


MERGER = (
    '<img src="assets/merger.webp" width="48%" alt="Two disk galaxies collide, throw out tidal tails '
    'and merge: a simulation written for this page.">'
)


def apod_block(entry: dict | None) -> str:
    """Today's real sky (NASA's picture of the day) beside a simulated one."""
    if not entry:
        return f'<p align="center">\n  {MERGER}\n</p>'
    link = entry.get("link") or "https://science.nasa.gov/apod/"
    what = "NASA APOD video, click to play" if entry.get("kind") in ("video", "youtube") else "NASA APOD"
    return (
        '<p align="center">\n'
        f'  <a href="{esc(link)}"><img src="{esc(entry["image"])}" width="48%" alt="{esc(entry.get("alt") or entry["title"])}"></a>\n'
        f"  {MERGER}\n"
        f'  <br><sub>real: <b>{html.escape(entry["title"], quote=False)}</b> ({what})'
        " &nbsp;·&nbsp; simulated: two galaxies merging</sub>\n"
        "</p>"
    )


# --------------------------------------------------------------------------- sky badges

TEMPE = (33.4255, -111.9400)
MST = dt.timezone(dt.timedelta(hours=-7), "MST")  # Arizona keeps standard time all year
SYNODIC = 29.530588853
NEW_MOON_JD = 2451550.1  # 2000-01-06 18:14 UTC


def julian_day(t: dt.datetime) -> float:
    return t.timestamp() / 86400.0 + 2440587.5


def moon_tonight(day: dt.date) -> tuple[float, float, str]:
    """Phase (0 = new, 0.5 = full), illuminated fraction and name at 9 p.m. in Tempe.

    A mean synodic month is good to about half a day, plenty for a name.
    """
    t = dt.datetime.combine(day, dt.time(21, 0), MST)
    phase = ((julian_day(t) - NEW_MOON_JD) / SYNODIC) % 1.0
    lit = (1 - math.cos(2 * math.pi * phase)) / 2
    names = [(0.034, "new moon"), (0.216, "waxing crescent"), (0.284, "first quarter"), (0.466, "waxing gibbous"),
             (0.534, "full moon"), (0.716, "waning gibbous"), (0.784, "last quarter"), (0.966, "waning crescent"),
             (1.001, "new moon")]
    return phase, lit, next(name for limit, name in names if phase < limit)


def sunset(day: dt.date, lat: float, lon: float) -> dt.datetime:
    """Sunset from the standard sunrise equation (good to within a few minutes)."""
    jd = julian_day(dt.datetime.combine(day, dt.time(12, 0), MST))
    n = round(jd - 2451545.0 + 0.0008)
    j_star = n - lon / 360.0
    m = math.radians((357.5291 + 0.98560028 * j_star) % 360)
    c = 1.9148 * math.sin(m) + 0.0200 * math.sin(2 * m) + 0.0003 * math.sin(3 * m)
    lam = math.radians((math.degrees(m) + c + 180 + 102.9372) % 360)
    transit = 2451545.0 + j_star + 0.0053 * math.sin(m) - 0.0069 * math.sin(2 * lam)
    dec = math.asin(math.sin(lam) * math.sin(math.radians(23.4397)))
    phi = math.radians(lat)
    cos_w = (math.sin(math.radians(-0.833)) - math.sin(phi) * math.sin(dec)) / (math.cos(phi) * math.cos(dec))
    j_set = transit + math.degrees(math.acos(max(-1.0, min(1.0, cos_w)))) / 360.0
    return dt.datetime.fromtimestamp((j_set - 2440587.5) * 86400, dt.timezone.utc).astimezone(MST)


def badge(label: str, value: str, color: str, dark_text: bool, icon: str = "", title: str = "") -> str:
    """A flat-square badge drawn to sit beside the shields.io ones in the same row."""
    char = 6.7  # Verdana at 11 px, as shields.io uses
    icon_w = 16 if icon else 0
    lw = round(len(label) * char + 12)
    vw = round(len(value) * char + 12 + icon_w)
    text = "#16161A" if dark_text else "#FFFFFF"
    body = (
        f'<rect width="{lw}" height="20" fill="#16161A"/><rect x="{lw}" width="{vw}" height="20" fill="{color}"/>'
        f'<g font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11" text-rendering="geometricPrecision">'
        f'<text x="{lw / 2:.1f}" y="14" text-anchor="middle" fill="#FFFFFF">{esc(label)}</text>'
        f'<text x="{lw + icon_w + (vw - icon_w) / 2:.1f}" y="14" text-anchor="middle" fill="{text}">{esc(value)}</text></g>'
        + (f'<g transform="translate({lw + 11} 10)">{icon}</g>' if icon else "")
    )
    return document(lw + vw, 20, body, None, "", title=title or f"{label}: {value}")


def moon_icon(phase: float) -> str:
    """A 12 px moon with the terminator drawn as an ellipse."""
    r = 5.5
    k = math.cos(2 * math.pi * phase)  # 1 at new moon, -1 at full
    waxing = phase < 0.5
    # The lit limb is on the right while waxing, on the left while waning.
    limb = f"M0,{-r} A{r},{r} 0 0 {1 if waxing else 0} 0,{r}"
    term = f"A{abs(k) * r:.2f},{r} 0 0 {(0 if waxing else 1) if k > 0 else (1 if waxing else 0)} 0,{-r} Z"
    return (f'<circle r="{r}" fill="#3A3A44"/><path d="{limb} {term}" fill="#FFF6DD"/>'
            f'<circle r="{r}" fill="none" stroke="#16161A" stroke-width=".6"/>')


def sky_badges(day: dt.date) -> dict[str, str]:
    phase, lit, name = moon_tonight(day)
    sun = sunset(day, *TEMPE)
    clock = sun.strftime("%I:%M %p").lstrip("0").lower()
    return {
        "moon.svg": badge("moon tonight", f"{name} {round(lit * 100)}%", "#E6B566", True, moon_icon(phase)),
        "sunset.svg": badge("Tempe sunset", clock, "#F08BA6", True, title=f"Sunset in Tempe, Arizona: {clock}"),
    }


def main() -> int:
    gh = cached("github", fetch_github)
    sky = cached("apod", fetch_apod)
    if gh:
        write(GENERATED / "stats.svg", stats_figure(gh))
    for name, svg in sky_badges(dt.datetime.now(MST).date()).items():
        write(GENERATED / name, svg)
    changed = readme.update({"APOD": apod_block(sky)})
    print("README updated" if changed else "README unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
