# useragents.me is used as the primary source despite having no licence

The site publishes dated JSON files under `/data/` with no licence, no terms of
service, and no licence or terms page at all — `/terms`, `/about` and `/license`
all return 404. Default copyright therefore applies and the data is nominally all
rights reserved. We use it as the primary source anyway.

The alternative was to drop it and run on CC0 data alone. That was rejected because
useragents.me is the only source publishing real frequency data — `count` and
`percentage` for observed traffic — and losing it would leave the dataset unable to
answer "what do people actually send", which is the question most consumers of this
repo are asking. The cost of dropping it is higher than the cost of accepting the
ambiguity.

Accepted consequences, all deliberate:

- Records carry full provenance so any consumer can see which data came from where.
- README attributes useragents.me explicitly rather than presenting the output as
  solely our own work.
- The site owner was asked about the intended use and gave permission, with no
  conditions attached.

The exposure is pre-existing: this repo has carried a GPL-3.0 LICENSE since its first
commit, while its README has always described it as MIT. Whichever is intended, that
discrepancy needs settling deliberately rather than being left to whichever document a
reader happens to open. A clean JSON endpoint makes redistribution cheaper and therefore
more likely to be noticed, but it does not create the exposure.

No source is load-bearing. Removing useragents.me entirely leaves a working, current,
legally clean dataset built on CC0 and MIT sources — only the frequency counts are
lost. That is the point of having more than one.

Update: the site owner was contacted and confirmed that the use described here is
permitted, with no conditions attached. No licence or terms were published in reply,
so this rests on that permission rather than on a licence a reader can point to. The
decision to use the source stands, and the exposure recorded above is closed.
