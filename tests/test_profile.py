"""Regression tests for the parts of the profile that have broken before.

    python -m unittest discover -s tests

The fixture is a trimmed copy of NASA's real APOD feed on 2026-10-16: a
video day (which the old page scraper could not see) followed by an image
day (whose picture the old scraper then showed under the wrong date).
"""

from __future__ import annotations

import datetime as dt
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import apod  # noqa: E402
import refresh  # noqa: E402

FIXTURE = (ROOT / "tests" / "fixtures" / "apod-basic-2026-10-16.xml").read_bytes()


class ApodFeed(unittest.TestCase):
    def setUp(self) -> None:
        self.entries = apod.parse_feed(FIXTURE)

    def test_dates_come_from_the_entries(self) -> None:
        self.assertEqual([e["date"] for e in self.entries], ["2026-10-16", "2026-10-15"])

    def test_video_day_is_recognised(self) -> None:
        video = self.entries[0]
        self.assertEqual(video["kind"], "video")
        self.assertEqual(video["title"], "Chasing the International Space Station")
        self.assertTrue(video["video"].endswith(".mp4"))
        self.assertIn("2026-october-16", video["link"])

    def test_image_day_gets_a_display_sized_image(self) -> None:
        image = self.entries[1]
        self.assertEqual(image["kind"], "image")
        self.assertTrue(image["image"].startswith("https://"))
        self.assertTrue(image["image"].endswith("?w=1280&h=1280&fit=clip"))

    def test_an_entry_without_a_date_is_refused_not_dated_today(self) -> None:
        item = ET.fromstring("<item><title>Undated</title><link>https://example.org/x/</link></item>")
        with self.assertRaises(apod.StaleOrBroken):
            apod.entry_date(item)

    def test_implausible_entries_are_refused(self) -> None:
        with self.assertRaises(apod.StaleOrBroken):
            apod.plausible({"date": "2026-10-16", "title": "NASA Science", "image": "https://x/a.jpg"})
        with self.assertRaises(apod.StaleOrBroken):
            apod.plausible({"date": "2026-10-16", "title": "A", "image": "https://x/nasa-logo.png"})

    def test_no_today_fallback_anywhere(self) -> None:
        source = (ROOT / "scripts" / "apod.py").read_text(encoding="utf-8")
        self.assertNotIn("date.today()", source)
        self.assertNotIn("datetime.now()", source)


class ApodBlock(unittest.TestCase):
    def test_video_entries_link_to_the_video(self) -> None:
        block = refresh.apod_block({
            "date": "2026-10-16", "title": "Chasing the International Space Station", "kind": "video",
            "image": "assets/generated/apod-still.jpg", "alt": "A launch",
            "link": "https://science.nasa.gov/image-article/apod-2026-october-16-chasing-the-international-space-station/",
        })
        self.assertIn("apod-2026-october-16", block)
        self.assertIn("click to play", block)
        self.assertIn("assets/generated/apod-still.jpg", block)


class SkyBadges(unittest.TestCase):
    def test_moon_and_sunset_are_sane(self) -> None:
        phase, lit, name = refresh.moon_tonight(dt.date(2026, 10, 26))
        self.assertGreater(lit, 0.9)
        self.assertIn(name, ("full moon", "waning gibbous", "waxing gibbous"))
        sun = refresh.sunset(dt.date(2026, 6, 21), *refresh.TEMPE)
        self.assertTrue(19 <= sun.hour <= 20)


if __name__ == "__main__":
    unittest.main()
