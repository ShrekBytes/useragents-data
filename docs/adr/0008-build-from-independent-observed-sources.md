# The dataset is built from independent Observed sources, not one of them

`useragents.me` was the whole product. Every string, every count, every field came
from one unlicensed site with no terms of service (ADR-0006), and ADR-0003's claim
that "no source is load-bearing" was true only in the sense that removing the source
removes the dataset with it.

Two sources are added. Neither replaces anything, and either can be unreachable on
any given run without stopping publication.

| Source | Kind | Licence | Categories | Refreshes |
| --- | --- | --- | --- | --- |
| [useragents.me](https://useragents.me) | Measured traffic | **None published** (ADR-0006) | all four | weekly |
| [WinFuture23/real-world-user-agents](https://github.com/WinFuture23/real-world-user-agents) | Observed traffic | CC0-1.0 | desktop, mobile, tablet | every 48h |
| [monperrus/crawler-user-agents](https://github.com/monperrus/crawler-user-agents) | Observed crawlers | MIT | bot | on commit |
| Browser vendor release APIs | Version manifest | Public APIs | none | on release |

## WinFuture23: the redistributable one

About 150 strings recorded off live traffic at WinFuture.de, published as JSON with
a `generated_at` the source itself stamps. Two reasons it is here.

It is **CC0**, which makes it the only current-version Observed coverage in this
dataset that is unambiguously redistributable. That is what makes ADR-0006's
"removing useragents.me costs us the counts and nothing else" an actual claim: the
current desktop, mobile and tablet strings survive its removal under a licence that
permits redistribution.

It refreshes every **48 hours** against a weekly build, so the data is never more
than a few days behind the run that publishes it.

It publishes **no counts**. Its list is ordered by prevalence, but the ordering is
the only ranking it offers and is not a number anyone can compare against another
sample, so none of it is ever presented as measured (ADR-0009).

## crawler-user-agents: bots as strings, not a traffic table

Around 1500 crawler patterns with the User Agent strings actually observed for each
— 2100-odd distinct strings. The patterns are regular expressions and are not data;
the `instances` are.

Every instance is filed as `bot` regardless of what browser token it carries. A
Googlebot that spoofs iPhone Safari is still a crawler, and filing it under `mobile`
because the string mentions Safari would be the most popular kind of wrong available
to this repository.

## What independence has to mean to be worth anything

A second source that mirrors the first buys nothing. These are independent in the
way that matters:

- **Different publishers, different samples.** WinFuture.de traffic and
  useragents.me traffic are not two views of one measurement.
- **Different licences.** One CC0, one unlicensed, one MIT. Losing any one of them
  leaves the others publishable, which is a different situation from three copies of
  the same scrape.
- **Different failure modes.** A site redesign, a rate limit, a schema change and an
  outage do not arrive together.

The build reports per-category which sources confirmed each record, and
`check_coverage` fails the build if any Device Category comes out empty.

## The second source has to actually be usable when the first is gone

Adding a second source is not the same as being able to survive without the first,
and the difference is the regression check. The source that measures also *confirms*
strings, and it confirmed families the others had never seen — Safari in the bot
category, Firefox on tablet. When it goes down, those records go with it, and a
regression check with no attribution reads that as data loss and blocks the run
forever.

So the loss is traced back through the published Provenance, and a family confirmed
only by sources that are currently unreachable is a degradation to warn about rather
than a failure. See the amendment in [ADR-0003](0003-sources-degrade-shrinkage-must-be-attributable.md).
Without that, this ADR would describe a dataset that cannot survive what it was
written to survive.

## Rejected

**A source that mirrors useragents.me's file format.** It would double the count of
every string and validate nothing.

**A per-category source with a fallback chain.** Falling back to a different source
when the preferred one is down makes the dataset's meaning depend on which source
happened to answer, and the records cannot be told apart afterwards. Degrading is
right; substituting is not.

**Publishing crawler patterns as User Agents.** A pattern matches infinitely many
strings, none of which anybody sent. `crawler-user-agents` publishing only patterns
is a failed fetch, not a source with nothing to say.
