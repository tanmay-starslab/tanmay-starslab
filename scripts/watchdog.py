"""Keep the profile's automatic updates alive, and say so loudly when they are not.

GitHub's cron is best-effort: scheduled runs are delayed by hours or dropped
outright when runners are busy, and schedules are switched off in quiet
public repositories. This script, run hourly, is the safety net. It:

1. re-enables any watched workflow that GitHub has disabled;
2. re-dispatches a workflow whose last successful run is too old;
3. checks the content itself against its source: the newest entry NASA has
   published versus the one on the profile, and today's activity data. A run
   can succeed while showing stale content (a source fails and the cache is
   reused), so job status alone is not evidence of freshness;
   the same goes for the daily art: the art branch must hold today's
   universe, and the README on main must point at it;
4. opens one issue when something stays stale (GitHub then notifies the
   owner), keeps it current, and closes it once everything is fresh again.

    GITHUB_TOKEN=... GITHUB_REPOSITORY=owner/repo python scripts/watchdog.py [--dry-run]
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import urllib.request
from pathlib import Path

import apod

ROOT = Path(__file__).resolve().parent.parent
ISSUE_TITLE = "Profile auto-refresh needs attention"
ART_BRANCH = "daily-art"  # as in daily.py (not imported: this script runs without the drawing dependencies)
ARIZONA = dt.timezone(dt.timedelta(hours=-7))

# workflow file: (re-dispatch when the last success is older than, alert when older than), in hours
WATCHED = {
    "refresh.yml": (3, 26),
    "3d-city.yml": (8, 26),
}


class GitHub:
    def __init__(self, repo: str, token: str, dry_run: bool) -> None:
        self.repo, self.token, self.dry_run = repo, token, dry_run

    def call(self, method: str, path: str, body: dict | None = None):
        url = path if path.startswith("https://") else f"https://api.github.com/repos/{self.repo}{path}"
        if self.dry_run and method != "GET":
            print(f"  [dry run] {method} {url} {json.dumps(body) if body else ''}")
            return {}
        req = urllib.request.Request(
            url,
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "tanmay-starslab-profile-watchdog",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
        return json.loads(raw) if raw else {}


def hours_since(stamp: str, now: dt.datetime) -> float:
    return (now - dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))).total_seconds() / 3600


def check_workflows(gh: GitHub, branch: str, now: dt.datetime, simulate: bool) -> tuple[list[str], set[str]]:
    """Problems found, and the workflows that are dispatched or already running."""
    problems, active = [], set()
    for wf, (redispatch_h, alert_h) in WATCHED.items():
        info = gh.call("GET", f"/actions/workflows/{wf}")
        if info.get("state") != "active":
            print(f"{wf}: state is {info.get('state')!r}; re-enabling")
            gh.call("PUT", f"/actions/workflows/{wf}/enable")
        runs = gh.call("GET", f"/actions/workflows/{wf}/runs?status=success&per_page=1").get("workflow_runs", [])
        age = hours_since(runs[0]["updated_at"], now) if runs else float("inf")
        if simulate:
            age = max(age, alert_h + 1)
        busy = any(
            gh.call("GET", f"/actions/workflows/{wf}/runs?status={s}&per_page=1").get("total_count", 0)
            for s in ("queued", "in_progress")
        )
        print(f"{wf}: last success {age:.1f} h ago{' (a run is already queued or running)' if busy else ''}")
        if busy:
            active.add(wf)
        elif age > redispatch_h:
            print(f"{wf}: older than {redispatch_h} h; dispatching a run")
            gh.call("POST", f"/actions/workflows/{wf}/dispatches", {"ref": branch})
            active.add(wf)
        if age > alert_h:
            problems.append(f"`{wf}` has not succeeded for {age:.0f} hours (expected at least every {redispatch_h} h).")
    return problems, active


def check_content(now: dt.datetime, simulate: bool) -> tuple[list[str], bool]:
    """Problems found, and whether the profile is behind its source and needs a refresh."""
    problems = []
    shown = json.loads((ROOT / "data" / "cache" / "apod.json").read_text(encoding="utf-8"))
    shown_date = dt.date.fromisoformat(shown["date"])
    github = json.loads((ROOT / "data" / "cache" / "github.json").read_text(encoding="utf-8"))
    data_date = dt.date.fromisoformat(github["days"][-1][0])
    try:
        newest = apod.newest_entry()
        published = dt.date.fromisoformat(newest["date"])
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=APOD feed unreachable::{exc!r}")
        newest, published = None, None
    if simulate:
        shown_date = shown_date - dt.timedelta(days=3)
        data_date = data_date - dt.timedelta(days=3)
    print(f"content: profile shows the APOD for {shown_date} ({shown.get('title')!r}); "
          f"NASA's newest is {published or 'unknown'}; activity data through {data_date}")

    # Behind if NASA has a newer date, or the same date under a different
    # title (the right date on the wrong picture is how staleness hid once).
    # An entry with no showable media is skipped on purpose by refresh.
    behind = bool(newest and newest["kind"] != "other" and (
        published > shown_date or (published == shown_date and newest["title"] != shown.get("title"))))
    if behind:
        # NASA posts each entry at 04:05 UTC on its date.
        lag = (now - dt.datetime.combine(published, dt.time(4, 5), dt.timezone.utc)).total_seconds() / 3600
        print(f"content: the profile is {lag:.1f} h behind NASA")
        if lag > 6:
            problems.append(f"NASA published \"{newest['title']}\" ({published}) {lag:.0f} hours ago, but the "
                            f"profile still shows \"{shown.get('title')}\" ({shown_date}).")
    today_et = now.astimezone(apod.EASTERN).date()
    if published is None and (today_et - shown_date).days >= 2:
        problems.append(f"The APOD on the profile is from {shown_date} and NASA's feed could not be read.")
    if (now.date() - data_date).days >= 2:
        problems.append(f"The activity data stops at {data_date}: the GitHub API query may be failing.")
    return problems, behind


def check_art(gh: GitHub, now: dt.datetime, simulate: bool) -> tuple[list[str], bool]:
    """Problems found, and whether the daily art is behind (yesterday's, or not linked from the README)."""
    import base64
    import urllib.error

    try:
        blob = gh.call("GET", f"/contents/manifest.json?ref={ART_BRANCH}")
        manifest = json.loads(base64.b64decode(blob["content"]))
    except (urllib.error.HTTPError, KeyError, ValueError) as exc:
        print(f"art: no readable manifest on {ART_BRANCH} ({exc!r})")
        return [f"The `{ART_BRANCH}` branch has no readable manifest.json, so the hero, merger and footer "
                "are missing from the profile."], True
    day = dt.date.fromisoformat(manifest["day"])
    local = now.astimezone(ARIZONA)
    if simulate:
        day -= dt.timedelta(days=3)
    linked = f"hero-{manifest['version']}.svg" in (ROOT / "README.md").read_text(encoding="utf-8")
    print(f"art: {ART_BRANCH} holds {manifest['version']} (day {day}); README links it: {linked}")
    # A new day starts at midnight in Arizona; give the hourly refresh an hour to draw it.
    behind = not linked or (day < local.date() and local.hour >= 1)
    problems = []
    if (local.date() - day).days >= 2:
        problems.append(f"The daily art is from {day}: the hero, merger and footer have not been redrawn since.")
    if not linked:
        problems.append(f"README.md does not link the published art ({manifest['version']}).")
    return problems, behind


def sync_issue(gh: GitHub, problems: list[str], simulate: bool) -> None:
    open_issues = gh.call("GET", "/issues?state=open&per_page=100")
    existing = next((i for i in open_issues if i.get("title") == ISSUE_TITLE and "pull_request" not in i), None)
    if problems:
        actions = f"https://github.com/{gh.repo}/actions"
        body = (
            ("**This is a test of the alert (simulate_stale was set).**\n\n" if simulate else "")
            + "The watchdog found parts of the profile that are not updating:\n\n"
            + "\n".join(f"- {p}" for p in problems)
            + f"\n\nIt has already re-dispatched what it could. Recent runs: {actions}\n\n"
            "This issue closes itself once everything is fresh again."
        )
        if existing:
            print(f"issue #{existing['number']} already open; updating it")
            gh.call("PATCH", f"/issues/{existing['number']}", {"body": body})
        else:
            print("opening an issue")
            gh.call("POST", "/issues", {"title": ISSUE_TITLE, "body": body})
    elif existing:
        print(f"all fresh; closing issue #{existing['number']}")
        gh.call("POST", f"/issues/{existing['number']}/comments", {"body": "Everything is updating again. Closing."})
        gh.call("PATCH", f"/issues/{existing['number']}", {"state": "closed", "state_reason": "completed"})


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    simulate = os.environ.get("SIMULATE_STALE", "").lower() == "true"
    gh = GitHub(os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_TOKEN"], dry_run)
    now = dt.datetime.now(dt.timezone.utc)
    branch = gh.call("GET", "").get("default_branch", "main")
    problems, active = check_workflows(gh, branch, now, simulate)
    content_problems, behind = check_content(now, simulate)
    art_problems, art_behind = check_art(gh, now, simulate)
    problems += content_problems + art_problems
    behind = behind or art_behind
    if behind and "refresh.yml" not in active:
        print("refresh.yml: the profile is behind its source; dispatching a run")
        gh.call("POST", "/actions/workflows/refresh.yml/dispatches", {"ref": branch})
    sync_issue(gh, problems, simulate)
    print("healthy" if not problems else f"{len(problems)} problem(s) reported")
    return 0


if __name__ == "__main__":
    sys.exit(main())
