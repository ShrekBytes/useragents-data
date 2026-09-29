# Freshness is asserted for every family with a readable vendor feed, within one major

`check_freshness` compares the newest version the dataset holds against the newest
version a vendor says is shipping. Two things about that comparison were left to
whatever the code happened to do. Both are now decided.

1. **Coverage.** Chrome and Firefox were asserted because they were the only two
   with a machine-readable current version. Edge and Safari are asserted too.
2. **Strictness.** The tolerance stays at one major, for a reason that is written
   down — and the reason it was originally given for does not survive checking.

This does not contradict [ADR-0005](0005-single-version-manifest.md), which
established that one manifest serves both the staleness assertion and Synthetic UA
generation. This ADR decides which vendors that manifest reads and how the
comparison is judged.

## Coverage: the four feeds

A family is asserted exactly when some vendor publishes a current version we can
read. That is the whole rule, and it is what makes an unasserted family a decision
rather than an oversight.

| Family | Feed | What is read |
| --- | --- | --- |
| Chrome | ChromiumDash | `version`, one request per platform channel |
| Firefox | Mozilla product-details | `LATEST_FIREFOX_VERSION` |
| Edge | `edgeupdates.microsoft.com/api/products` | `ProductVersion` of the **Stable** product, per platform |
| Safari | Apple's release-notes documentation index | newest major with a release that is not a beta |

### Edge was never as unavailable as it looked

The previous comment said Edge's version was markdown-scraped, which is true of
Microsoft's *release notes* and irrelevant, because that is not the only thing
Microsoft serves. The update API returns JSON, and its `ProductVersion` is the same
number the `Edg/` token already carries: as of 2026-09-29 the Stable product's
Windows build reads `154.0.4258.37`.

Two things follow from reading that feed.

The **Beta**, **Dev** and **Canary** products publish higher majors within days of
the stable release, so only `Product == "Stable"` is read. Reading any other would
leave the build permanently red.

**iOS and Android are not read.** Edge there is `EdgiOS/` and `EdgA/`, which are
not this repository's `edge` family. An entry for them would assert freshness
about strings we do not hold.

The endpoint is not documented by Microsoft. That is a real risk and it is
handled the same way every other vendor risk is: if the shape changes the fetch
fails, the reason is recorded in `manifest.errors` — which every published file
carries — and `freshness/edge` reports itself as skipped. Skipped is a warning, not
a claim that the data is current, so what is lost is an assertion rather than
correctness.

### Safari has no vendor feed, and still gets asserted

Apple publishes no current version anywhere, in any format. What it does publish
is the documentation index behind `developer.apple.com`, which is JSON and is
grouped by Safari major — and which lists **betas alongside shipped releases**, so
the obvious reading of "the newest version in the index" is wrong. On the day the
28 beta appears, that reading is 28, and it would fail every run for the months
before 28 actually ships.

So a major is read only once one of its release notes is not titled a beta. A
section whose notes cannot be resolved proves nothing either way and is not
claimed. The direction of both errors is the same one: the worst outcome is a check
that skips and says why, never one that fails every run over a beta.

This is the weakest of the four feeds and is written down as such. It is still
better than the alternative, which is Safari not being asserted at all while every
other family is — Safari is on an operating-system release cycle, so a dataset can
carry `Version/20.0` for a year with Chrome and Firefox current and nothing else
complaining.

**What this feed cannot do.** It is Apple's documentation index, not a version
feed, and two things follow that a feed would not have. It is read by matching the
section title `Version <n>`, so a cosmetic change to that title stops the read —
which degrades to a named error and a skipped check, and leaves Safari covered by
the regression check alone. And if Apple stopped shipping a new Safari for a year,
nothing here would notice, because a version that has not changed is not stale.

### What is still not asserted

Opera, Samsung Internet, CriOS and FxiOS have no vendor feed we can read, so
nothing is asserted about them. The regression check still covers them: a family
that goes backwards, or disappears, is a failure regardless of whether any vendor
told us what current looks like. What they do not have is a second line of defence
against a freeze. That is a real gap, and it is recorded rather than papered over
by trusting some third party's list of current browser versions — a version we did
not read from the vendor is not the vendor saying it.

## Strictness: one major, and not for the reason given

The tolerance is kept, and the reason it is kept is the two cadences:

- The run is **weekly** and the source data is at most a week old.
- A browser major ships **more often than the run does**.

So in the days after a release, the newest data there is legitimately one major
behind what the vendor reports, and strict equality would refuse to publish it —
leaving the dataset a further week older, every month, to prove a point the
published data does not need proving. This is also, on the evidence of the git
history, what the constant's own comment has always said.

**A justification that was offered for it, and does not hold.** The reasoning
recorded in the ticket that raised this was that ChromiumDash's platform channels
disagree — Linux lagging Windows by a major — so strict equality would fail on a
vendor quirk rather than on our own staleness. It would not. `MANIFEST_PRODUCTS`
reads a family's expected version as the *newest* of its entries, so a lagging
platform cannot lower the bar: the last recorded run had Linux at 154 and Windows
at 155, was compared against 155, and would have passed.

That is recorded rather than quietly dropped, because it is the reason not to
assume a lagging vendor platform is what the tolerance is hiding. It is not: the
max rule already handles that case.

The cost, stated rather than discovered later: **this oracle cannot see a freeze
shorter than two majors.** That is comfortably inside the thirteen months it exists
to catch, and it is the price of not blocking publication once a month on a
vendor's release schedule. The limit is written in majors rather than weeks because
majors are the unit the vendors publish and the unit we compare; a wall-clock figure
would have to be re-derived whenever a vendor changes its schedule, and would then
be wrong without anybody noticing.

**What the max rule does hide.** Reading a family as the newest of its entries is
what makes the channel argument above wrong, and it costs something of its own: a
dataset satisfies a family by holding one current string, whatever else is stale
alongside it. The Edge feed carries MacOS at both 152 and 154, so a dataset whose
newest Edge string is a 154 on Windows passes `freshness/edge` with its Mac Edge two
majors behind. Per-platform freshness would be the stricter check. It is not what is
asserted, and the gap is recorded here rather than discovered later.

`TOLERANCE_MAJORS` is asserted from both sides in the tests: one major behind
passes, two fails. A tolerance nobody states the limit of is an accident.

## Rejected

**Strict equality.** Catches a freeze the moment it is a major behind, and buys
that by going red after every release for up to a week. A build that cries wolf
once a month is a build whose failures are ignored, and the thirteen months this
repository lost were lost to a build that was green.

**Scraping Edge's markdown release notes.** A browser version read out of prose is
a parse of a sentence, and the JSON feed says the same thing more reliably.

**Deriving Safari from the current macOS or iOS version.** Two steps from a vendor
statement, through a mapping Apple changes on its own schedule. If the mapping
breaks, the check fails every run and the reason is nowhere near the cause.

**Reading Safari's index without the beta filter.** Simple, and wrong for most of
the year.

**Marking Edge's undocumented endpoint too risky to use.** The risk is real, and
it should be named honestly rather than talked away: if the shape changes, the
failure is recorded in `manifest.errors` and `freshness/edge` reports itself
skipped, so a stale Edge would publish with a warning on it rather than be caught.
Declining to read a vendor because the vendor's documentation is thin would mean
asserting Chrome and Firefox only, which is the gap this ADR exists to close.
