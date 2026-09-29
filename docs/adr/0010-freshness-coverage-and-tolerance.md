# Freshness is asserted for every family whose vendor publishes a current version, within one major

`check_freshness` compares the newest version the dataset holds against the newest
version a vendor says is shipping. Two things about that comparison were left to
whatever the code happened to do. Both are now decided.

1. **Coverage.** Chrome and Firefox were asserted because they were the only two
   with a machine-readable current version. Edge is asserted too. Safari is not,
   and the reason it is not is written down below.
2. **Strictness.** The tolerance stays at one major, for a reason that is written
   down — and the reason it was originally given for does not survive checking.

This does not contradict [ADR-0005](0005-single-version-manifest.md), which
established that one manifest serves both the staleness assertion and Synthetic UA
generation. This ADR decides which vendors that manifest reads and how the
comparison is judged.

## Coverage: three feeds

A family is asserted exactly when its vendor publishes a current version, as a
version, somewhere we can read. That is the whole rule, and it is what makes an
unasserted family a decision rather than an oversight.

| Family | Feed | What is read |
| --- | --- | --- |
| Chrome | ChromiumDash | `version`, one request per platform channel |
| Firefox | Mozilla product-details | `LATEST_FIREFOX_VERSION` |
| Edge | `edgeupdates.microsoft.com/api/products` | `ProductVersion` of the **Stable** product, per platform |

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

### Safari: not asserted, and the gap is left open

Apple publishes no current version anywhere, in any format. That is the reason the
previous comment gave, and it is true but not sufficient, because something
machine-readable *does* exist and it would be easy to reach for.

It is the documentation index behind `developer.apple.com`: JSON, grouped by
Safari major, and it does report 27 today. It is not a statement about what has
shipped. It is a statement about what Apple has written articles about, which
includes versions nobody has:

- It lists **betas alongside shipped releases**. As of 2026-09-29 it carries
  `Safari 27 Release Notes` and `Safari 27.2 Beta Release Notes` in the same
  section. Reading the newest entry gives 28 on the day the 28 beta appears, and
  would then fail every run for the months before 28 actually ships.
- It is read by matching a section title of the form `Version <n>`, which is a
  presentation decision. Apple renames a heading, and Safari's freshness assertion
  stops silently degrading to a skipped check.
- A version that has not changed is not stale, so if Apple stopped shipping Safari
  entirely, this source would never say so.

Every one of those is survivable. The point is that each one is a way for the
build to go red, or to stop asserting, for reasons that have nothing to do with
whether our data is stale. A staleness oracle whose inputs are a vendor's editorial
plans is not an oracle, and the failure mode is the expensive one: a red build
operators learn to ignore, which is how thirteen months were lost in the first
place.

So **Safari is not asserted**, and the gap is left visible rather than closed with
something we cannot stand behind. It is written into the ADR, into the comment on
`MANIFEST_PRODUCTS`, and into a test that fails if anyone adds it back without
reopening this decision.

What Safari still has: the regression check covers every family, so a Safari that
goes backwards, or vanishes from a file, is still a hard failure. What it does not
have is a second line of defence against a freeze — a dataset could sit on
`Version/20.0` indefinitely with Chrome, Edge and Firefox current and nothing else
objecting. That is a real hole, and the honest response to a hole is to write it
down, not to paper it over with a source that cannot be trusted to mean what we
need it to mean.

### What is still not asserted

Opera, Samsung Internet, CriOS and FxiOS have no vendor feed at all, so nothing is
asserted for them, on the same terms as Safari: the regression check covers them,
a freeze does not. A version we did not read from the vendor is not the vendor
saying it, and a third party's list of current browser versions is not a substitute
for one.

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

**Asserting Safari from Apple's documentation index.** It is machine-readable, it
does report the current major, and with a beta filter it can be made to pass today.
It is also a record of Apple's editorial plans rather than of what has shipped, and
a freshness check built on it fails — or quietly stops checking — for reasons that
have nothing to do with our data. See the Safari section above.

**Marking Edge's undocumented endpoint too risky to use.** The risk is real, and
it should be named honestly rather than talked away: if the shape changes, the
failure is recorded in `manifest.errors` and `freshness/edge` reports itself
skipped, so a stale Edge would publish with a warning on it rather than be caught.
Declining to read a vendor because the vendor's documentation is thin would mean
asserting Chrome and Firefox only, which is the gap this ADR exists to close.
