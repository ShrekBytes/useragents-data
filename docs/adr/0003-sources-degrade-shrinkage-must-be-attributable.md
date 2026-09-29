# Sources degrade independently, but shrinkage must be attributable

Ingestion is per-source and independent. When a source fails, the run continues on
the surviving sources and publishes their combined output. The failure is reported,
never swallowed.

This reverses the earlier fail-open-to-last-known-good policy, which was written
when the repo had exactly one source. There, "degrade to survivors" meant "publish
nothing," and holding the previous dataset was the correct call. With four
independent sources, refusing to publish because one is down discards good data for
no benefit.

The invariant that replaces it: **shrinkage must be attributable.** If the dataset
loses records, every lost record must be explained by a source that is known to be
down. Unexplained shrinkage is a hard failure.

That is the real lesson from the 13-month outage. The old scraper produced a smaller,
worse dataset than the day before and nothing objected, because nothing compared
the output against expectations. A fixed "20% shrink" threshold would not have caught
it either — it only detects large losses, and it cannot distinguish an honest
degradation from a source quietly returning garbage. Per-source expected-count
baselines catch both, because a source that stays up while its output collapses is
visibly anomalous even when the total dataset looks healthy.

Maximum browser version may never regress below what was last published, regardless
of attribution. A dataset that goes backwards is never published.

**Amended by [ADR-0008](0008-build-from-independent-observed-sources.md).** The
sentence above was written when one source supplied everything, and it made this ADR
self-contradicting the moment there were two: the source that measured everything
was also the only one that confirmed some browser families, so refusing to publish
on its outage meant never publishing, and the second source was decorative.

Regression is now attributed on the same terms as shrinkage. Every published record
carries its own Provenance, so a lost browser version is traced back to the sources
that confirmed it. If every one of them is unreachable this run, the loss is
explained and the run publishes a warning. If any of them is still answering, the
version was lost for no stated reason and that is a hard failure.

Only the records *above the version still held* are candidates for the explanation.
A category keeps plenty of old strings from a source that is answering, and none of
them is the reason the newest version disappeared; counting them would let an
unrelated source veto the explanation and block the run forever.

The invariant is unchanged where it was doing its job: unexplained loss is never
published. What was wrong was the assumption that a loss could never be explained.
