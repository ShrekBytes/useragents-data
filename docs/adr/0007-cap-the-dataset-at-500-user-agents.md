# Cap the dataset at 500 user agents, with sub-caps per Device Category

The repository holds at most 500 distinct Observed User Agents. Beyond that,
records are discarded on every build rather than accumulating.

The cap exists so the repository stays a curated dataset rather than an unbounded
mirror of whatever a source chooses to publish. Nothing about the pipeline needs
a limit technically; this is a judgement about what the repository is for.

## Why not trim purely by measured frequency

The obvious rule — keep the most commonly observed strings — is wrong here, and
visibly so. Measured frequency is dominated by old and degenerate strings: on
desktop the top five are a bare `Mozilla/5.0 (Windows NT 10.0; Win64; x64)
AppleWebKit/537.36` with no browser token at all, Chrome 120, Chrome 131 twice,
and Safari 17.5 and 17.6. Current Chrome 153 sits seventh. Firefox 156, which is
actually shipping, has no measured count at all and would be discarded first.

Trimming by frequency alone would therefore rebuild exactly the failure this
rewrite exists to prevent: a dataset that looks healthy because it is full of
popular strings, and is stale because none of them are current.

## The rule

Within a Device Category, records are already ordered measured-first by frequency
and then unmeasured by newest browser version. Trimming keeps that order and cuts
the tail, with one exception:

> At least 20 slots per category are reserved for unmeasured records.

Measured records may only consume the remainder. So a growing pile of measured
traffic can never evict every current-version string, which it otherwise would
eventually do since the measured block grows monotonically as sources are added.

## Why sub-caps rather than one global 500

A single global cut is taken entirely by whichever category is largest. Bots are
roughly 69% of real traffic, so a frequency-ordered global trim would fill the
budget with `python-requests` and leave almost nothing for browsers — the strings
most consumers of this repository actually came for.

The budget is therefore split, and the split is editorial rather than derived from
observed traffic:

| Device Category | Cap |
| --- | --- |
| desktop | 200 |
| mobile | 200 |
| tablet | 50 |
| bot | 50 |

This deliberately does not represent traffic share. The `bot` cap is the sharpest
expression of that: bots dominate real traffic and are capped at a tenth of the
budget, because a consumer wanting a User Agent to send is far more often
choosing a browser than a crawler.

A category with no sub-cap is a build error rather than an uncapped category.

## Scope

The cap applies to distinct strings in the canonical `data/` files. `common/` is a
derived projection of a subset of those and is not counted separately.

Synthetic UAs are not counted against this budget. They are a separate dataset by
ADR-0002, and letting them consume the Observed budget would silently shrink the
observed data. Synthetic volume is decided with the generator.
