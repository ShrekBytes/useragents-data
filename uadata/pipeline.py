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
from typing import Any

from . import browsers, fidelity, synthetic
from .manifest import Manifest
from .model import (
    CATEGORIES,
    CATEGORY_LABELS,
    OBSERVED,
    SYNTHETIC,
    MixedKindsError,
    Record,
    SourceResult,
    merge_records,
)

DATA_DIR = "data"
LEGACY_DIR = "common"
# Synthetic UAs are a separate dataset, in a directory named for them. A consumer
# reaches these only by asking for `synthetic/`; nothing globs them up by accident
# (ADR-0002).
SYNTHETIC_DIR = "synthetic"
STATE_PATH = os.path.join("state", "history.json")

# Bumped for `kind` and `synthesized_from` on every record. A consumer that
# switches on `kind` and finds it absent in an old file should see a version it can
# check rather than a `null` that reads as "Observed".
SCHEMA_VERSION = 4

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
# version we can read, as a version. Safari is not: Apple publishes none, and the
# documentation index that stands in for one is not a statement about what has
# shipped (ADR-0010). So Opera, Samsung Internet, Safari and the iOS forks are
# covered by the regression check alone — a family going backwards, or vanishing,
# is a failure, but a family quietly sitting still is not.
MANIFEST_PRODUCTS = {
    "chrome": ("windows", "mac", "linux", "android"),
    "firefox": ("firefox",),
    "edge": ("edge_windows", "edge_macos", "edge_linux"),
}


@dataclass
class Check:
    name: str
    ok: bool
    level: str  # "error" | "warning"
    detail: str


def one_kind(records: list[Record], kind: str | None = None) -> str:
    """The single kind these records share, or refuse (ADR-0002).

    One predicate, several call sites, and the reason it is a function rather than
    a convention: `build_payload` and `build_legacy` both publish files a consumer
    opens without reading, so neither may be the only thing standing between a
    fabricated string and somebody's `User-Agent` header. If the two ever
    disagreed about what counts as a mixed set, one of them would quietly stop
    protecting anything.

    `kind` is what the caller asserts the file is about. A payload built for the
    Synthetic dataset that somehow received Observed records is as wrong as a mixed
    one, so the caller's claim is checked too, not just the records' agreement.
    """
    kinds = {record.kind for record in records}
    if len(kinds) > 1:
        raise MixedKindsError(
            f"refusing to publish {sorted(kinds)} in one file; {len(records)} records"
        )
    found = kinds.pop() if kinds else None
    if kind is not None and found is not None and found != kind:
        raise MixedKindsError(
            f"refusing to publish {found} records in the {kind} dataset"
        )
    return found or ""


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


def check_separation(merged: dict[str, list[Record]]) -> list[Check]:
    """No published category may hold both kinds, or the wrong one.

    The refusal itself lives in `one_kind`, called by the two functions that write
    files. This states the same invariant as a check, so a run names the category
    that is mixed instead of raising from inside a builder, and so every build
    summary states the kind of what it published.
    """
    checks = []
    for category in sorted(merged):
        try:
            kind = one_kind(merged[category], kind=OBSERVED)
            checks.append(
                Check(
                    f"separation/{category}",
                    True,
                    "warning",
                    f"{len(merged[category])} {kind} records",
                )
            )
        except MixedKindsError as exc:
            checks.append(Check(f"separation/{category}", False, "error", str(exc)))
    return checks


def check_synthetic(
    records: list[Record],
    observed: dict[str, list[Record]],
    withheld: list[synthetic.Withheld],
) -> list[Check]:
    """The Synthetic dataset exists, is not empty, and shares no string with Observed.

    A string in both sets is not a near-miss, it is a contradiction: the Observed
    record says a source saw it and the Synthetic one says nobody ever did
    (ADR-0002). The generator refuses to emit one; this is what proves it did.

    Also names every withheld template, because both reasons for withholding are
    silent: a string we already observe, and a manifest entry we could not read. A
    browser leaving the dataset with nothing to show for it is the failure mode the
    rest of this pipeline exists to prevent, and it would look exactly like a
    healthy run.
    """
    if not records:
        return [
            Check(
                "synthetic/present",
                False,
                "error",
                "the manifest supported no Synthetic user agents; nothing would be published",
            )
        ]

    seen = {record.user_agent for record in records}
    collisions = sorted(
        seen & {r.user_agent for values in observed.values() for r in values}
    )
    checks = [
        Check("synthetic/present", True, "warning", f"{len(records)} Synthetic records"),
        Check(
            "synthetic/collision",
            not collisions,
            "error" if collisions else "warning",
            f"also Observed: {collisions}"
            if collisions
            else f"{len(seen)} strings, none also Observed",
        ),
    ]

    # Grouped by reason, because the two call for different responses: an
    # "already Observed" template is the design working, a missing manifest entry is
    # a vendor outage somebody has to look at.
    by_reason: dict[str, list[str]] = {}
    for item in withheld:
        by_reason.setdefault(item.reason, []).append(item.name)
    for reason, names in sorted(by_reason.items()):
        level = "warning" if reason == "already Observed" else "error"
        checks.append(
            Check(
                f"synthetic/withheld[{reason}]",
                True,
                level,
                f"{len(names)} template(s): {', '.join(sorted(names))}",
            )
        )
    return checks


def _expected(record: Record, manifest: Manifest, parser: str) -> tuple[str, int, str]:
    """What `parser` must report for this record, from the manifest and the template.

    Never from the record's own `browser` or `os` label. A record that mislabels
    itself would otherwise be checked against its own mislabelling, and a generator
    bug that wrote the wrong family into the label would sail through the check
    meant to catch it. The manifest is the one artifact both this check and the
    staleness oracle read (ADR-0005), so the two cannot be satisfied by
    disagreeing about what the version is.
    """
    template = synthetic.TEMPLATES_BY_NAME[record.synthesized_from]
    return (
        fidelity.browser_family(parser, template.family, mobile=template.mobile),
        manifest.major(template.product),
        fidelity.os_family(parser, template.os),
    )


def _mislabelled(record: Record, manifest: Manifest) -> str | None:
    """How this record's published labels disagree with its template, or None.

    A string that is right while the record describing it is wrong is the same
    defect one layer down. `browser` and `os` are published fields a consumer
    filters on, and a label that disagrees with the string it sits on is a wrong
    answer given confidently rather than an obviously broken one. Checked against
    the template, which is what generated both, so the two definitions of the same
    product cannot drift apart.
    """
    template = synthetic.TEMPLATES_BY_NAME[record.synthesized_from]
    major = manifest.major(template.product)
    for field, published, expected in (
        ("browser", record.browser, synthetic.browser_label(template, major)),
        ("os", record.os, synthetic.os_label(template)),
    ):
        if published != expected:
            return f"{field} is {published!r}, not {expected!r}"
    return None


def check_fidelity(records: list[Record], manifest: Manifest) -> list[Check]:
    """Every Synthetic string must be identified correctly by two real parsers.

    Three things per record, per parser: the browser family, the browser major, and
    the OS name. Each is compared against the manifest and the template, and each
    one alone would miss a defect the others hide — a Gecko string that happens to
    carry the right `Firefox/` token still reads as the wrong family to one parser
    and the wrong OS to both, and a Windows string that parses as Windows but as
    Chrome when it is Edge would pass on version alone.

    One check per parser, so a failure says which one objected. A parser that could
    not be run fails rather than skips: the promise this dataset makes is that its
    strings were verified, and a verification that did not happen is not a
    verification that passed (ADR-0011).
    """
    if not records:
        return []

    # The labels are the same question regardless of which parser is asked, so they
    # are judged once rather than repeated per parser.
    mislabelled = [
        f"{r.synthesized_from}: {reason}"
        for r in records
        if (reason := _mislabelled(r, manifest)) is not None
    ]

    checks = []
    user_agents = tuple(dict.fromkeys(r.user_agent for r in records))
    for parser, adapter in fidelity.ADAPTERS.items():
        name = f"synthetic/fidelity/{parser}"
        try:
            parsed = adapter(user_agents)
        except fidelity.ParserUnavailable as exc:
            checks.append(Check(name, False, "error", f"unavailable: {exc}"))
            continue

        wrong = list(mislabelled)
        for record in records:
            got = parsed[record.user_agent]
            want = _expected(record, manifest, parser)
            if (got.browser_family, got.browser_major, got.os_family) != want:
                wrong.append(
                    f"{record.synthesized_from}: read as {got}, "
                    f"expected {want[0]} {want[1]} on {want[2]}"
                )
        checks.append(
            Check(
                name,
                not wrong,
                "error" if wrong else "warning",
                "; ".join(wrong)
                if wrong
                else f"{len(user_agents)} user agents read as intended",
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
    one_kind(records, kind=OBSERVED)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": OBSERVED,
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


def build_synthetic_payload(
    category: str, records: list[Record], manifest: Manifest, generated_at: str
) -> dict[str, Any]:
    """One category's Synthetic records, and the manifest they were built from.

    The manifest travels with the file because it is the entire provenance of
    every string in it. There is no source to name and no `collected_at` to
    publish: nothing was collected, and a reader who wants to know how current
    these are is asking the only question that has an answer, which is what the
    vendors say is shipping.

    `sources` and `freshness` are absent rather than empty. An empty `sources`
    list beside a list of records would read as "sources ran and found nothing",
    which is the opposite of what happened.
    """
    one_kind(records, kind=SYNTHETIC)
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": SYNTHETIC,
        "generated_at": generated_at,
        "category": category,
        "generated_from": {
            "manifest": manifest.to_json(),
            "templates": [r.synthesized_from for r in records],
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
    one_kind(records, kind=OBSERVED)
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
