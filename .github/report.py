#!/usr/bin/env python3
"""Report what actually happened, and escalate a source that has been down.

The status shown is read from the published data and the run history rather than
asserted, so a run that collected nothing cannot report that it succeeded.

    report.py            markdown table for the step summary
    report.py --issue    open/update a single rolling issue for unhealthy sources
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from uadata.pipeline import DATA_DIR, STATE_PATH  # noqa: E402

ISSUE_TITLE = "Source health: user agent sources degraded"
MIN_CONSECUTIVE_FAILURES = 2


def read_json(path: str) -> Any:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def collect() -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    """Per-source health, from the published data plus the run history."""
    seen: dict[str, dict[str, Any]] = {}
    if os.path.isdir(DATA_DIR):
        for name in sorted(os.listdir(DATA_DIR)):
            payload = read_json(os.path.join(DATA_DIR, name))
            if not payload:
                continue
            for source in payload.get("sources", []):
                entry = seen.setdefault(source["name"], {**source, "categories": []})
                entry["categories"].append(payload.get("category"))

    runs = (read_json(STATE_PATH) or {}).get("runs", [])

    # History records *successful publishes only*, so a source missing from the
    # trailing runs has been absent from every publish since, not necessarily
    # failing every scheduled run in between. That is the signal we can actually
    # measure, and it is the one that matters: it counts consecutive publishes the
    # source did not contribute to.
    for name, source in seen.items():
        source["runs_absent"] = next(
            (i for i, run in enumerate(reversed(runs)) if name in run.get("sources", {})), len(runs)
        )
        source["runs_recorded"] = len(runs)
    return seen, runs


def unhealthy(sources: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        name: source
        for name, source in sources.items()
        if source["runs_absent"] >= MIN_CONSECUTIVE_FAILURES
    }


def last_seen(source: dict[str, Any]) -> str:
    """When this source last collected, in its own terms.

    Sources describe their coverage differently — useragents.me names the week it
    published, WinFuture23 names a 48h window — and only some publish a timestamp.
    `collected_at` is the one field the schema guarantees, so it leads; a source
    that does not record one falls back to whatever window it does name.
    """
    return source.get("collected_at") or source.get("meta", {}).get("window") or "-"


def summary(sources: dict[str, dict[str, Any]], runs: list[dict[str, Any]]) -> str:
    lines = ["## User agent update", ""]
    if not sources:
        lines += [
            "**No dataset was published.** The published data is whatever the last",
            "successful run wrote; nothing was replaced by this run.",
            "",
        ]
        return "\n".join(lines)

    lines += [
        "| source | status | records | last seen | consecutive publishes absent |",
        "| --- | --- | ---: | --- | ---: |",
    ]
    for name, source in sorted(sources.items()):
        lines.append(
            f"| `{name}` | {source['status']} | {source['records']} "
            f"| {last_seen(source)} | {source['runs_absent']} |"
        )

    lines.append("")
    if runs:
        lines.append(f"Last successful run: `{runs[-1].get('generated_at', 'unknown')}`")
        lines.append("")
        lines.append(f"Successful publishes recorded: {len(runs)}")
    else:
        lines.append("No successful runs recorded yet; shrinkage baselines are still warming up.")

    degraded = unhealthy(sources)
    if degraded:
        lines += ["", "### Needs attention", ""]
        for name, source in sorted(degraded.items()):
            lines.append(
                f"- `{name}` was absent from {source['runs_absent']} consecutive "
                f"publishes: {source.get('error') or 'no error recorded'}"
            )
    return "\n".join(lines)


def gh(*args: str) -> tuple[int, str]:
    try:
        done = subprocess.run(
            ["gh", *args], capture_output=True, text=True, timeout=60, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return 1, "gh unavailable"
    return done.returncode, done.stdout.strip()


def find_issue() -> int | None:
    code, listing = gh(
        "issue", "list", "--state", "open", "--search", ISSUE_TITLE, "--json", "number"
    )
    if code != 0:
        print(f"could not list issues: {listing}", file=sys.stderr)
        return None
    numbers = [entry["number"] for entry in json.loads(listing or "[]")]
    return numbers[0] if numbers else None


def upsert_issue(sources: dict[str, dict[str, Any]]) -> None:
    degraded = unhealthy(sources)
    existing = find_issue()
    if not degraded:
        if existing is not None:
            gh("issue", "close", str(existing), "--comment", "All sources are recovering. Closing.")
        return

    body = "\n".join(
        f"- `{name}`: absent from {source['runs_absent']} consecutive publishes — "
        f"{source.get('error') or 'unknown error'}"
        for name, source in sorted(degraded.items())
    )
    comment = f"Still degraded as of this run:\n\n{body}"

    if existing is not None:
        gh("issue", "edit", str(existing), "--title", ISSUE_TITLE, "--body", comment)
    else:
        gh("issue", "create", "--title", ISSUE_TITLE, "--body", comment)


def main() -> int:
    sources, runs = collect()
    print(summary(sources, runs))
    if "--issue" in sys.argv:
        upsert_issue(sources)
    return 0


if __name__ == "__main__":
    sys.exit(main())
