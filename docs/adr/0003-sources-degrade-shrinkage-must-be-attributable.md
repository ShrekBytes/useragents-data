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
