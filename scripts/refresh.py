"""Refresh every live part of the profile: figures and README blocks.

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
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import readme
from svgkit import ROOT, THEMES, Fonts, Theme, document, esc, write

USER = "tanmay-starslab"
CHESS_USER = "voyager972"
CACHE = ROOT / "data" / "cache"
GENERATED = ROOT / "assets" / "generated"
UA = "tanmay-starslab-profile-readme (+https://github.com/tanmay-starslab)"
THIN = " "


# --------------------------------------------------------------------------- fetching


def http(url: str, data: bytes | None = None, headers: dict | None = None, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def http_json(url: str, **kwargs) -> dict:
    return json.loads(http(url, **kwargs))


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
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC,
                 orderBy: {field: PUSHED_AT, direction: DESC}) {
      totalCount
      nodes { name description url pushedAt stargazerCount primaryLanguage { name } }
    }
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
    out = http_json(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    if out.get("errors"):
        raise RuntimeError(out["errors"])
    user = out["data"]["user"]
    days = [d for w in user["contributionsCollection"]["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    return {
        "pull_requests": user["pullRequests"]["totalCount"],
        "repo_count": user["repositories"]["totalCount"],
        "repos": [
            {
                "name": r["name"],
                "description": r["description"] or "",
                "url": r["url"],
                "pushed_at": r["pushedAt"],
                "stars": r["stargazerCount"],
                "language": (r["primaryLanguage"] or {}).get("name"),
            }
            for r in user["repositories"]["nodes"]
        ],
        "total_contributions": user["contributionsCollection"]["contributionCalendar"]["totalContributions"],
        "days": [[d["date"], d["contributionCount"]] for d in days],
    }


def fetch_chess() -> dict:
    stats = http_json(f"https://api.chess.com/pub/player/{CHESS_USER}/stats")
    modes = {}
    for key, label in (("chess_bullet", "Bullet"), ("chess_blitz", "Blitz"), ("chess_rapid", "Rapid"), ("chess_daily", "Daily")):
        if key in stats:
            s = stats[key]
            modes[label] = {
                "rating": s["last"]["rating"],
                "best": s.get("best", {}).get("rating"),
                "win": s["record"]["win"],
                "draw": s["record"]["draw"],
                "loss": s["record"]["loss"],
            }
    return {
        "modes": modes,
        "tactics_best": stats.get("tactics", {}).get("highest", {}).get("rating"),
        "rush_best": stats.get("puzzle_rush", {}).get("best", {}).get("score"),
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
        a = http_json(f"https://api.nasa.gov/planetary/apod?thumbs=true&api_key={key}", timeout=40)
        image = a.get("url") if a.get("media_type") == "image" else a.get("thumbnail_url")
        if not image:
            raise RuntimeError("APOD entry has no image or thumbnail")
        return plausible_apod({
            "date": a["date"],
            "title": a["title"].strip(),
            "image": image,
            "explanation": a.get("explanation", "").strip(),
            "credit": re.sub(r"\s+", " ", a.get("copyright", "")).strip(),
            "link": "https://science.nasa.gov/apod/",
        })
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
    explanation = re.search(r"Explanation:\s*(.+?)\s*Tomorrow.s picture:", text)
    credit = re.search(r"Credit:\s*(.+?)\s*Authors", text)
    date = re.search(r"Date:\s*([A-Z][a-z]+ \d{1,2}, \d{4})", text)
    return plausible_apod({
        "date": dt.datetime.strptime(date.group(1), "%B %d, %Y").date().isoformat() if date else dt.date.today().isoformat(),
        "title": html.unescape(title.group(1)).strip(),
        "image": html.unescape(img.group(1)),
        # The page puts spaces inside link text ("( M44 )"); close them up.
        "explanation": re.sub(r"\s+([,.;:)’'])", r"\1", re.sub(r"\(\s+", "(", explanation.group(1))) if explanation else "",
        "credit": re.sub(r"\s+([,.;:)])", r"\1", re.sub(r"\(\s+", "(", credit.group(1))) if credit else "",
        "link": "https://science.nasa.gov/apod/",
    })


ATOM = "{http://www.w3.org/2005/Atom}"
ARXIV_EXTRA_QUERY = 'au:"Singh, Tanmay" AND au:Borthakur'


def fetch_papers() -> list[dict]:
    """Paper metadata from arXiv for the curated list, plus any new paper with my advisor."""
    papers = json.loads((ROOT / "data" / "papers.json").read_text(encoding="utf-8"))
    ids = [p["arxiv"] for p in papers if p.get("arxiv")]
    found = http(
        "https://export.arxiv.org/api/query?"
        + urllib.parse.urlencode({"search_query": ARXIV_EXTRA_QUERY, "max_results": 25})
    )
    for entry in ET.fromstring(found).iter(f"{ATOM}entry"):
        arxiv_id = entry.findtext(f"{ATOM}id", "").rsplit("/", 1)[-1].split("v")[0]
        if arxiv_id and arxiv_id not in ids:
            ids.append(arxiv_id)
            papers.append({"arxiv": arxiv_id})
    meta = {}
    feed = http("https://export.arxiv.org/api/query?" + urllib.parse.urlencode({"id_list": ",".join(ids), "max_results": len(ids)}))
    for entry in ET.fromstring(feed).iter(f"{ATOM}entry"):
        arxiv_id = entry.findtext(f"{ATOM}id", "").rsplit("/", 1)[-1].split("v")[0]
        meta[arxiv_id] = {
            "title": re.sub(r"\s+", " ", entry.findtext(f"{ATOM}title", "")).strip(),
            "authors": [a.findtext(f"{ATOM}name", "") for a in entry.iter(f"{ATOM}author")],
            "year": entry.findtext(f"{ATOM}published", "")[:4],
        }
    out = []
    for p in papers:
        merged = {**meta.get(p.get("arxiv", ""), {}), **p}
        if merged.get("title"):
            out.append(merged)
    return sorted(out, key=lambda p: (p.get("year", ""), p.get("arxiv", "")), reverse=True)


# --------------------------------------------------------------------------- formatting


def num(n: int) -> str:
    """SI-style digit grouping with a thin space: 3 151."""
    return f"{n:,}".replace(",", THIN)


def figure_caption(fonts: Fonts, x: float, y: float, label: str, text: str, theme: Theme) -> str:
    return fonts.rich(x, y, [("bf", f"{label} "), ("rm", text)], 19, theme.muted)


# --------------------------------------------------------------------------- figures


def streaks(days: list[list]) -> tuple[int, int]:
    longest = run = active = 0
    for _, count in days:
        if count > 0:
            run += 1
            active += 1
            longest = max(longest, run)
        else:
            run = 0
    return longest, active


def stats_figure(gh: dict, theme: Theme) -> str:
    fonts = Fonts()
    W, H = 1200, 450
    days = gh["days"]
    longest, active = streaks(days)
    weeks: list[tuple[str, int]] = []
    for i in range(0, len(days), 7):
        chunk = days[i : i + 7]
        weeks.append((chunk[0][0], sum(c for _, c in chunk)))
    peak_i = max(range(len(weeks)), key=lambda i: weeks[i][1])

    tiles = [
        (num(gh["total_contributions"]), "contributions, past year"),
        (num(gh["pull_requests"]), "pull requests opened"),
        (num(active), "active days, past year"),
        (f"{longest} days", "longest streak"),
        (num(gh["repo_count"]), "public repositories"),
        (num(weeks[peak_i][1]), "in the busiest week"),
    ]
    parts = [f'<rect width="{W}" height="{H}" rx="18" fill="{theme.surface}"/>']
    for i, (value, label) in enumerate(tiles):
        x = 56 + (i % 2) * 262
        y = 104 + (i // 2) * 108
        parts.append(fonts.text(x, y, value, "rm", 50, theme.ink))
        parts.append(fonts.text(x + 2, y + 30, label, "rm", 19, theme.muted))

    # Step plot of weekly contributions, drawn like a spectrum.
    px0, px1, py0, py1 = 650, 1150, 70, 340
    ymax = max(c for _, c in weeks) or 1
    step = next(s for s in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000) if ymax / s <= 4)
    ytop = step * (int(ymax / step) + 1)
    sx = lambda i: px0 + (px1 - px0) * i / len(weeks)  # noqa: E731
    sy = lambda v: py1 - (py1 - py0) * v / ytop  # noqa: E731
    for v in range(0, ytop + 1, step):
        y = sy(v)
        stroke = theme.muted if v == 0 else theme.faint
        parts.append(f'<line x1="{px0}" y1="{y:.1f}" x2="{px1}" y2="{y:.1f}" stroke="{stroke}" stroke-width="1"/>')
        parts.append(fonts.text(px0 - 12, y + 6, num(v), "rm", 17, theme.muted, "end"))
    seen_months = set()
    for i, (start, _) in enumerate(weeks):
        d = dt.date.fromisoformat(start)
        key = (d.year, d.month)
        # Label a month at the first week that starts inside it.
        if key not in seen_months and d.day <= 7 and i > 0:
            seen_months.add(key)
            x = sx(i)
            parts.append(f'<line x1="{x:.1f}" y1="{py1}" x2="{x:.1f}" y2="{py1 + 6}" stroke="{theme.muted}" stroke-width="1"/>')
            parts.append(fonts.text(x, py1 + 26, d.strftime("%b"), "rm", 17, theme.muted, "middle"))
    d = f"M{sx(0):.1f},{sy(0):.1f}"
    for i, (_, v) in enumerate(weeks):
        d += f" V{sy(v):.1f} H{sx(i + 1):.1f}"
    d_area = d + f" V{sy(0):.1f} Z"
    parts.append(f'<path d="{d_area}" fill="{theme.accent}" fill-opacity="0.14"/>')
    parts.append(f'<path d="{d}" fill="none" stroke="{theme.accent}" stroke-width="2" stroke-linejoin="round"/>')

    # Label the busiest week the way a paper labels an emission line.
    pk_x = (sx(peak_i) + sx(peak_i + 1)) / 2
    pk_y = sy(weeks[peak_i][1]) - 10
    start = dt.date.fromisoformat(weeks[peak_i][0])
    label = f"week of {start.strftime('%b')} {start.day}"
    anchor = "end" if pk_x > px1 - 120 else ("start" if pk_x < px0 + 120 else "middle")
    lx = pk_x + (8 if anchor == "start" else -8 if anchor == "end" else 0)
    parts.append(f'<line x1="{pk_x:.1f}" y1="{pk_y:.1f}" x2="{pk_x:.1f}" y2="{pk_y - 12:.1f}" stroke="{theme.ink}" stroke-width="1"/>')
    parts.append(fonts.text(lx, pk_y - 20, label, "it", 18, theme.ink, anchor))
    parts.append(fonts.text(px0 - 40, py0 - 30, "contributions per week", "it", 17, theme.muted))

    parts.append(
        figure_caption(
            fonts, 56, H - 30, "Figure 2.",
            "My GitHub contributions over the past year, one step per week. Refreshed daily.", theme,
        )
    )
    return document(W, H, "".join(parts), fonts, title="GitHub activity over the past year")


def languages_figure(gh: dict, theme: Theme) -> str:
    fonts = Fonts()
    counts: dict[str, int] = {}
    for r in gh["repos"]:
        if r["language"] and r["name"] != USER:
            counts[r["language"]] = counts.get(r["language"], 0) + 1
    rows = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:6]
    W = 1200
    H = 70 + 46 * len(rows) + 70
    parts = [f'<rect width="{W}" height="{H}" rx="18" fill="{theme.surface}"/>']
    top = max((c for _, c in rows), default=1)
    bx0, bx1 = 300, 1020
    for i, (lang, count) in enumerate(rows):
        y = 70 + 46 * i
        w = (bx1 - bx0) * count / top
        parts.append(fonts.text(bx0 - 20, y + 7, lang, "rm", 21, theme.ink, "end"))
        # Bar anchored at the baseline with a rounded data end.
        parts.append(
            f'<path d="M{bx0},{y - 7} H{bx0 + w - 4:.1f} a4,4 0 0 1 4,4 V{y + 3} a4,4 0 0 1 -4,4 H{bx0} Z" fill="{theme.accent}"/>'
        )
        noun = "repository" if count == 1 else "repositories"
        parts.append(fonts.text(bx0 + w + 14, y + 7, f"{count} {noun}", "rm", 19, theme.muted))
    parts.append(f'<line x1="{bx0}" y1="48" x2="{bx0}" y2="{70 + 46 * len(rows) - 24}" stroke="{theme.muted}" stroke-width="1"/>')
    parts.append(
        figure_caption(fonts, 56, H - 30, "Figure 3.", "Main language of each of my public repositories, forks excluded.", theme)
    )
    return document(W, H, "".join(parts), fonts, title="Languages of my public repositories")


def chess_figure(chess: dict, theme: Theme) -> str:
    fonts = Fonts()
    W, H = 1200, 420
    parts = [f'<rect width="{W}" height="{H}" rx="18" fill="{theme.surface}"/>']
    colors = {"won": theme.accent, "drawn": theme.neutral, "lost": theme.gold}

    # Legend: three series, so identity is never colour alone.
    lx = W - 56
    for name in reversed(list(colors)):
        w = fonts.width("rm", name, 18)
        parts.append(fonts.text(lx, 52, name, "rm", 18, theme.muted, "end"))
        parts.append(f'<rect x="{lx - w - 22:.1f}" y="39" width="14" height="14" rx="3" fill="{colors[name]}"/>')
        lx -= w + 48

    modes = list(chess["modes"].items())
    col_w = (W - 112) / max(len(modes), 1)
    for i, (mode, s) in enumerate(modes):
        x = 56 + i * col_w
        bar_w = col_w - 48
        parts.append(fonts.text(x, 104, mode, "rm", 21, theme.muted))
        parts.append(fonts.text(x - 2, 168, num(s["rating"]), "rm", 58, theme.ink))
        if s.get("best"):
            parts.append(fonts.text(x, 202, f"best {num(s['best'])}", "it", 19, theme.muted))
        total = s["win"] + s["draw"] + s["loss"]
        if total:
            seg_x = x
            segs = [("won", s["win"]), ("drawn", s["draw"]), ("lost", s["loss"])]
            visible = [(k, v) for k, v in segs if v > 0]
            gap = 2 * (len(visible) - 1)
            for j, (k, v) in enumerate(visible):
                w = (bar_w - gap) * v / total
                r = 4 if j in (0, len(visible) - 1) else 0
                parts.append(
                    f'<rect x="{seg_x:.1f}" y="234" width="{max(w, 1):.1f}" height="12" rx="{min(r, w / 2):.1f}" fill="{colors[k]}"/>'
                )
                seg_x += w + 2
            parts.append(fonts.text(x, 276, f"{num(s['win'])} won, {num(s['draw'])} drawn,", "rm", 18, theme.muted))
            parts.append(fonts.text(x, 300, f"{num(s['loss'])} lost", "rm", 18, theme.muted))

    extras = []
    if chess.get("tactics_best"):
        extras.append(f"Highest puzzle rating {num(chess['tactics_best'])}")
    if chess.get("rush_best"):
        extras.append(f"best Puzzle Rush score {chess['rush_best']}")
    if extras:
        parts.append(fonts.text(56, 348, ", ".join(extras) + ".", "rm", 20, theme.ink))
    parts.append(
        figure_caption(
            fonts, 56, H - 30, "Figure 4.",
            f"My chess.com ratings ({CHESS_USER}) for each time control, with best-ever rating and record. Refreshed daily.",
            theme,
        )
    )
    return document(W, H, "".join(parts), fonts, title="Chess.com ratings")


# --------------------------------------------------------------------------- README blocks


def text(s: str) -> str:
    """Escape for HTML text content (quotes can stay as they are)."""
    return html.escape(s, quote=False)


def short_author(name: str) -> str:
    parts = name.split()
    if len(parts) < 2:
        return name
    initials = " ".join(p[0] + "." for p in parts[:-1])
    return f"{parts[-1]}, {initials}"


def papers_block(papers: list[dict]) -> str:
    lines = []
    for p in papers:
        authors = [short_author(a) for a in p.get("authors", [])]
        me = authors.index("Singh, T.") if "Singh, T." in authors else None
        if len(authors) > 5:
            # Long lists: first three, then me if I am further down, then et al.
            authors = authors[:3] + (["Singh, T."] if me is not None and me >= 3 else []) + ["et al."]
        authors = [f"**{a}**" if a == "Singh, T." else a for a in authors]
        title = re.sub(r"\$([^$]+)\$", r"\1", p["title"])
        where = p.get("journal") or (f"arXiv:{p['arxiv']}" if p.get("arxiv") else "")
        links = []
        if p.get("arxiv"):
            links.append(f"[abstract](https://arxiv.org/abs/{p['arxiv']})")
            links.append(f"[PDF](https://arxiv.org/pdf/{p['arxiv']})")
        if p.get("doi"):
            links.append(f"[journal](https://doi.org/{p['doi']})")
        tail = f" {', '.join(links)}" if links else ""
        lines.append(f"1. {', '.join(authors)} ({p.get('year', '')}). <em>{esc(title)}</em>. {where}.{tail}")
    return "\n".join(lines)


def apod_block(apod: dict | None) -> str:
    if not apod:
        return "_NASA's picture of the day could not be loaded this morning. It will be back on the next refresh._"
    excerpt = ""
    for sentence in re.split(r"(?<=[.!?])\s+", apod.get("explanation", "")):
        if excerpt and len(excerpt) + len(sentence) > 330:
            break
        excerpt += sentence + " "
    excerpt = excerpt.strip()
    credit = f"<br><sub>Image credit: {text(apod['credit'])}</sub>" if apod.get("credit") else ""
    date = dt.date.fromisoformat(apod["date"])
    return (
        "<table><tr>\n"
        f'<td width="50%"><a href="{apod["link"]}"><img src="{esc(apod["image"])}" width="100%" alt="{esc(apod["title"])}"></a></td>\n'
        f'<td width="50%"><b>{text(apod["title"])}</b><br><sub>{date.strftime("%B")} {date.day}, {date.year}</sub><br><br>'
        f"{text(excerpt)}{' ' if excerpt else ''}"
        f'<a href="{apod["link"]}">Read more on APOD</a>.{credit}</td>\n'
        "</tr></table>"
    )


def recent_block(gh: dict | None) -> str:
    if not gh:
        return "_Recent activity could not be loaded._"
    rows = []
    for r in [r for r in gh["repos"] if r["name"] != USER][:5]:
        pushed = dt.datetime.fromisoformat(r["pushed_at"].replace("Z", "+00:00")).date()
        desc = r["description"].strip().rstrip(".") or "no description yet"
        if len(desc) > 110:
            # Prefer a whole first sentence to a cut-off one.
            first = re.split(r"(?<=[.!?])\s", desc)[0].rstrip(".")
            desc = first + "." if len(first) <= 110 else desc[:107].rsplit(" ", 1)[0] + "…"
        else:
            desc += "."
        lang = f" <sub>{text(r['language'])}</sub>" if r["language"] else ""
        rows.append(f"- [**{r['name']}**]({r['url']}){lang}: {text(desc)} <sub>Last push {pushed.strftime('%b')} {pushed.day}.</sub>")
    return "\n".join(rows)


def main() -> int:
    gh = cached("github", fetch_github)
    chess = cached("chess", fetch_chess)
    apod = cached("apod", fetch_apod)
    papers = cached("papers", fetch_papers)

    for theme in THEMES:
        if gh:
            write(GENERATED / f"stats-{theme.name}.svg", stats_figure(gh, theme))
            write(GENERATED / f"languages-{theme.name}.svg", languages_figure(gh, theme))
        if chess:
            write(GENERATED / f"chess-ratings-{theme.name}.svg", chess_figure(chess, theme))

    blocks = {"APOD": apod_block(apod), "RECENT": recent_block(gh)}
    if papers:
        blocks["PAPERS"] = papers_block(papers)
    changed = readme.update(blocks)
    print("README updated" if changed else "README unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
