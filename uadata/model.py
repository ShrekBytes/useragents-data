"""Data types for the user agent dataset.

Every record carries provenance. See CONTEXT.md for what Observed/Synthetic and
Provenance mean; the short version is that a consumer must always be able to tell
where a string came from, and Observed and Synthetic must never share a file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CATEGORIES = ("desktop", "mobile", "tablet", "bot")

# Every record declares which of the two kinds it is, so a consumer never has to
# infer it from the file it arrived in. See ADR-0002: a consumer who picks a string
# to put in a request header is making an implicit trust claim, and a fabricated
# string silently breaks it.
OBSERVED = "observed"
SYNTHETIC = "synthetic"
KINDS = (OBSERVED, SYNTHETIC)

CATEGORY_LABELS = {
    "desktop": "most_common_desktop",
    "mobile": "most_common_mobile",
    "tablet": "most_common_tablet",
    "bot": "most_common_bot",
}


class SourceError(RuntimeError):
    """A source could not be ingested. Raised, never swallowed.

    A source that returns nothing must be distinguishable from a source that has
    nothing to report, or a run publishes quietly on a subset of its inputs
    without saying so (ADR-0003).
    """


class MixedKindsError(ValueError):
    """A set of records was about to be written to one file holding both kinds.

    ADR-0002. Raised rather than warned about, because the file it would have
    produced is the exact artefact a consumer trusts without reading: pick a
    string, put it in a `User-Agent` header, report later that production never
    sends it.
    """


@dataclass
class Record:
    """One user agent string, plus whatever its source was willing to tell us.

    `kind` is Observed or Synthetic and is never inferred from context, so a
    consumer holding a single record always knows which claim it may make about
    it. `synthesized_from` names the template that built a Synthetic record, and
    is the only thing that can: no source witnessed it.

    `count`/`percentage` are only populated by sources that measure real traffic.
    A null count is not missing data to be filled in later; it means no source has
    measured this string, and the record must never be presented as "most common".

    `count_source` names the source that measured them. It is not redundant with
    `sources`: a source can confirm a string exists without saying how often it
    was seen, and a frequency is only comparable within the source that measured
    it (ADR-0009).
    """

    user_agent: str
    kind: str = OBSERVED
    os: str | None = None
    browser: str | None = None
    device: str | None = None
    count: int | None = None
    percentage: float | None = None
    count_source: str | None = None
    sources: tuple[str, ...] = ()
    synthesized_from: str | None = None

    def __post_init__(self) -> None:
        # Refused here, at construction, because by publication the record is
        # already filed into the wrong block and nobody would notice (ADR-0009).
        if self.count is not None and self.count_source is None:
            raise ValueError(
                f"count on {self.user_agent!r} names no source; a frequency is only "
                "comparable within the source that measured it"
            )
        if self.count is None and (self.percentage is not None or self.count_source):
            # The other direction is worse. A record claiming a source but no count
            # reads as a measured zero, and `measured_by` would sort it into the
            # ranked block ahead of every real measurement. A percentage with
            # nothing behind it is a share of a sample that was never stated.
            raise ValueError(
                f"{self.user_agent!r} claims {self.count_source or 'a frequency'} "
                "with no count behind it"
            )
        if self.kind not in KINDS:
            raise ValueError(f"{self.user_agent!r} declares kind {self.kind!r}")
        if self.kind == SYNTHETIC and self.count is not None:
            # No source ever saw this string, so nobody measured it. A frequency on
            # a Synthetic record is not a slightly wrong number, it is a claim
            # about traffic that does not exist.
            raise ValueError(
                f"{self.user_agent!r} is Synthetic and carries a count; a fabricated "
                "string has never been seen in traffic"
            )
        if self.kind == SYNTHETIC and not self.synthesized_from:
            # Otherwise a Synthetic record is a string of unknown manufacture
            # wearing the one label that says nobody can vouch for it.
            raise ValueError(
                f"{self.user_agent!r} is Synthetic and names no template; there is no "
                "other record of how it was built"
            )
        if self.kind == OBSERVED and self.synthesized_from:
            raise ValueError(
                f"{self.user_agent!r} is Observed but names a template; a source "
                "witnessed it, so it was not built by one"
            )

    def measured_by(self, source: str) -> bool:
        """Did `source` measure this record's frequency?"""
        return self.count_source == source

    def to_json(self) -> dict[str, Any]:
        return {
            "user_agent": self.user_agent,
            "kind": self.kind,
            "os": self.os,
            "browser": self.browser,
            "device": self.device,
            "count": self.count,
            "percentage": self.percentage,
            "count_source": self.count_source,
            "sources": list(self.sources),
            "synthesized_from": self.synthesized_from,
        }


def _measurement(record: Record) -> tuple[int, float | None, str] | None:
    """A record's frequency claim as one indivisible thing, or None.

    `__post_init__` guarantees the three fields travel together; this exists so
    `merge_records` cannot take `count` from one record and `percentage` from
    another, which would publish a number and a share of a sample that never
    existed, attributed to whichever side happened to be first.
    """
    if record.count is None:
        return None
    return (record.count, record.percentage, record.count_source)


def merge_records(a: Record, b: Record, prefer: str | None = None) -> Record:
    """Combine two records describing the same string.

    Frequency data is never averaged or summed across sources. Counts are only
    comparable within the source that measured them, so one whole measurement wins
    and provenance records that both sources confirmed the string.

    `prefer` names the source whose measurement we publish when both sides carry
    one. Picking whichever was ingested first would silently drop the designated
    ordering source's number whenever a second counting source is listed ahead of
    it in `SOURCES`.
    """
    if a.user_agent != b.user_agent:
        raise ValueError("refusing to merge different user agents")
    if a.kind != b.kind:
        # A merged record would have to pick a kind, and either choice is a lie:
        # the string was either witnessed or built, and the merge would be
        # asserting the one that was not true.
        raise MixedKindsError(
            f"refusing to merge an {a.kind} and a {b.kind} record: {a.user_agent!r}"
        )

    first, second = _measurement(a), _measurement(b)
    if prefer and first is not None and second is not None:
        measurement = second if second[2] == prefer else first
    else:
        measurement = first or second
    count, percentage, count_source = measurement or (None, None, None)

    return Record(
        user_agent=a.user_agent,
        kind=a.kind,
        os=a.os or b.os,
        browser=a.browser or b.browser,
        device=a.device or b.device,
        count=count,
        percentage=percentage,
        count_source=count_source,
        sources=tuple(sorted(set(a.sources) | set(b.sources))),
        synthesized_from=a.synthesized_from or b.synthesized_from,
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
