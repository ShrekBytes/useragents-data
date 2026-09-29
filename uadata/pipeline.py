"""Merge sources, check the result, publish it.

The checks are the point of this rewrite. The previous scraper produced a worse
dataset than the day before and nothing objected, because nothing compared the
output against any expectation. Three checks stand in for that:

  freshness  is the newest thing we hold as new as what vendors say is shipping
  regression did anything we published last week disappear this week
  shrinkage  did a source that is still up quietly start returning less

Everything else here is plumbing.
"""

from __future__ import annotations

import json
import os
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from . import browsers
from .manifest import Manifest
from .model import CATEGORIES, CATEGORY_LABELS, Record, SourceResult, merge_records

DATA_DIR = "data"
LEGACY_DIR = "common"
STATE_PATH = os.path.join("state", "history.json")

# One major of slack absorbs a release landing between the source's last publish
# and our Saturday run. Two majors behind is a freeze, and is a hard failure.
TOLERANCE_MAJORS = 1

# Per-source baselines: warn under this fraction of the recent median, fail under
# the lower one (ADR-0003). A source needs a few good runs before it can be judged,
# otherwise a new source fails on its first, perfectly healthy, run.
WARN_SHRINK = 0.70
FAIL_SHRINK = 0.50
GRACE_RUNS = 4
HISTORY_WINDOW = 8

# The repository is a curated dataset, not an unbounded mirror of whatever a source
# chooses to publish (ADR-0007).
#
# Sub-caps rather than one global number: a single frequency-ordered cut would be
# taken entirely by bots, which are roughly 69% of real traffic, leaving almost
# nothing for browsers. This split is editorial, not traffic-proportional.
CATEGORY_CAPS = {"desktop": 200, "mobile": 200, "tablet": 50, "bot": 50}
TOTAL_CAP = sum(CATEGORY_CAPS.values())
assert TOTAL_CAP == 500, "the budget is 500 in total; adjust ADR-0007 if this changes"

# Slots within a category's cap that measured records may not consume. Measured
# frequency is dominated by old and degenerate strings — the most common desktop UA
# has no browser token at all — so trimming purely by frequency would evict every
# current browser and rebuild the staleness this pipeline exists to prevent.
RESERVED_UNMEASURED = 20

# Freshness is checked against these families only, because it needs a vendor to
# compare with. Regression is checked against every family in
# `browsers.FAMILY_NAMES`, since it only needs what we published last time.
MANIFEST_PRODUCTS = {
    "chrome": ("windows", "mac", "linux", "android"),
    "firefox": ("firefox",),
}


@dataclass
class Check:
    name: str
    ok: bool
    level: str  # "error" | "warning"
    detail: str

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "ok": self.ok, "level": self.level, "detail": self.detail}


def merge_sources(results: list[SourceResult]) -> dict[str, list[Record]]:
    """Union every source's records per category, keyed by the exact string.

    Counts are never summed or averaged: `count` from one source has no relationship
    to `count` from another. The first measured value wins and provenance records
    who confirmed the string.
    """
    merged: dict[str, dict[str, Record]] = {c: {} for c in CATEGORIES}
    for result in results:
        for category, records in result.records.items():
            bucket = merged.setdefault(category, {})
            for record in records:
                existing = bucket.get(record.user_agent)
                bucket[record.user_agent] = (
                    record if existing is None else merge_records(existing, record)
                )
    return {c: order_records(list(v.values())) for c, v in merged.items() if v}


def order_records(records: list[Record]) -> list[Record]:
    """Measured records first by frequency, then everything else, newest first.

    The measured block leads because that is the ordering consumers of the legacy
    files have always seen. Within the unmeasured block, newest browser version
    first, so the current strings are not buried under ancient ones.
    """
    measured = sorted(
        (r for r in records if r.count is not None),
        key=lambda r: (-(r.count or 0), r.user_agent),
    )
    unmeasured = sorted(
        (r for r in records if r.count is None),
        key=lambda r: (-newest_major(r.user_agent), r.user_agent),
    )
    return measured + unmeasured


def apply_caps(merged: dict[str, list[Record]]) -> tuple[dict[str, list[Record]], int]:
    """Trim every category to its sub-cap, protecting current versions.

    Each category reserves slots for unmeasured records. Measured traffic is
    dominated by old and degenerate strings — the single most common desktop UA
    carries no browser token at all — so a plain tail cut would discard the current
    browsers first and rebuild the staleness this pipeline exists to prevent.

    A category with no sub-cap passes through untouched; `check_caps` fails the
    build on it rather than this function guessing a number.

    Returns the capped dataset and how many records were discarded.
    """
    capped: dict[str, list[Record]] = {}
    discarded = 0
    for category, records in merged.items():
        cap = CATEGORY_CAPS.get(category)
        if cap is None:
            capped[category] = records
            continue
        measured = [r for r in records if r.count is not None]
        unmeasured = [r for r in records if r.count is None]
        reserved = min(RESERVED_UNMEASURED, len(unmeasured))
        kept_measured = measured[: max(0, cap - reserved)]
        kept_unmeasured = unmeasured[: max(0, cap - len(kept_measured))]
        capped[category] = kept_measured + kept_unmeasured
        discarded += len(records) - len(capped[category])
    return {c: v for c, v in capped.items() if v}, discarded


def check_caps(merged: dict[str, list[Record]]) -> list[Check]:
    """The published dataset must fit the budget, and no category may escape it."""
    total = sum(len(v) for v in merged.values())
    uncapped = sorted(set(merged) - set(CATEGORY_CAPS))
    return [
        Check(
            "cap/categories",
            not uncapped,
            "error" if uncapped else "warning",
            (
                f"no sub-cap defined for {', '.join(uncapped)}; it would publish uncapped"
                if uncapped
                else f"{len(merged)} categories, all within their sub-caps"
            ),
        ),
        Check(
            "cap/total",
            total <= TOTAL_CAP,
            "error" if total > TOTAL_CAP else "warning",
            f"{total} user agents, budget {TOTAL_CAP}",
        ),
    ]


def newest_major(ua: str) -> int:
    """The highest version any family reports in a string, or 0 if none does."""
    known = [m for m in browsers.majors([ua]).values() if m is not None]
    return max(known) if known else 0


def check_freshness(merged: dict[str, list[Record]], manifest: Manifest) -> list[Check]:
    """Is the newest thing we hold as new as what vendors say is shipping?

    This is the check that would have caught the 13-month freeze: the pipeline ran
    happily every day against a source serving browser 134 while the world moved
    to 155.
    """
    everything = [r.user_agent for records in merged.values() for r in records]
    checks = []
    for family in MANIFEST_PRODUCTS:
        expected = max(
            (m for p in MANIFEST_PRODUCTS[family] if (m := manifest.major(p)) is not None),
            default=None,
        )
        observed = browsers.max_major(everything, family)
        name = f"freshness/{family}"
        if expected is None:
            checks.append(
                Check(name, True, "warning", f"skipped: no manifest entry for {family}")
            )
            continue
        if observed is None:
            # Absent is a coverage gap, not evidence of staleness. Treating it as an
            # error would mean a surviving source that happens to lack one browser
            # blocked publication, which is precisely what ADR-0003 forbids. A family
            # we *had* and now do not is caught by check_regression, which is where
            # that case belongs.
            checks.append(
                Check(name, True, "warning", f"dataset holds no {family} user agents")
            )
        elif observed < expected - TOLERANCE_MAJORS:
            checks.append(
                Check(
                    name,
                    False,
                    "error",
                    f"dataset max {family} major {observed}, "
                    f"shipping {expected} (tolerance {TOLERANCE_MAJORS})",
                )
            )
        else:
            checks.append(Check(name, True, "warning", f"max {family} major {observed}"))
    return checks


def check_regression(merged: dict[str, list[Record]], previous: dict[str, Any]) -> list[Check]:
    """Did any browser family go backwards, or vanish, since we last published?

    A dataset that regresses is never published, attributed or not: losing a version
    we already had means something was lost, not merely not refreshed.

    A family that disappears entirely is a regression too, and is the case this
    exists for. `check_freshness` deliberately only warns when a family is absent,
    because absence is a coverage gap rather than evidence of staleness — which
    leaves nobody to catch a family quietly dropping out of the dataset unless it is
    caught here.
    """
    checks = []
    for category, rows in sorted(previous.items()):
        was_by_family = browsers.majors(r["user_agent"] for r in rows)
        now_by_family = browsers.majors(r.user_agent for r in merged.get(category, []))
        for family in browsers.FAMILY_NAMES:
            was, now = was_by_family[family], now_by_family[family]
            if was is None:
                continue  # never published this family; nothing to lose
            if now is None:
                checks.append(
                    Check(
                        f"regression/{category}/{family}",
                        False,
                        "error",
                        f"held {family} major {was} last run and holds none now",
                    )
                )
            elif now < was:
                checks.append(
                    Check(
                        f"regression/{category}/{family}",
                        False,
                        "error",
                        f"max {family} major fell from {was} to {now}",
                    )
                )
    return checks


def check_shrinkage(
    results: list[SourceResult], history: list[dict[str, Any]]
) -> list[Check]:
    """Did a source that is still up start returning less?

    Compares each source against the median of its last few successful runs. The
    comparison is deliberately per-source: a source staying up while its own output
    collapses is anomalous even when the total dataset looks healthy, which is what
    a whole-dataset threshold would miss.
    """
    checks = []
    for result in results:
        name = f"shrinkage/{result.name}"
        if not result.ok:
            checks.append(Check(name, True, "warning", f"source down: {result.error}"))
            continue
        past = [
            run["sources"][result.name]
            for run in history[-HISTORY_WINDOW:]
            if result.name in run.get("sources", {})
        ]
        if len(past) < GRACE_RUNS:
            checks.append(
                Check(
                    name,
                    True,
                    "warning",
                    f"no baseline yet ({len(past)}/{GRACE_RUNS} runs); {result.total} records",
                )
            )
            continue
        median = statistics.median(past)
        if median <= 0 or result.total >= median * WARN_SHRINK:
            checks.append(
                Check(name, True, "warning", f"{result.total} records, median {median:g}")
            )
            continue
        fraction = result.total / median
        detail = f"{result.total} records is {fraction:.0%} of median {median:g}"
        if fraction < FAIL_SHRINK:
            checks.append(Check(name, False, "error", detail))
        else:
            checks.append(Check(name, True, "warning", detail))
    return checks


def load_history(path: str = STATE_PATH) -> list[dict[str, Any]]:
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle).get("runs", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def append_history(
    entry: dict[str, Any], path: str = STATE_PATH, window: int = HISTORY_WINDOW
) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    runs = (load_history(path) + [entry])[-window:]
    with open(path, "w", encoding="utf-8") as handle:
        json.dump({"runs": runs}, handle, indent=2)
        handle.write("\n")


def load_previous(directory: str = DATA_DIR) -> dict[str, Any]:
    """What we published last time, for the regression check."""
    previous: dict[str, Any] = {}
    if not os.path.isdir(directory):
        return previous
    for name in sorted(os.listdir(directory)):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(directory, name), encoding="utf-8") as handle:
                previous[name[: -len(".json")]] = json.load(handle).get("user_agents", [])
        except (json.JSONDecodeError, OSError):
            continue
    return previous


def build_payload(
    category: str,
    records: list[Record],
    results: list[SourceResult],
    manifest: Manifest,
    generated_at: str,
    collection_max_majors: dict[str, int | None] | None = None,
) -> dict[str, Any]:
    """One category's records, with the freshness evidence needed to judge them.

    Both scopes are published because either alone misleads: `bot.json` holds
    Chrome 131 while the collection as a whole holds 154, and a reader given only
    the first would conclude the dataset is stale when it is not.
    """
    return {
        "schema_version": 2,
        "generated_at": generated_at,
        "category": category,
        "sources": [r.to_json() for r in results],
        "freshness": {
            "manifest": manifest.to_json(),
            "collection_max_majors": collection_max_majors or {},
            "in_this_file_max_majors": browsers.majors(r.user_agent for r in records),
        },
        "user_agents": [r.to_json() for r in records],
    }


def build_legacy(
    category: str, records: list[Record], results: list[SourceResult], generated_at: str
) -> dict[str, Any]:
    """The v1 shape, kept alive as a projection so `jq .user_agents[0]` keeps working.

    Only records with a measured count appear. Filling this list from unmeasured
    strings would make it a list of things we cannot say are common, which is the
    one claim this file exists to make.
    """
    return {
        "scraped_at": generated_at,
        "scraped_from": [r.name for r in results if r.ok],
        "type": CATEGORY_LABELS[category],
        "user_agents": [r.user_agent for r in records if r.count is not None],
    }


def write_json(path: str, payload: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
