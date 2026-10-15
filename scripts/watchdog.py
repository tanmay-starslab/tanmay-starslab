"""Keep the profile's automatic updates alive, and say so loudly when they are not.

GitHub's cron is best-effort: scheduled runs are delayed by hours or dropped
outright when runners are busy, and schedules are switched off in quiet
public repositories. This script, run every couple of hours, is the safety
net. It:

1. re-enables any watched workflow that GitHub has disabled;
2. re-dispatches a workflow whose last successful run is too old;
3. checks the content itself (today's NASA picture, today's activity data);
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

ROOT = Path(__file__).resolve().parent.parent
MST = dt.timezone(dt.timedelta(hours=-7), "MST")  # Arizona: no daylight saving
ISSUE_TITLE = "Profile auto-refresh needs attention"

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


def check_workflows(gh: GitHub, branch: str, now: dt.datetime, simulate: bool) -> list[str]:
    problems = []
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
        if age > redispatch_h and not busy:
            print(f"{wf}: older than {redispatch_h} h; dispatching a run")
            gh.call("POST", f"/actions/workflows/{wf}/dispatches", {"ref": branch})
        if age > alert_h:
            problems.append(f"`{wf}` has not succeeded for {age:.0f} hours (expected at least every {redispatch_h} h).")
    return problems


def check_content(today: dt.date, simulate: bool) -> list[str]:
    problems = []
    apod = json.loads((ROOT / "data" / "cache" / "apod.json").read_text(encoding="utf-8"))
    apod_age = (today - dt.date.fromisoformat(apod["date"])).days
    github = json.loads((ROOT / "data" / "cache" / "github.json").read_text(encoding="utf-8"))
    data_age = (today - dt.date.fromisoformat(github["days"][-1][0])).days
    if simulate:
        apod_age, data_age = max(apod_age, 3), max(data_age, 3)
    print(f"content: NASA picture from {apod['date']} ({apod_age} d old); activity data through {github['days'][-1][0]}")
    # NASA posts the new picture late in the evening, Arizona time, so one day of lag is normal.
    if apod_age >= 2:
        problems.append(f"NASA's picture of the day is {apod_age} days old: both the APOD API and the APOD page may be failing.")
    if data_age >= 2:
        problems.append(f"The activity data stops {data_age} days ago: the GitHub API query may be failing.")
    return problems


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
    problems = check_workflows(gh, branch, now, simulate) + check_content(now.astimezone(MST).date(), simulate)
    sync_issue(gh, problems, simulate)
    print("healthy" if not problems else f"{len(problems)} problem(s) reported")
    return 0


if __name__ == "__main__":
    sys.exit(main())
