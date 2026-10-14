"""Refresh the live parts of the profile: the activity figure and NASA's picture.

Each source is fetched independently. A source that fails keeps its last
good data from data/cache/, so one flaky API never blanks a section.

    GITHUB_TOKEN=... python scripts/refresh.py
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sys
import urllib.request

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
        print(f"warning: {name}: {exc!r}; using cached data", file=sys.stderr)
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


def plausible_apod(entry: dict) -> dict:
    """The APOD API has been seen returning the site's logo and name instead of the picture."""
    image, title = entry.get("image") or "", (entry.get("title") or "").strip()
    if not image.startswith("https://") or "logo" in image.lower():
        raise RuntimeError(f"implausible APOD image {image!r}")
    if not title or "nasa science" in title.lower():
        raise RuntimeError(f"implausible APOD title {title!r}")
    return entry


def fetch_apod() -> dict:
    key = os.environ.get("NASA_API_KEY") or "DEMO_KEY"
    try:
        a = json.loads(http(f"https://api.nasa.gov/planetary/apod?thumbs=true&api_key={key}", timeout=40))
        image = a.get("url") if a.get("media_type") == "image" else a.get("thumbnail_url")
        return plausible_apod({"date": a["date"], "title": a["title"].strip(), "image": image or ""})
    except Exception as exc:  # noqa: BLE001
        print(f"warning: APOD API failed ({exc!r}); reading the APOD page instead", file=sys.stderr)
    # The API is often down; the APOD page carries the same picture.
    page = http("https://science.nasa.gov/apod/", timeout=40).decode("utf-8", "ignore")
    page = re.sub(r"<(script|style)\b.*?</\1>", "", page, flags=re.S)
    img = re.search(r'<img[^>]+src="(https://assets\.science\.nasa\.gov/[^"]*cds/apod/[^"]+)"', page)
    title = re.search(r'<h2 class="display-48[^"]*">([^<]+)</h2>', page)
    if not img or not title:
        raise RuntimeError("the APOD page layout changed; no image or title found")
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page)))
    date = re.search(r"Date:\s*([A-Z][a-z]+ \d{1,2}, \d{4})", text)
    return plausible_apod({
        "date": dt.datetime.strptime(date.group(1), "%B %d, %Y").date().isoformat() if date else dt.date.today().isoformat(),
        "title": html.unescape(title.group(1)).strip(),
        "image": html.unescape(img.group(1)),
    })


# --------------------------------------------------------------------------- the activity figure


def num(n: int) -> str:
    """SI-style digit grouping with a thin space: 3 151."""
    return f"{n:,}".replace(",", THIN)


def stats_figure(gh: dict) -> str:
    """Rolling-digit counters over a weekly activity line that draws itself."""
    fonts = Fonts()
    W, H, size = 1200, 300, 60
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
        cx, base = 150 + 300 * i, 104
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
    x0, x1, y0, y1 = 70, 1130, 190, 274
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


def apod_block(apod: dict | None) -> str:
    if not apod:
        return '<p align="center"><sub>NASA\'s picture of the day will be back on the next refresh.</sub></p>'
    return (
        '<p align="center">\n'
        f'  <a href="https://science.nasa.gov/apod/"><img src="{esc(apod["image"])}" width="86%" alt="{esc(apod["title"])}"></a>\n'
        f'  <br><sub><b>{html.escape(apod["title"], quote=False)}</b></sub>\n'
        "</p>"
    )


def main() -> int:
    gh = cached("github", fetch_github)
    apod = cached("apod", fetch_apod)
    if gh:
        write(GENERATED / "stats.svg", stats_figure(gh))
    changed = readme.update({"APOD": apod_block(apod)})
    print("README updated" if changed else "README unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
