# User Agents Data

A current, honest dataset of user agent strings for web scraping, testing and HTTP
client configuration. Updated weekly from multiple independent sources.

## Why this exists

This repo previously scraped [useragents.me](https://useragents.me) by locating HTML
tables through `h2 id="..."` anchors. When the site was redesigned, every extraction
silently returned an empty list. The scraper reported success, `scraped_at` kept
advancing, and CI committed daily — while the dataset sat frozen at browser 134 for
roughly **13 months**, with the real world at 155.

That failure is the reason for the current design:

- Sources are read as **data files**, never parsed from markup ([ADR-0001](docs/adr/0001-consume-data-files-not-html.md)).
- Every build **fails loudly** if the data is more than one major behind what vendors
  say is shipping.
- Sources are **independent**. One failing does not stop the others, but shrinkage
  that cannot be attributed to a source that is known to be down is a hard error
  ([ADR-0003](docs/adr/0003-sources-degrade-shrinkage-must-be-attributable.md)).
  Three of them publish Observed strings, and every Device Category is confirmed by
  at least two ([ADR-0008](docs/adr/0008-build-from-independent-observed-sources.md)).
- Counts are **never combined**. The published order is defined by one designated
  source's measurements, and a frequency always names the source that measured it
  ([ADR-0009](docs/adr/0009-order-by-one-designated-source.md)).
- **Observed and Synthetic are never mixed.** Every record declares which it is,
  and the two live in separate directories. A consumer who picks a string to put in
  a request header is making an implicit trust claim, and a fabricated string
  silently breaks it
  ([ADR-0002](docs/adr/0002-observed-and-synthetic-never-mixed.md)).
- **Synthetic UAs are held to a test, not to a reviewer's eye.** Every generated
  string must be identified correctly by two independent real User Agent parsers
  or the build fails
  ([ADR-0011](docs/adr/0011-synthetic-dataset-shape-and-fidelity.md)).

## Project structure

```
useragents-data/
├── data/                    # Observed records (schema v4)
│   ├── desktop.json
│   ├── mobile.json
│   ├── tablet.json
│   └── bot.json
├── common/                  # Observed plain-string views, regenerated each build
│   ├── desktop.json
│   ├── mobile.json
│   ├── tablet.json
│   └── bot.json
├── synthetic/               # Synthetic UAs. Never Observed, never mixed with them
│   ├── desktop.json         # (a category is published only while the manifest
│   └── tablet.json          #  supports it and its output is not already Observed)
├── state/history.json       # Per-source run history, for shrinkage baselines
├── scraper.py               # Build entry point
├── uadata/                  # Ingestion package
├── tests/                   # unittest suite
└── .github/workflows/       # Weekly build + source health reporting
```

`common/` is **generated from** `data/` on every run. It is not maintained
separately, so the two cannot drift apart.

`data/` and `common/` hold **Observed** UAs: strings a source recorded from real
traffic. `synthetic/` holds **Synthetic** UAs: strings we constructed from
genuinely current product versions. They never share a file, and every record
in `data/` and `synthetic/` says which it is ([ADR-0002](docs/adr/0002-observed-and-synthetic-never-mixed.md),
[ADR-0011](docs/adr/0011-synthetic-dataset-shape-and-fidelity.md)).

Which categories appear in `synthetic/` changes from run to run. A category is
published only while the manifest supports a template for it *and* that
template's output is not already in the Observed corpus — and a category that
stops qualifying has its file deleted rather than left stale.

## Data format

### `data/<category>.json` — Observed, canonical, schema v4

```json
{
  "schema_version": 4,
  "kind": "observed",
  "generated_at": "2026-09-29T09:47:35.722530+00:00",
  "category": "desktop",
  "sources": [
    {
      "name": "useragents.me",
      "status": "ok",
      "error": null,
      "collected_at": "2026-09-29T09:47:33.174027+00:00",
      "records": 126,
      "by_category": {"bot": 20, "desktop": 47, "mobile": 39, "tablet": 20},
      "meta": {"window": "2026-09-20-to-2026-09-27"}
    }
  ],
  "freshness": {
    "manifest": {"versions": {"windows": 155, "firefox": 156}, "errors": []},
    "collection_max_majors": {"chrome": 154, "firefox": 156, "edge": 154},
    "in_this_file_max_majors": {"chrome": 153, "firefox": 156, "edge": 154}
  },
  "user_agents": [
    {
      "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36",
      "kind": "observed",
      "os": "Windows 10",
      "browser": "Chrome 153.0.0.0",
      "device": null,
      "count": 1029,
      "percentage": 2.59,
      "count_source": "useragents.me",
      "sources": ["useragents.me", "winfuture23"],
      "synthesized_from": null
    }
  ]
}
```

**`kind` is on every record and is never inferred.** `observed` or `synthetic`.
A consumer holding one record — copied into a spreadsheet, passed between
services — can still tell what claim to make about it. Schema v4 added it; on a
v3 file the field is absent, so check `schema_version` rather than reading a
missing `kind` as `observed`.

**`count` and `percentage` are only populated for strings a source actually
measured.** A `null` count does not mean zero traffic — it means nobody measured.
Those records are ordered after the measured ones so that anything with a real
frequency claim leads the file. On a Synthetic record they are always `null`,
because no source ever saw the string.

**`count_source` names the source that measured them.** It is not redundant with
`sources`: a source can confirm that a string exists without saying how often it was
seen. `crawler-user-agents` confirms hundreds of crawler strings that no source has
measured, and every one of them carries `count: null`.

### `common/<category>.json` — legacy shape, unchanged keys

```json
{
  "scraped_at": "2026-09-29T09:47:35.722530+00:00",
  "scraped_from": ["useragents.me"],
  "type": "most_common_desktop",
  "user_agents": ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"]
}
```

Observed only, and its keys have not changed since v1, so its records carry no `kind`:
they are bare strings. A test asserts no Synthetic string can appear here, which it
cannot — a Synthetic record carries no count, and this file publishes only measured
strings.

Only strings the ordering source measured appear here, in its descending count order
([ADR-0009](docs/adr/0009-order-by-one-designated-source.md)). This file exists to
answer "what do people actually send", and filling it with strings we cannot make
that claim for — or with another sample's numbers — would defeat it. On a run where
that source is down it publishes an **empty list**: no source measured anything, so
there is no "most common" to publish. `data/` still carries the current strings.

### `synthetic/<category>.json` — Synthetic, schema v4

`synthetic/desktop.json` as published on 2026-09-29, with the three records after
the first left out. The file holds exactly one record per entry in
`generated_from.templates`, and which templates those are changes from run to run.

```json
{
  "schema_version": 4,
  "kind": "synthetic",
  "generated_at": "2026-09-29T12:28:14.917902+00:00",
  "category": "desktop",
  "generated_from": {
    "manifest": {
      "versions": {
        "android": 155,
        "edge_linux": 154,
        "edge_macos": 154,
        "edge_windows": 154,
        "firefox": 156,
        "firefox_esr": 140,
        "linux": 154,
        "mac": 155,
        "windows": 155
      },
      "errors": []
    },
    "templates": ["chrome-mac", "edge-windows", "edge-linux", "firefox-firefox_esr-mac"]
  },
  "user_agents": [
    {
      "user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36",
      "kind": "synthetic",
      "os": "macOS",
      "browser": "Chrome 155",
      "device": null,
      "count": null,
      "percentage": null,
      "count_source": null,
      "sources": [],
      "synthesized_from": "chrome-mac"
    }
  ]
}
```

**These strings were constructed, not witnessed.** They are built from the
versions vendors currently publish, and every one of them is verified by two
independent real User Agent parsers before publication
([ADR-0011](docs/adr/0011-synthetic-dataset-shape-and-fidelity.md)). They carry
no frequency and no Provenance, because there is nothing to attribute: no source
saw them. `generated_from.manifest` is the whole of their provenance, and
`synthesized_from` names the template that built each one.

There is no `sources` or `freshness` block. An empty `sources` list beside a list
of records would read as "sources ran and found nothing", which is the opposite of
what happened.

**Observed and Synthetic never share a file.** If a template's output is already
in the Observed corpus it is withheld rather than published twice — a string
cannot have been both witnessed and built. That means the two datasets overlap
less than you might expect, and the `synthetic/withheld[already Observed]` check
names the withheld templates on every run. Where they *do* overlap in subject, the
Observed record is the more useful answer: it carries real Provenance and a real
frequency, so that is where the string is published.

There is no `synthetic/bot.json`. A fabricated crawler string would name a bot
that does not exist, under someone else's product.

```bash
# Synthetic UAs, and the manifest they were built from.
jq -r '.user_agents[].user_agent' synthetic/desktop.json
jq '.generated_from.manifest.versions' synthetic/desktop.json

# Confirm the two datasets really are disjoint.
jq -r '.user_agents[].user_agent' data/*.json synthetic/*.json | sort | uniq -d
```

## Migrating from the old layout

| Before | Now |
| --- | --- |
| `latest/*.json` (8 files) | **Removed.** The concept did not survive the source redesign. Use `common/` or `data/`. |
| `common/{desktop,mobile}.json` | Unchanged keys; still a plain array of strings |
| — | `common/{tablet,bot}.json` added |
| — | `data/*.json` added, with parsed OS/browser/count/provenance |
| `scraped_from: "https://useragents.me"` (string) | `scraped_from: ["useragents.me"]` (array) |
| `data/*.json` `schema_version: 2` | `schema_version: 3`, adding `count_source` to every record |
| `data/*.json` `schema_version: 3` | `schema_version: 4`, adding `kind` and `synthesized_from` |
| — | `synthetic/*.json` added: constructed UAs, kept apart ([ADR-0011](docs/adr/0011-synthetic-dataset-shape-and-fidelity.md)) |

The `scraped_from` type change is the only breaking one. `jq -r '.user_agents[0]'`
and equivalent code in Python, Node or `curl` is unaffected. Schema v4 only
*adds* fields to `data/*.json` and `synthetic/*.json`, so a reader that ignores
them keeps working; a reader that wants to switch on `kind` should check
`schema_version` first, since a v3 file has the field absent rather than set to
`observed`. `common/*.json` is unchanged.

`scraped_from` now names only the sources whose strings are actually in the file,
rather than every source that ran. On a healthy build the two are the same thing.
On a degraded one it is `[]` beside an empty list, which is the truth.

## Usage

```python
import json, requests

with open("common/desktop.json") as f:
    user_agents = json.load(f)["user_agents"]

requests.get("https://example.com", headers={"User-Agent": user_agents[0]})
```

```javascript
const fs = require("fs");
const { user_agents } = JSON.parse(fs.readFileSync("common/mobile.json", "utf8"));
fetch("https://example.com", { headers: { "User-Agent": user_agents[0] } });
```

```bash
jq -r '.user_agents[0]' common/desktop.json
curl -H "User-Agent: $(jq -r '.user_agents[0]' common/desktop.json)" https://example.com

# Filter the enriched view: everything we know that is a recent Chrome on desktop.
# `.browser` is null for strings no source could identify, hence the fallback.
jq -r '.user_agents[] | select((.browser // "") | test("^Chrome 15[3-9]")) | .user_agent' data/desktop.json

# Check a dataset's freshness without trusting the repo
jq '.freshness' data/desktop.json

# Is the collection current? Compare what we hold against what vendors ship.
jq -r '.freshness | "we hold chrome \(.collection_max_majors.chrome), shipping \(.manifest.versions.windows)"' data/desktop.json
```

`collection_max_majors` and `in_this_file_max_majors` are both published because
either alone misleads: `bot.json` holds Chrome 131 while the collection as a whole
holds 154. Only the first is comparable to the manifest.

## Sources

Three independent Observed sources, plus the version manifest
([ADR-0008](docs/adr/0008-build-from-independent-observed-sources.md)).

| Source | Kind | Licence | Categories | Refreshes | Notes |
| --- | --- | --- | --- | --- | --- |
| [useragents.me](https://useragents.me) | Measured traffic | **None published** | all four | weekly | The only source publishing measured frequency, and the one the published order is defined by. See below. |
| [WinFuture23/real-world-user-agents](https://github.com/WinFuture23/real-world-user-agents) | Observed traffic | CC0-1.0 | desktop, mobile, tablet | 48h | ~150 live strings from WinFuture.de. The only current-version coverage here that is unambiguously redistributable. |
| [monperrus/crawler-user-agents](https://github.com/monperrus/crawler-user-agents) | Observed crawlers | MIT | bot | on commit | ~2100 crawler strings seen in the wild, not an aggregate bot traffic table. |
| Browser vendor release APIs | Version manifest | Public APIs | none | on release | ChromiumDash, Mozilla product-details, Microsoft's Edge update API. Used only for the freshness assertion. |

Every Device Category is confirmed by at least two of them, and `coverage/<category>`
fails the build if any comes out empty. Nothing is load-bearing: any one source being
unreachable is a degraded run that still publishes.

Vendor APIs contribute **version numbers, never user agent strings**. A browser's
version number is not a user agent.

### Attribution and licensing

`useragents.me` publishes no licence, no terms of service, and no licence page. The
site owner has confirmed that the use described here is permitted, with no conditions
attached — a permission, not a licence. We rely on it anyway, because it is the only
source of real frequency data and dropping it would leave the dataset unable to
answer the question most people have. This is a deliberate decision, recorded in
[ADR-0006](docs/adr/0006-useragents-me-used-despite-no-licence.md).

Nothing is load-bearing. Removing that source costs this dataset its `count` and
`percentage` fields and its legacy `common/` rankings; the current browser strings
survive under CC0
([ADR-0008](docs/adr/0008-build-from-independent-observed-sources.md)).

## How staleness is prevented

**Twenty-one checks** run on every build. Any failure aborts the build and leaves
the published data untouched.

A name in the table below is a pattern, not a single check: `coverage/<category>`
is four checks on a normal run, one per Device Category, and `shrinkage/<source>`
is one per configured source, up or down. Twenty-one is the count for a healthy
build, and it moves only when something is wrong — a vendor we cannot read adds a
`synthetic/withheld[no manifest entry for …]`, and a lost browser family adds a
`regression/…` row, one per category it was lost from.

| Check | Guards against |
| --- | --- |
| `separation/<category>` | A published file holding both Observed and Synthetic UAs, or records of the wrong kind for the file ([ADR-0002](docs/adr/0002-observed-and-synthetic-never-mixed.md)). |
| `synthetic/present` | A build that would publish an empty Synthetic dataset, which would read as "there are none". |
| `synthetic/collision` | A string in both datasets. A string cannot have been both witnessed and built. |
| `synthetic/withheld[<reason>]` | A template that generated nothing, dropped without a name. `[already Observed]` is the design working — the witnessed copy is published instead, with real Provenance and a real frequency. `[no manifest entry for <product>]` is a vendor we cannot read: the run still publishes, but the dataset is smaller than the manifest supports ([ADR-0011](docs/adr/0011-synthetic-dataset-shape-and-fidelity.md)). |
| `synthetic/fidelity/uap-core`, `synthetic/fidelity/ua-parser` | A generated string that a real User Agent parser does not identify as intended ([ADR-0011](docs/adr/0011-synthetic-dataset-shape-and-fidelity.md)). One check per parser, so a failure says which objected. |
| `freshness/<browser>` | Data that parses, builds and publishes while being months old. Fails if the dataset's newest version is more than one major behind what vendors report as shipping. Asserted for Chrome, Edge and Firefox — every family whose vendor publishes a current version as a version ([ADR-0010](docs/adr/0010-freshness-coverage-and-tolerance.md)). Safari, Opera, Samsung Internet and the iOS forks have no such feed and are **not** asserted; the regression check is all that covers them. |
| `regression/<category>/<browser>` | Losing a version we already published, or a browser family dropping out of a file entirely. Checked against **every** family, not only those with a vendor feed. Unexplained loss is never published. |
| `coverage/<category>` | A Device Category coming out empty, and reports how many sources confirmed each one. This is the check bot strings need: they carry no browser family, so the regression check cannot see a whole category of crawlers disappear. |
| `cap/categories`, `cap/total` | A Device Category with no sub-cap, or a dataset over the 500 budget. |
| `shrinkage/<source>` | A source that stays up, returns valid JSON, and quietly returns less. Compared against the median of that source's last 8 runs: warn below 70%, fail below 50%. |

Two names are not checks, because they abort the run before it reaches the check
list: `separation/merge`, when a source hands over a Synthetic record, and
`synthetic/generate`, when the generator produces a string it cannot classify. Both
are defects in this repository rather than source outages, and both publish nothing
([ADR-0002](docs/adr/0002-observed-and-synthetic-never-mixed.md),
[ADR-0011](docs/adr/0011-synthetic-dataset-shape-and-fidelity.md)).

A source that is **down** is reported and skipped, not counted as shrinkage — the
run continues on the surviving sources and publishes their combined output
([ADR-0003](docs/adr/0003-sources-degrade-shrinkage-must-be-attributable.md)). After
two consecutive failures a rolling GitHub issue is opened and kept updated.

Shrinkage is judged per source on purpose. Another source being unreachable explains
its own absence; it does not explain a collapse in a source that is up and answering.
The same rule governs the regression check: a browser version that goes missing is
traced back through the published Provenance to the sources that confirmed it, and it
is a hard failure only while any of them is still answering. Without that, a second
source would be decorative — the outage it exists to survive would block every future
run ([ADR-0003](docs/adr/0003-sources-degrade-shrinkage-must-be-attributable.md)).

Builds run **weekly on Saturdays**. Sources publish weekly or every 48 hours, and
Chrome and Edge ship a major every two weeks; a daily schedule produced nothing but
no-op commits.

## The 500 cap

The repository holds at most **500 distinct Observed User Agents**; anything beyond
that is discarded on every build ([ADR-0007](docs/adr/0007-cap-the-dataset-at-500-user-agents.md)).

| Device Category | Cap |
| --- | --- |
| desktop | 200 |
| mobile | 200 |
| tablet | 50 |
| bot | 50 |

Sub-caps rather than one global cut, because a single frequency-ordered budget would
be taken entirely by bots — roughly 69% of real traffic — leaving almost nothing for
browsers.

Within a category, records are already ordered by the designated ordering source's
frequency, then everything else by newest browser version, and trimming keeps that
order **except** that at least 20 slots are reserved for records that source did not
measure. This matters: measured frequency is dominated by old and degenerate strings.
The single most common desktop UA carries no browser token at all, the next few are
Chrome 120, Chrome 131 twice and Safari 17.5, and current Chrome 153 only ranks
seventh. Trimming purely by frequency would evict every current browser and rebuild
the staleness this pipeline exists to prevent.

Synthetic UAs do not count against this budget — they are a separate dataset, and
letting them consume it would silently shrink the observed data.

## How the published order is decided

Records that the ordering source measured lead the file, in descending count.
Everything else follows, by newest browser version. Counts from other sources keep
their own attribution and never enter the ranking, because 10,000 hits in one site's
sample and 5 in another's say nothing about which is more common
([ADR-0009](docs/adr/0009-order-by-one-designated-source.md)).

```bash
# What is ranked, and by whom.
jq -r '.user_agents[] | select(.count != null) | .count_source' data/desktop.json | sort -u

# Confirming a string is not the same act as measuring it.
jq -r '.user_agents[] | select(.sources | length > 1) | "\(.sources | join("+"))  \(.user_agent[0:60])"' data/bot.json
```

## Local development

```bash
git clone https://github.com/ShrekBytes/useragents-data.git
cd useragents-data

pip install -r requirements.txt
npm ci

python -m unittest discover -s tests -t .   # 178 tests, no network
python scraper.py --check                   # run every check, write nothing
python scraper.py                           # build and publish locally
```

Requires Python 3.10+ and **Node**. Both fidelity oracles are needed to publish,
not just to develop: a parser that cannot be run fails the build rather than
skipping, because the promise the Synthetic dataset makes is that its strings were
verified
([ADR-0011](docs/adr/0011-synthetic-dataset-shape-and-fidelity.md)). `ua-parser`
comes from `requirements.txt`; `ua-parser-js` from `package.json`. They are
deliberately independent implementations — if you only want to fetch Observed
data, nothing in `uadata/sources.py` needs either.

### How Synthetic UAs are generated

Versions come from the same manifest the staleness assertion reads, so the
generator and the oracle cannot disagree about what "current" means
([ADR-0005](docs/adr/0005-single-version-manifest.md)). Platform tokens are
literals, and they are literals for two different reasons, which matters. Chromium's
are **frozen**: its User-Agent reduction replaced the platform segment with values
that do not change with the user's operating system, so `Linux; Android 10; K` is
what a current Chrome on Android sends and is *not* a claim about any particular
device. Gecko did no User-Agent reduction at all. Firefox's tokens are hardcoded for
Web compatibility — `Intel Mac OS X 10.15` is a literal in `nsHttpHandler.cpp`, not a
reported version — so they need no version either, but they are not frozen and can
change in any commit. The
[ADR](docs/adr/0011-synthetic-dataset-shape-and-fidelity.md) records the evidence and
the two alternatives that were rejected.

14 templates cover Chrome, Edge and Firefox on Windows, macOS and Linux, plus
Chrome on Android as phone and tablet, and Firefox release and ESR. Not
generated, and why, is written down in the ADR: Firefox on Android, Safari, the
iOS forks, Opera, Samsung Internet and bots all need a version no vendor feed we
can read publishes.

### Adding a source

Implement `fetch(session) -> SourceResult` (see `uadata/sources.py`) and add it to
`SOURCES` in `scraper.py`. The core pipeline does not change: merging, provenance,
ordering, every check and both output formats are already per-source.

Set `count_source` on every record you measure. Leave `count` alone if you do not
measure — a record whose count is unattributed is refused at construction, and one
your source confirmed but did not count is exactly the case that keeps
`crawler-user-agents` from being mistaken for a traffic source.

If it publishes counts, decide in the same change whether it displaces
`pipeline.ORDERING_SOURCE`. Adding a second counting source without a decision about
which one ranks the file is how the two samples get interleaved.

## Documentation

- [`CONTEXT.md`](CONTEXT.md) — vocabulary: Observed vs Synthetic UA, Provenance, Measurement Attribution, Device Category
- [`docs/adr/`](docs/adr/) — why the pipeline is shaped this way

## Licence

GPL-3.0 — see [LICENSE](LICENSE). The README previously claimed MIT; the LICENSE file has
been GPL-3.0 since the first commit. See
[ADR-0006](docs/adr/0006-useragents-me-used-despite-no-licence.md).

## Disclaimer

User agent strings are factual strings sent by HTTP clients. The frequency figures
attributed to `useragents.me` are that site's measurement and are redistributed as
described in [ADR-0006](docs/adr/0006-useragents-me-used-despite-no-licence.md).
The strings from WinFuture23 and crawler-user-agents are redistributed under CC0-1.0
and MIT respectively. Do not use this data to evade bot detection.
