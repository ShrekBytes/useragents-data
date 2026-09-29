# Synthetic UAs are generated from the manifest, verified by two parsers, and published apart

[ADR-0002](0002-observed-and-synthetic-never-mixed.md) said the two datasets must never share a
file. [ADR-0005](0005-single-version-manifest.md) said one manifest serves both the staleness
assertion and synthetic generation. Neither said how the strings are built, which families are
covered, or how "indistinguishable from Observed" is decided rather than asserted. This does.

## What lands

1. Every record declares `kind`: `observed` or `synthetic`. Schema v3 → v4.
2. Synthetic UAs are generated from the manifest, into `synthetic/`, never into `data/`.
3. Two independent real parsers must identify every generated string correctly, or the build
   fails.

These are one unit. Generation without the separation guarantee breaches ADR-0002, and
generation without the fidelity test ships strings nobody can put in a request header.

## Every record declares its kind

Not inferred from the file it arrived in. A consumer holding a single record — copied into a
spreadsheet, passed between services — can still tell what claim to make about it.

The field is on the record and enforced in `Record.__post_init__`, alongside the rules that
were already there:

- a Synthetic record carrying a `count` is refused. A frequency on a fabricated string is not a
  slightly wrong number; it is a claim about traffic that does not exist.
- a Synthetic record with no `synthesized_from` is refused. Otherwise it is a string of
  unknown manufacture wearing the one label that says nobody can vouch for it.
- `merge_records` refuses to merge records of different kinds. A merged record would have to
  pick a kind, and either choice is a lie.

## Publication refuses a mixed set

`one_kind` in `pipeline.py` is the single predicate, called by both file publishers
(`build_payload`, `build_legacy`) and reported by `check_separation`. One function rather than a
convention because both files are opened by a consumer who reads a list and does not read a
schema; neither may be the only thing standing between a fabricated string and somebody's
`User-Agent` header.

It also checks the caller's claim, not just the records' agreement. An Observed record arriving
at the Synthetic publisher is as wrong as a mixed file, and a search for "a second kind" would
not catch it.

## Generation: versions from the manifest, platform tokens as literals

Versions come from `Manifest` and nowhere else. The staleness oracle and the generator read one
artifact, so they cannot disagree about what "current" means (ADR-0005). A template whose
manifest entry is missing generates nothing and says so.

Platform tokens are literals, and **that is not a shortcut**. Chromium's User-Agent reduction
froze the platform segment of every Chrome string it sends, and documents these as values that
"will not update even if a user is on an updated operating system or device":

| Platform | Frozen token |
| --- | --- |
| Windows | `Windows NT 10.0; Win64; x64` (both 10 and 11) |
| macOS | `Macintosh; Intel Mac OS X 10_15_7` (Chromium) |
| Linux | `X11; Linux x86_64` |
| Android | `Linux; Android 10; K` |

`Linux; Android 10; K` is the reason **no Android version feed exists**, which is worth stating
because the obvious next step is to add one. Current Chrome on Android sends no Android version
at all: reduction reduced the OS version and the device model to that one literal. An Android
feed would be read into a string that does not contain a slot for it.

The SDK repository index (`dl.google.com/android/repository`) was considered and rejected. It
would need a second step to map API level to marketing version, and the mapping is one Google
changes on its own schedule — the same objection ADR-0010 raises against deriving Safari from
macOS.

Gecko keeps its own platform punctuation, and this is one of the tokens that is easy to get
wrong: `Macintosh; Intel Mac OS X 10.15` with dots, against Chromium's `10_15_7` with
underscores. Both are frozen. Neither is the macOS version.

### What is deliberately not generated

| Not generated | Why |
| --- | --- |
| Firefox on Android | Mozilla publishes no Android Firefox version, and unlike Chromium it has not reduced the platform segment — the string genuinely carries the device's Android version, which we would have to invent. |
| Safari, and every iOS string | Apple publishes no current version anywhere (ADR-0010). `CriOS`/`FxiOS` versions come from the same absent feed. |
| Opera, Samsung Internet | No vendor feed. |
| Bots | A fabricated crawler string is a fabricated identity: it would name a bot that does not exist, under someone else's product. |

Firefox is generated from **two** channels, `firefox` and `firefox_esr`. This is not padding. A
current release Firefox is one of the most observed strings in the corpus, so the collision rule
below withholds it on any run where it is present — without ESR, the Synthetic dataset would
lose Firefox outright rather than occasionally. ESR is a supported release, not a back-port, and
the manifest already carries it.

**14 templates**, covering the three families the staleness oracle already asserts. Every browser
whose vendor publishes a version we can read, and nothing else.

## The fidelity bar: two parsers, not one

CONTEXT.md defines the bar as strings indistinguishable from Observed "to a real User Agent
parser", and the plural is doing the work. One parser is one regex database: it agrees with the
templates whenever both were written against the same idea of what Chrome sends. Two
independent implementations agree only when the string is genuinely the string.

- **uap-core**, via the `ua-parser` Python package.
- **ua-parser-js**, the Node module. A separate project with its own rules, which is the point.

The pip package `user-agents` was evaluated as a third opinion and rejected: it wraps
`ua_parser` and returned byte-identical parses on every string. Two parsers that agree because
they are one parser would have made the check look thorough while checking half as much.

The independence is visible, which is how it was confirmed. On the same macOS string uap-core
reports `Mac OS X` and ua-parser-js reports `macOS`; on Android, `Chrome Mobile` against
`Mobile Chrome`. Those disagreements are why the check carries a per-parser spelling table rather
than comparing case-insensitively, and why `test_the_two_parsers_are_genuinely_independent`
asserts they still differ — if they ever agreed on vocabulary, the second parser would be adding
nothing and the check would be one parser wearing two names.

**Node is a build requirement.** `uadata/fidelity.py` shells out to `node`; CI sets it up with
`actions/setup-node`. A parser that cannot be run is a **failure, not a skip**: the promise this
dataset makes is that its strings were verified, and a verification that did not happen is not a
verification that passed. `requirements.txt` and `README.md` say so.

### What the check compares, and against what

Three things per record, per parser: **browser family, browser major, OS name**. All three, because
each one alone misses what the others hide. A string whose `Firefox/` token sits on Chromium
scaffolding carries the right version and the wrong browser. A string naming the right browser on
the wrong platform parses as a browser and nothing else.

The expected values come from the **manifest and the template**, never from the record's own
labels. A record that mislabels itself would otherwise be validated against its own mislabelling,
and a generator bug that wrote the wrong family into the label would sail through the check meant
to catch it. Reading the manifest means the fidelity check and the staleness oracle cannot both be
satisfied by disagreeing about the version.

Separately, the published `browser` and `os` labels must match what the template says they should
be. A string that is right while the record describing it is wrong is the same defect one layer
down: both are published fields a consumer filters on, and a label that disagrees with the string
it sits on is a confidently wrong answer rather than an obviously broken one. This is judged once,
not per parser, because it is a fact about the record rather than about any parser.

The published labels use the dataset's own vocabulary, not a parser's. A phone publishes
`Chrome 155`; both parsers read it as `Mobile Chrome 155`. Same fact, two vocabularies, and the
published one is not the one the check compares against — that would make the label check a
tautology.

The generator also cross-checks each rendered string against this repository's own `browsers`
module — the same family detection the staleness oracle uses. A token in the wrong order fails
there, before a parser is ever consulted.

**Each of the four guards has a test that fails when it is deleted** — the family, the OS, the
version, and the label check, one test each, with a fixture broken in exactly one way so only the
guard the test names can reject it. This is not formality: review found that removing the family
and OS comparisons entirely left the whole suite green, and that a version fixture whose labels
were *also* wrong passed for the wrong reason, so deleting the version comparison was invisible
too. `test_the_browser_family_guard_rejects_a_string_a_parser_reads_as_another_browser` and its OS,
version and label counterparts exist because a check nobody has tried to break is a check nobody
has verified.


## Collision: a string cannot be both witnessed and built

A string in both sets is not a near-miss, it is a contradiction. The Observed record says a
source saw it; the Synthetic one says nobody ever did (ADR-0002).

The generator therefore **withholds** any template whose output is already in the capped Observed
set, and `check_synthetic` proves it did.

Withholding is reported, and the two reasons are reported separately, because both are silent
otherwise and a template that vanishes without a name is how a browser leaves a published
dataset without anybody deciding to:

| Check | Level | Meaning |
| --- | --- | --- |
| `synthetic/withheld[already Observed]` | warning | The design working. The Observed copy is published instead, with real provenance and a real frequency. |
| `synthetic/withheld[no manifest entry for <product>]` | error | A vendor we cannot read. Degrades the dataset without blocking publication (ADR-0003), but is not a run that looks healthy. |

A level says how loud a condition is, not whether it failed, and this is the only check that
passes at error level: the dataset is smaller and nothing is wrong, except that a vendor is dark.
So it is annotated rather than skipped, which is what puts it on the Actions page naming the
product and the templates withheld from it, while the run still publishes and still exits zero.
The reporter skips exactly one shape — a check that passed at warning level.

A category that goes from published to withheld has its file **deleted** on the next successful
build. A stale Synthetic file is worse than a missing one: it keeps presenting strings this build
no longer stands behind, and because the Observed corpus is what caused the withholding, the
corpus-disjointness check would then fail with no build able to fix it. Pruning is scoped to
`*.json` in `synthetic/`.

**The withholding is steady state, and that is the design working.** As of this ADR a run against
the live corpus generates 5 of 14 templates and withholds 9: the Observed corpus legitimately
holds current Chrome, Edge and Firefox on the platforms it covers. Advance the manifest one major
and 12 of 14 return. The two datasets cover different ground by construction — `data/` says what
was seen, `synthetic/` says what a current client would send, and where they overlap the Observed
record is the more useful answer, so that is where the string is published.

An empty Synthetic dataset is a **failure**, not an empty file. A file of zero records reads as
"there are no Synthetic user agents", which is a claim.

## Output

`synthetic/<category>.json`, per Device Category, alongside `data/` and `common/`. Filenames
repeat across directories deliberately — both datasets are cut by Device Category — so what
distinguishes them is the directory and the `kind` every file and every record declares. A
consumer following either path learns what it is holding.

The payload carries `generated_from.manifest` and no `sources` or `freshness` block. The manifest
is the entire provenance of a Synthetic record: there is no source to name and nothing to have
been collected. `sources` is absent rather than empty, because an empty list beside a list of
records would read as "sources ran and found nothing".

## Check names

| Check | Guards against |
| --- | --- |
| `separation/<category>` | A published category holding both kinds, or the wrong one. |
| `synthetic/present` | A build that would publish an empty Synthetic dataset. |
| `synthetic/collision` | A string in both datasets. Names the withheld templates. |
| `synthetic/fidelity/uap-core` | A string uap-core does not identify as intended. |
| `synthetic/fidelity/ua-parser` | A string ua-parser-js does not identify as intended. |

One check per parser, so a failure says which one objected. A single merged check would leave an
operator guessing which regex database disagreed.

## What is checked against the published files, not the generator

Most of the suite tests the generator against its own expectations. Three things are asserted
against the files on disk instead, because they are the only assertions that would notice the
generator and its output having drifted apart:

- **the two datasets are disjoint**, and every published record declares the kind of the file it
  sits in;
- **every published Synthetic string survives both parsers**, so a hand-edited file, a bad merge,
  or a build that published something unplaceable fails CI;
- **`common/` holds no Synthetic string.** It is the one file whose records carry no `kind`, so
  the claim is enforced rather than left to the shape of the file. Nothing Synthetic can get
  there: a Synthetic record carries no count, and `common/` publishes only measured strings.

## Rejected

**Generating from hardcoded version lists.** The point of ADR-0005 is that the staleness oracle
and the generator cannot disagree. A list in the generator is a second answer to "what is
shipping", and it is the one nobody refreshes.

**Adding an Android version feed.** Reduction means current Chrome on Android sends no Android
version. There is no slot for it.

**Checking fidelity on freshly generated records only.** That checks the generator, not the
dataset. The published files are what a consumer downloads, and only a test that reads them
notices a hand-edit, a bad merge, or a build that published something unplaceable.

**Asserting fidelity against our own `browsers` module alone.** It shares our assumptions about
what a Chrome string looks like. It is kept as a cheap first gate — a token in the wrong order
fails there — and it is not the bar.

**Comparing parser output case-insensitively.** Hides the mobile-Android disagreement, and with
it the one case where the two implementations resolve the same bytes to different names. The
spelling tables are three lines each; pretending the difference away is how a check stops
checking.

**Merging Synthetic strings into `common/`.** That file is a ranking of things we can say are
common. Synthetic UAs have no frequency, so the file would be a list of things nobody measured,
under a key called `most_common_desktop`.
