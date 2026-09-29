"""Data types for the user agent dataset.

Every record carries provenance. See CONTEXT.md for what Observed/Synthetic and
Provenance mean; the short version is that a consumer must always be able to tell
where a string came from, and Observed and Synthetic must never share a file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CATEGORIES = ("desktop", "mobile", "tablet", "bot")

CATEGORY_LABELS = {
    "desktop": "most_common_desktop",
    "mobile": "most_common_mobile",
    "tablet": "most_common_tablet",
    "bot": "most_common_bot",
}


class SourceError(RuntimeError):
    """A source could not be ingested. Raised, never swallowed.

    The previous implementation caught every exception per extraction and returned
    an empty list. A source that silently returned nothing looked identical to a
    source with nothing to report, which is how the dataset froze for 13 months.
    """


@dataclass
class Record:
    """One user agent string, plus whatever its source was willing to tell us.

    `count`/`percentage` are only populated by sources that measure real traffic.
    A null count is not missing data to be filled in later; it means no source has
    measured this string, and the record must never be presented as "most common".
    """

    user_agent: str
    os: str | None = None
    browser: str | None = None
    device: str | None = None
    count: int | None = None
    percentage: float | None = None
    sources: tuple[str, ...] = ()

    def to_json(self) -> dict[str, Any]:
        return {
            "user_agent": self.user_agent,
            "os": self.os,
            "browser": self.browser,
            "device": self.device,
            "count": self.count,
            "percentage": self.percentage,
            "sources": list(self.sources),
        }


def merge_records(a: Record, b: Record) -> Record:
    """Combine two records describing the same string.

    Frequency data is never averaged or summed across sources. Counts are only
    comparable within the source that measured them, so the first non-null value
    wins and provenance records that both sources confirmed the string.
    """
    if a.user_agent != b.user_agent:
        raise ValueError("refusing to merge different user agents")
    return Record(
        user_agent=a.user_agent,
        os=a.os or b.os,
        browser=a.browser or b.browser,
        device=a.device or b.device,
        count=a.count if a.count is not None else b.count,
        percentage=a.percentage if a.percentage is not None else b.percentage,
        sources=tuple(sorted(set(a.sources) | set(b.sources))),
    )


@dataclass
class SourceResult:
    """What one source produced, or why it did not.

    Sources are ingested independently: a failure here is recorded and the run
    continues on the others (ADR-0003).

    `collected_at` is part of Provenance per CONTEXT.md — which source saw a string
    is recorded per record, when it was seen is recorded here, once per fetch rather
    than repeated across every record.
    """

    name: str
    records: dict[str, list[Record]] = field(default_factory=dict)
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    collected_at: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None

    @property
    def total(self) -> int:
        return sum(len(v) for v in self.records.values())

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": "ok" if self.ok else "failed",
            "error": self.error,
            "collected_at": self.collected_at,
            "records": self.total,
            "by_category": {k: len(v) for k, v in sorted(self.records.items())},
            "meta": self.meta,
        }
