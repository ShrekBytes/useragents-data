#!/usr/bin/env python3
"""Build the user agent dataset from every configured source.

Sources are ingested independently: one failing does not stop the others, and the
failure is reported rather than swallowed (ADR-0003). The run publishes only if
the result passes the freshness, regression and shrinkage checks, and if no
published file mixes Observed with Synthetic UAs (ADR-0002).

Synthetic UAs are built here too, from the same manifest the staleness oracle
reads, and published to their own directory. They are generated last and checked
last because they are the only part of the dataset nobody observed: every other
string in it came out of a source that can be asked whether it is still there.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from typing import Any

import requests

from uadata import browsers, pipeline, synthetic
from uadata.manifest import fetch_manifest
from uadata.model import MixedKindsError, SourceError, SourceResult
from uadata.sources import USER_AGENT, CrawlerUserAgents, UserAgentsMe, WinFuture23

# Adding a source is the only thing Phase 2 should need to touch here.
#
# Independent by construction, not by claim: useragents.me measures frequency,
# WinFuture23 is CC0 current-version traffic, crawler-user-agents is observed
# crawler strings. Any one of them can vanish without taking the dataset with it
# (ADR-0008). `pipeline.ORDERING_SOURCE` names the one whose counts we rank by.
SOURCES = [UserAgentsMe(), WinFuture23(), CrawlerUserAgents()]


def _annotate(level: str, title: str, detail: str) -> None:
    """Surface a condition on the Actions page and in the run summary."""
    safe = detail.replace("%", "%25").replace("\r", " ").replace("\n", " ")
    print(f"::{level} title={title}::{safe}")


def _report(results: list[SourceResult], checks: list[pipeline.Check], manifest) -> None:
    for result in results:
        state = f"ok ({result.total} records)" if result.ok else f"FAILED: {result.error}"
        _annotate("error" if not result.ok else "notice", result.name, state)
    for check in checks:
        if check.ok and check.level != "warning":
            continue
        _annotate(check.level, check.name, check.detail)

    print("\n== sources ==")
    for result in results:
        detail = f"{result.total} records" + (f"  {result.meta}" if result.meta else "")
        print(f"  {result.name:24} {'ok' if result.ok else 'FAILED':8} {detail}")
    print("\n== manifest ==")
    print(f"  {manifest.to_json()['versions'] or 'unavailable'}")
    if manifest.errors:
        for error in manifest.errors:
            print(f"  ! {error}")
    print("\n== checks ==")
    for check in checks:
        mark = "ok  " if check.ok else "FAIL"
        print(f"  [{mark}] {check.name:34} {check.detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="run the checks and report without writing anything",
    )
    args = parser.parse_args(argv)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    results: list[SourceResult] = []
    for source in SOURCES:
        try:
            results.append(source.fetch(session))
        except SourceError as exc:
            results.append(SourceResult(name=source.name, error=str(exc)))
        except Exception as exc:  # a plugin bug must not take the run down
            results.append(SourceResult(name=source.name, error=f"{type(exc).__name__}: {exc}"))

    manifest = fetch_manifest(session)
    try:
        merged = pipeline.merge_sources(results)
    except MixedKindsError as exc:
        # A source handed over a Synthetic record. No source observes anything
        # fabricated, so this is a source plugin that has lost track of what it is
        # — and it is reported as a failed run rather than a traceback, because the
        # operator reading the Actions page needs to know which source to look at
        # (ADR-0002).
        _annotate("error", "separation/merge", str(exc))
        print(f"\n{exc}\nNothing published.")
        return 1

    # Which sources could not be reached this run. Every check that would otherwise
    # read a loss as unexplained asks this first (ADR-0003).
    down = {r.name for r in results if not r.ok}

    # Cap before the checks run, so every check sees exactly what would be
    # published. Capping afterwards would let a regression hide in the discarded
    # tail, and would report freshness for records no consumer can see.
    merged, discarded = pipeline.apply_caps(merged)

    # Generated against the capped Observed set, so a string we already publish as
    # witnessed is never published a second time as a fabrication (ADR-0002).
    try:
        synthetic_records, withheld = synthetic.build(
            manifest, (r.user_agent for records in merged.values() for r in records)
        )
    except synthetic.SyntheticError as exc:
        # The generator produced a string its own family detection cannot classify.
        # That is a bug in this repository, not a source outage, so it is reported
        # the same way rather than left to print a traceback nobody reads.
        _annotate("error", "synthetic/generate", str(exc))
        print(f"\n{exc}\nNothing published.")
        return 1

    checks = (
        pipeline.check_freshness(merged, manifest)
        + pipeline.check_regression(merged, pipeline.load_previous(), down=down)
        + pipeline.check_shrinkage(results, pipeline.load_history())
        + pipeline.check_coverage(merged)
        + pipeline.check_caps(merged)
        + pipeline.check_separation(merged)
        + pipeline.check_synthetic(synthetic_records, merged, withheld)
        + pipeline.check_fidelity(synthetic_records, manifest)
    )

    generated_at = datetime.now(timezone.utc).isoformat()
    _report(results, checks, manifest)

    if not merged:
        print("\nNo data collected from any source. Nothing published.")
        return 1

    failed = [c for c in checks if not c.ok]
    if failed:
        print(f"\n{len(failed)} check(s) failed. Existing data left untouched.")
        return 1
    if args.check:
        print("\n--check: all clear, nothing written.")
        return 0
    if discarded:
        print(f"  capped: discarded {discarded} record(s) over the ADR-0007 budget")

    collection_max_majors = browsers.majors(
        r.user_agent for records in merged.values() for r in records
    )
    for category, records in sorted(merged.items()):
        payload: dict[str, Any] = pipeline.build_payload(
            category, records, results, manifest, generated_at, collection_max_majors
        )
        pipeline.write_json(f"{pipeline.DATA_DIR}/{category}.json", payload)
        pipeline.write_json(
            f"{pipeline.LEGACY_DIR}/{category}.json",
            pipeline.build_legacy(category, records, generated_at),
        )
        measured = sum(1 for r in records if r.count is not None)
        print(f"  wrote {category:8} {len(records):4} records ({measured} measured)")

    written = set()
    for category, records in sorted(synthetic.by_category(synthetic_records).items()):
        name = f"{category}.json"
        pipeline.write_json(
            f"{pipeline.SYNTHETIC_DIR}/{name}",
            pipeline.build_synthetic_payload(category, records, manifest, generated_at),
        )
        written.add(name)
        print(f"  wrote {category:8} {len(records):4} Synthetic records")

    # A category that goes from published to withheld leaves its file behind, and a
    # stale Synthetic file is worse than a missing one: it keeps presenting strings
    # this build no longer stands behind. Scoped to `*.json` in this one directory,
    # so a build cannot delete anything a person put there.
    for stale in sorted(set(os.listdir(pipeline.SYNTHETIC_DIR)) - written):
        if not stale.endswith(".json"):
            continue
        os.remove(os.path.join(pipeline.SYNTHETIC_DIR, stale))
        print(f"  removed {stale:8} no longer generated")

    pipeline.append_history(
        {
            "generated_at": generated_at,
            "sources": {r.name: r.total for r in results if r.ok},
        }
    )

    degraded = [r.name for r in results if not r.ok]
    if degraded:
        print(f"\nPublished with {len(degraded)} source(s) down: {', '.join(degraded)}")
    else:
        print("\nPublished from all sources.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
