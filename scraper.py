#!/usr/bin/env python3
"""Build the user agent dataset from every configured source.

Sources are ingested independently: one failing does not stop the others, and the
failure is reported rather than swallowed (ADR-0003). The run publishes only if the
result passes the freshness, regression and shrinkage checks.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from typing import Any

import requests

from uadata import browsers, pipeline
from uadata.manifest import fetch_manifest
from uadata.model import SourceError, SourceResult
from uadata.sources import USER_AGENT, UserAgentsMe

# Adding a source is the only thing Phase 2 should need to touch here.
SOURCES = [UserAgentsMe()]


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
    merged = pipeline.merge_sources(results)
    checks = (
        pipeline.check_freshness(merged, manifest)
        + pipeline.check_regression(merged, pipeline.load_previous())
        + pipeline.check_shrinkage(results, pipeline.load_history())
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
            pipeline.build_legacy(category, records, results, generated_at),
        )
        measured = sum(1 for r in records if r.count is not None)
        print(f"  wrote {category:8} {len(records):4} records ({measured} measured)")

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
