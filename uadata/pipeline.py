"""Merge sources, check the result, publish it.

The checks are the point of this rewrite. The previous scraper produced a worse
dataset than the day before and nothing objected, because nothing compared the
output against any expectation. Four checks stand in for that:

  freshness  is the newest thing we hold as new as what vendors say is shipping
  regression did anything we published last week disappear this week
  shrinkage  did a source that is still up quietly start returning less
  coverage   is every Device Category still published, and by whom

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

# The one source whose measured frequency defines the published order (ADR-0009).
#
# Counts from different sources are not comparable: 1000 hits in one site's sample
# and 5 in another's say nothing about which is more common. So a record is ranked
# only if this source measured it, and a record another source measured joins the
# unmeasured block rather than being compared against ours.
ORDERING_SOURCE = "useragents.me"

# One major of slack, decided rather than inherited (ADR-0010).
#
# The run is weekly and the source data is at most a week old, while a browser
# major ships more often than the run does, so in the days after a release the
# newest data there is is legitimately one major behind the vendor. Strict
# equality would refuse to publish it and leave the dataset a further week older.
#
# Not because vendor channels disagree: `MANIFEST_PRODUCTS` reads a product's
# expected version as the *newest* of its entries, so a lagging platform cannot
# lower the bar. That was the reason offered for this constant, and it does not
# hold.
#
# The cost, stated rather than discovered later: this oracle cannot see a freeze
# shorter than two majors.
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

# Slots within a category's cap that ranked records may not consume. Measured
# frequency is dominated by old and degenerate strings — the most common desktop UA
# has no browser token at all — so trimming purely by frequency would evict every
# current browser and rebuild the staleness this pipeline exists to prevent.
#
# "Unranked" is not the same as "unmeasured": a record the ordering source did not
# measure is unranked even when another source published a count for it (ADR-0009).
RESERVED_UNRANKED = 20

# Freshness is checked against these families only, because it needs a vendor to
# compare with. Regression is checked against every family in
# `browsers.FAMILY_NAMES`, since it only needs what we published last time.
#
# A family is in the first list exactly when some vendor publishes a current
# version we can read. Opera, Samsung Internet and the iOS forks have no such
# feed, so nothing is asserted about them and the regression check is all they
# have — which is why coverage there rests on a family going backwards, not on a
# family going stale (ADR-0010).
MANIFEST_PRODUCTS = {
    "chrome": ("windows", "mac", "linux", "android"),
    "firefox": ("firefox",),
    "edge": ("edge_windows", "edge_macos", "edge_linux"),
    "safari": ("safari",),
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
    to `count` from another. One whole measurement wins and provenance records who
    confirmed the string.
    """
    merged: dict[str, dict[str, Record]] = {c: {} for c in CATEGORIES}
    for result in results:
        for category, records in result.records.items():
            bucket = merged.setdefault(category, {})
            for record in records:
                existing = bucket.get(record.user_agent)
                bucket[record.user_agent] = (
                    record
                    if existing is None
                    else merge_records(existing, record, prefer=ORDERING_SOURCE)
                )
    return {c: order_records(list(v.values())) for c, v in merged.items() if v}


def split_ranked(records: list[Record]) -> tuple[list[Record], list[Record]]:
    """The two blocks every published category is made of, in published order.

    One predicate, two call sites. `order_records` sorts them apart and
    `apply_caps` reserves slots for the second; if the two ever disagreed about
    which block a record is in, the cap would protect records nothing ranks and
    let ranked records spend the space that was meant for the current ones.
    """
    ranked = [r for r in records if r.measured_by(ORDERING_SOURCE)]
    return ranked, [r for r in records if not r.measured_by(ORDERING_SOURCE)]


def order_records(records: list[Record]) -> list[Record]:
    """Ranked by the ordering source's frequency, then everything else, newest first.

    The ranked block leads because that is the ordering consumers of the legacy
    files have always seen. It is deliberately *only* the ordering source's
    measurements: a string another source measured 5,000 times does not outrank a
    string ours measured 10 times, because that comparison would be between two
    different samples rather than a ranking. Within the second block, newest
    browser version first, so the current strings are not buried under ancient ones.
    """
    ranked, unranked = split_ranked(records)
    return sorted(ranked, key=lambda r: (-(r.count or 0), r.user_agent)) + sorted(
        unranked, key=lambda r: (-newest_major(r.user_agent), r.user_agent)
    )


def apply_caps(merged: dict[str, list[Record]]) -> tuple[dict[str, list[Record]], int]:
    """Trim every category to its sub-cap, protecting current versions.

    Each category reserves slots for unranked records. Measured traffic is
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
        ranked, unranked = split_ranked(records)
        reserved = min(RESERVED_UNRANKED, len(unranked))
        kept_ranked = ranked[: max(0, cap - reserved)]
        kept_unranked = unranked[: max(0, cap - len(kept_ranked))]
        capped[category] = kept_ranked + kept_unranked
        discarded += len(records) - len(capped[category])
    return {c: v for c, v in capped.items() if v}, discarded


def check_coverage(merged: dict[str, list[Record]]) -> list[Check]:
    """Every Device Category must be published, and we must say who confirmed it.

    A category that goes missing is not a coverage gap that degrades gracefully:
    `check_regression` only notices a lost browser family, and bot strings carry no
    browser family at all, so a whole category of crawlers could vanish and publish
    cleanly. The build's promise is every Device Category, so an empty one fails.

    The per-category source count is reported rather than enforced. Two sources
    confirming a category is the goal, but refusing to publish because the second
    one is down is exactly what ADR-0003 forbids.
    """
    checks = []
    for category in CATEGORIES:
        records = merged.get(category)
        name = f"coverage/{category}"
        if not records:
            checks.append(Check(name, False, "error", "no records published"))
            continue
        confirming = {source for r in records for source in r.sources}
        checks.append(
            Check(
                name,
                True,
                "warning",
                f"{len(records)} records confirmed by {len(confirming)} source(s): "
                f"{', '.join(sorted(confirming))}",
            )
        )
    return checks


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


def _explained_by(
    rows: list[dict[str, Any]], family: str, now: int | None, down: set[str]
) -> set[str]:
    """The sources whose outage accounts for this family going backwards, or none.

    Attribution, the same rule `check_shrinkage` applies to volume. The published
    records carry their own Provenance, so a lost browser version can be traced
    back to the sources that confirmed it; if every one of them is unreachable, the
    loss is explained. If any of them is still answering, something dropped the
    version and nothing is.

    Only the records *above what we still hold* are candidates. A category almost
    always keeps plenty of old strings from a source that is up, and none of them
    is the reason the newest version disappeared — counting them would let an
    unrelated source veto the explanation and block the run forever.
    """
    if not down:
        return set()
    lost = [
        r
        for r in rows
        if (browsers.major(r.get("user_agent", ""), family) or 0) > (now or 0)
    ]
    # Provenance we cannot read cannot exonerate anyone. A record with no `sources`
    # — a file published before the field existed — is not evidence that the
    # sources that are up did not confirm it.
    provenance = [r.get("sources") for r in lost]
    if not lost or any(not isinstance(p, list) or not p for p in provenance):
        return set()
    confirming = set().union(*(set(p) for p in provenance))
    return confirming if confirming <= down else set()


def check_regression(
    merged: dict[str, list[Record]],
    previous: dict[str, Any],
    down: set[str] | None = None,
) -> list[Check]:
    """Did any browser family go backwards, or vanish, since we last published?

    A dataset that regresses is never published when the loss is unexplained, which
    is the case that matters: a family that disappears while the sources that
    confirmed it are still up has been lost, not merely not refreshed.

    A family that disappears entirely is a regression too, and is the case this
    exists for. `check_freshness` deliberately only warns when a family is absent,
    because absence is a coverage gap rather than evidence of staleness — which
    leaves nobody to catch a family quietly dropping out of the dataset unless it is
    caught here.

    `down` names the sources that failed this run. A family held last time only by
    sources in that set is a degradation we can account for, and it warns. That is
    the one relaxation, and it is the difference between a second source being worth
    having and being decorative: with one source that measured, refusing to publish
    on its outage would mean never publishing (ADR-0003).
    """
    down = down or set()
    checks = []
    for category, rows in sorted(previous.items()):
        was_by_family = browsers.majors(r["user_agent"] for r in rows)
        now_by_family = browsers.majors(r.user_agent for r in merged.get(category, []))
        for family in browsers.FAMILY_NAMES:
            was, now = was_by_family[family], now_by_family[family]
            if was is None:
                continue  # never published this family; nothing to lose
            name = f"regression/{category}/{family}"
            if now is None:
                detail = f"held {family} major {was} last run and holds none now"
            elif now < was:
                detail = f"max {family} major fell from {was} to {now}"
            else:
                continue
            explained_by = _explained_by(rows, family, now, down)
            if explained_by:
                confirmed = ", ".join(sorted(explained_by))
                checks.append(
                    Check(name, True, "warning", f"{detail}; confirmed only by {confirmed}")
                )
            else:
                checks.append(Check(name, False, "error", detail))
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
        "schema_version": 3,
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
    category: str, records: list[Record], generated_at: str
) -> dict[str, Any]:
    """The v1 shape, kept alive as a projection so `jq .user_agents[0]` keeps working.

    This file is the ordering source's ranking and nothing else. Two reasons, and
    they pull the same way:

    - Only records that source measured appear. Filling this list from unmeasured
      strings would make it a list of things we cannot say are common, which is the
      one claim this file exists to make.
    - No other source's measurements appear. They are not comparable with ours, so
      including them would present a list of numbers as one ranking when it is two
      samples compared (ADR-0009).

    `scraped_from` names only the sources whose strings are actually in the list, so
    it cannot claim a provenance the file does not carry. On a run where the ordering
    source is down it is `[]` beside an empty list: nothing here came from anywhere.
    """
    ranking = [r.user_agent for r in records if r.measured_by(ORDERING_SOURCE)]
    return {
        "scraped_at": generated_at,
        "scraped_from": [ORDERING_SOURCE] if ranking else [],
        "type": CATEGORY_LABELS[category],
        "user_agents": ranking,
    }


def write_json(path: str, payload: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
