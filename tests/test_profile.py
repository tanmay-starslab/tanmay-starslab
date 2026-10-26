"""Regression tests for the parts of the profile that have broken before.

    python -m unittest discover -s tests

The fixture is a trimmed copy of NASA's real APOD feed on 2026-10-16: a
video day (which the old page scraper could not see) followed by an image
day (whose picture the old scraper then showed under the wrong date).
"""

from __future__ import annotations

import datetime as dt
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import apod  # noqa: E402
import daily  # noqa: E402
import hero  # noqa: E402
import merger  # noqa: E402
import refresh  # noqa: E402
import watchdog  # noqa: E402

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


class ApodCredit(unittest.TestCase):
    def test_credit_is_plain_text(self) -> None:
        entries = apod.parse_feed(FIXTURE)
        self.assertEqual(entries[0]["credit"], "Eric Holland")
        self.assertEqual(entries[1]["credit"], "Jason Kurth, Ty Buckley")


ENTRY = {
    "date": "2026-10-16", "title": "Chasing the International Space Station", "kind": "video",
    "image": "assets/generated/apod-still.jpg", "alt": "A launch", "credit": "Eric Holland",
    "link": "https://science.nasa.gov/image-article/apod-2026-october-16-chasing-the-international-space-station/",
}


class DailySeeds(unittest.TestCase):
    def test_a_day_has_one_universe_and_days_differ(self) -> None:
        day = dt.date(2026, 10, 26)
        self.assertEqual(daily.seed_for(daily.universe_key(day, 0)), daily.seed_for("2026-10-26"))
        self.assertNotEqual(daily.seed_for("2026-10-26"), daily.seed_for("2026-10-27"))
        self.assertNotEqual(daily.seed_for(daily.universe_key(day, 0)), daily.seed_for(daily.universe_key(day, 1)))

    def test_version_follows_nasa_and_the_universe(self) -> None:
        a = daily.version_for("2026-10-26", ENTRY)
        self.assertTrue(a.startswith("2026-10-26-"))
        self.assertNotEqual(a, daily.version_for("2026-10-26", {**ENTRY, "title": "Something else"}))
        self.assertNotEqual(a, daily.version_for("2026-10-26r1", ENTRY))

    def test_rolls_reset_daily_and_are_capped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(daily, "ROLL_FILE", Path(tmp) / "reroll.json"):
            day = dt.date(2026, 10, 26)
            self.assertEqual(daily.roll_count(day), 0)
            self.assertEqual(daily.bump_roll(day), 1)
            self.assertEqual(daily.bump_roll(day), 2)
            self.assertEqual(daily.roll_count(day + dt.timedelta(days=1)), 0)
            for _ in range(daily.MAX_ROLLS):
                daily.bump_roll(day)
            self.assertEqual(daily.bump_roll(day), 0)
            self.assertEqual(daily.roll_count(day), daily.MAX_ROLLS)

    def test_watchdog_watches_the_branch_daily_publishes(self) -> None:
        self.assertEqual(watchdog.ART_BRANCH, daily.ART_BRANCH)


class Hero(unittest.TestCase):
    def test_same_seed_same_sky(self) -> None:
        svg, facts = hero.build(1234)
        again, _ = hero.build(1234)
        self.assertEqual(svg, again)
        ET.fromstring(svg)  # well-formed
        self.assertLess(len(svg), 400_000)
        self.assertGreaterEqual(len(facts["lines"]), 1)
        self.assertLess(facts["z_abs"], facts["z_qso"])

    def test_sightline_crosses_the_halo_and_misses_the_disk(self) -> None:
        import math
        import random
        for seed in range(200):
            g = hero.layout(random.Random(seed))
            (qx, qy), (px, py), (gx, gy) = g["Q"], g["P"], g["G"]
            # Perpendicular distance from the galaxy to the sightline.
            b = abs((px - qx) * (qy - gy) - (qx - gx) * (py - qy)) / math.hypot(px - qx, py - qy)
            self.assertAlmostEqual(b, g["b"], places=6)
            self.assertLess(b, g["halo"])
            self.assertGreater(b, g["disk"] * 0.75)
            self.assertTrue(60 < px < 1140 and py == hero.PRISM_Y)


class Merger(unittest.TestCase):
    def test_the_galaxies_merge(self) -> None:
        for seed in (1, 2):
            p = merger.plan(seed)
            snaps, *_ = merger.simulate(seed, p)
            first = snaps[0][1]
            last = snaps[-1][1]
            self.assertGreater(float(((first[1] - first[0]) ** 2).sum() ** 0.5), 2.0)
            self.assertLess(float(((last[1] - last[0]) ** 2).sum() ** 0.5), 0.35)


class ReadmeBlocks(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = {
            "version": "2026-10-26-abcdef",
            "hero": {"z_qso": 2.4, "z_abs": 0.9, "arms": 2, "lines": ["Fe II", "Mg II"]},
            "merger": {"q": 0.7, "retrograde": False, "merged": True},
            "plaque_title": "x &amp; y", "footer_title": "An aurora",
        }

    def test_blocks_point_at_todays_versioned_art(self) -> None:
        blocks = daily.readme_blocks(self.manifest, ENTRY)
        self.assertIn(f"{daily.RAW}/hero-2026-10-26-abcdef.svg", blocks["HERO"])
        self.assertIn(f"{daily.RAW}/merger-2026-10-26-abcdef.webp", blocks["APOD"])
        self.assertIn(f"{daily.RAW}/footer-2026-10-26-abcdef.svg", blocks["FOOTER"])
        self.assertIn("apod-2026-october-16", blocks["APOD"])
        self.assertIn("assets/generated/apod-still.jpg", blocks["APOD"])
        self.assertIn("Fe II and Mg II", blocks["HERO"])

    def test_the_reroll_link_opens_the_issue_the_workflow_listens_for(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "reroll.yml").read_text(encoding="utf-8")
        self.assertIn(f"github.event.issue.title == '{daily.REROLL_TITLE}'", workflow)
        self.assertIn("title=" + daily.REROLL_TITLE.replace(" ", "+"), daily.REROLL_URL)

    def test_the_readme_has_every_marker(self) -> None:
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        for name in ("HERO", "APOD", "FOOTER"):
            self.assertIn(f"<!-- {name}:START -->", text)
            self.assertIn(f"<!-- {name}:END -->", text)


class Plaque(unittest.TestCase):
    def test_long_titles_are_trimmed_and_credit_shown(self) -> None:
        svg = daily.plaque({**ENTRY, "title": "A very long title " * 8}, {"q": 0.5, "retrograde": True}, "v", 2)
        ET.fromstring(svg)
        self.assertIn("…", svg)
        self.assertIn("© Eric Holland", svg)
        self.assertIn("re-rolled 2×", svg)

    def test_footer_is_well_formed(self) -> None:
        ET.fromstring(daily.footer(5, dt.date(2026, 10, 26)))


class SkyBadges(unittest.TestCase):
    def test_moon_and_sunset_are_sane(self) -> None:
        phase, lit, name = refresh.moon_tonight(dt.date(2026, 10, 26))
        self.assertGreater(lit, 0.9)
        self.assertIn(name, ("full moon", "waning gibbous", "waxing gibbous"))
        sun = refresh.sunset(dt.date(2026, 6, 21), *refresh.TEMPE)
        self.assertTrue(19 <= sun.hour <= 20)


if __name__ == "__main__":
    unittest.main()
