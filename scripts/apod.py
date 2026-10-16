"""NASA's Astronomy Picture of the Day, read from NASA's own feed.

The feed (science.nasa.gov/feed/apod-basic/) is the source of truth: every
entry carries its own date, title, permalink and media. Two rules keep the
profile honest:

* an entry's date always comes from the source; nothing here ever falls back
  to "today" (that once labelled yesterday's picture as today's and hid a
  stale profile behind a fresh-looking date);
* video days are real days: the still is a frame taken from the video, so
  the README always shows the current entry.
"""

from __future__ import annotations

import datetime as dt
import email.utils
import html
import json
import os
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

FEED = "https://science.nasa.gov/feed/apod-basic/"
API = "https://api.nasa.gov/planetary/apod?thumbs=true&api_key={key}"
NS = {"apod": "https://science.nasa.gov/apod/", "content": "http://purl.org/rss/1.0/modules/content/"}
EASTERN = dt.timezone(dt.timedelta(hours=-4))  # APOD dates follow US Eastern; -4 or -5 both land on the same date at 04:05 UTC


class StaleOrBroken(RuntimeError):
    """The source gave us something we refuse to publish."""


def entry_date(item: ET.Element) -> dt.date:
    """The date the entry is for, read from the entry itself, never assumed."""
    discussion = item.findtext("apod:discussion", "", NS)
    m = re.search(r"date=(\d{6})", discussion)
    if m:
        return dt.datetime.strptime(m.group(1), "%y%m%d").date()
    m = re.search(r"apod-(\d{4})-([a-z]+)-(\d{1,2})-", item.findtext("link", ""))
    if m:
        return dt.datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%Y %B %d").date()
    pub = item.findtext("pubDate", "")
    if pub:
        return email.utils.parsedate_to_datetime(pub).astimezone(EASTERN).date()
    raise StaleOrBroken(f"feed entry {item.findtext('title')!r} carries no date")


def parse_feed(raw: bytes) -> list[dict]:
    """Every entry in the feed, newest first, with its media classified."""
    entries = []
    for item in ET.fromstring(raw).iter("item"):
        title = html.unescape((item.findtext("title") or "").strip())
        encoded = item.findtext("content:encoded", "", NS)
        hd = (item.findtext("apod:hdurl", "", NS) or "").strip()
        mp4 = re.search(r"https://[^\"'\s<>]+\.mp4", encoded)
        youtube = re.search(r"(?:youtube(?:-nocookie)?\.com/embed/|youtu\.be/)([\w-]{11})", encoded)
        entry = {
            "date": entry_date(item).isoformat(),
            "title": title,
            "link": (item.findtext("link") or "").strip(),
            "alt": html.unescape((item.findtext("apod:alt", "", NS) or title).strip()),
        }
        if hd:
            # A sensible display size instead of the full-resolution original.
            entry.update(kind="image", image=re.sub(r"\?.*$", "", hd) + "?w=1280&h=1280&fit=clip")
        elif mp4:
            entry.update(kind="video", video=mp4.group(0))
        elif youtube:
            entry.update(kind="youtube", image=f"https://img.youtube.com/vi/{youtube.group(1)}/hqdefault.jpg")
        else:
            entry.update(kind="other")
        entries.append(entry)
    entries.sort(key=lambda e: e["date"], reverse=True)
    return entries


def plausible(entry: dict) -> dict:
    """Refuse things that are clearly not a picture of the day (the API once returned NASA's logo)."""
    title = entry.get("title", "")
    image = entry.get("image", "")
    if not title or "nasa science" in title.lower():
        raise StaleOrBroken(f"implausible APOD title {title!r}")
    if not image or "logo" in image.lower():
        raise StaleOrBroken(f"implausible APOD image {image!r}")
    dt.date.fromisoformat(entry["date"])
    return entry


def video_still(url: str, out: Path) -> None:
    """Grab a frame a few seconds into the video and mark it with a play button.

    The video is downloaded first and ffmpeg reads the local file: on GitHub's
    runners ffmpeg reading the URL directly failed without saying why.
    """
    import shutil
    from urllib.request import Request, urlopen

    import imageio_ffmpeg
    from PIL import Image, ImageDraw

    exe = imageio_ffmpeg.get_ffmpeg_exe()
    with tempfile.TemporaryDirectory() as tmp:
        clip, frame = Path(tmp) / "clip.mp4", Path(tmp) / "frame.png"
        with urlopen(Request(url, headers={"User-Agent": "tanmay-starslab-profile-readme"}), timeout=180) as resp, \
                open(clip, "wb") as fh:
            shutil.copyfileobj(resp, fh)
        errors = []
        for offset in ("8", "2", "0"):
            proc = subprocess.run(
                [exe, "-y", "-loglevel", "warning", "-ss", offset, "-i", str(clip), "-frames:v", "1",
                 "-vf", "scale=1280:-2", str(frame)],
                capture_output=True, text=True, timeout=180,
            )
            if proc.returncode == 0 and frame.exists():
                break
            errors.append(f"at {offset}s: exit {proc.returncode}: {proc.stderr.strip()[-300:]}")
        else:
            raise StaleOrBroken(f"could not read a frame from {url} ({clip.stat().st_size} bytes): {' | '.join(errors)}")
        img = Image.open(frame).convert("RGB")
        draw = ImageDraw.Draw(img, "RGBA")
        w, h = img.size
        r = min(w, h) // 9
        cx, cy = w // 2, h // 2
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(10, 10, 12, 150), outline=(255, 255, 255, 220), width=max(2, r // 14))
        t = r * 0.42
        draw.polygon([(cx - t * 0.7, cy - t), (cx - t * 0.7, cy + t), (cx + t, cy)], fill=(255, 255, 255, 235))
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out, "JPEG", quality=82, optimize=True)


def from_feed(still_path: Path, still_url: str) -> dict:
    from urllib.request import Request, urlopen

    with urlopen(Request(FEED, headers={"User-Agent": "tanmay-starslab-profile-readme"}), timeout=40) as resp:
        entries = parse_feed(resp.read())
    if not entries:
        raise StaleOrBroken("the APOD feed has no entries")
    newest = entries[0]
    if newest["kind"] == "video":
        video_still(newest["video"], still_path)
        newest["image"] = still_url
    elif newest["kind"] == "other":
        # No image we can show for today's entry: show the newest one we can,
        # under its own date and title (never relabelled as today's).
        newest = next(e for e in entries if e["kind"] in ("image", "youtube"))
    return plausible(newest)


def from_api() -> dict:
    from urllib.request import Request, urlopen

    key = os.environ.get("NASA_API_KEY") or "DEMO_KEY"
    with urlopen(Request(API.format(key=key), headers={"User-Agent": "tanmay-starslab-profile-readme"}), timeout=40) as resp:
        a = json.loads(resp.read())
    image = a.get("url") if a.get("media_type") == "image" else a.get("thumbnail_url")
    return plausible({
        "date": a["date"], "title": a["title"].strip(), "image": image or "",
        "link": "https://science.nasa.gov/apod/", "kind": a.get("media_type", "image"), "alt": a["title"].strip(),
    })


def fetch(still_path: Path, still_url: str) -> dict:
    """Today's entry from the feed, with the API as a fallback. Raises if both fail."""
    try:
        return from_feed(still_path, still_url)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=APOD feed failed::{exc!r}; trying the APOD API", file=sys.stderr)
    return from_api()


def newest_entry() -> dict:
    """The newest entry NASA has published, for the watchdog's end-to-end check."""
    from urllib.request import Request, urlopen

    with urlopen(Request(FEED, headers={"User-Agent": "tanmay-starslab-profile-watchdog"}), timeout=40) as resp:
        entries = parse_feed(resp.read())
    if not entries:
        raise StaleOrBroken("the APOD feed has no entries")
    return entries[0]
