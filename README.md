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
- Every build **fails loudly** if the data is older than what vendors say is shipping.
- Sources are **independent**. One failing does not stop the others, but shrinkage
  that cannot be attributed to a source that is known to be down is a hard error
  ([ADR-0003](docs/adr/0003-sources-degrade-shrinkage-must-be-attributable.md)).

## Project structure

```
useragents-data/
├── data/                    # Canonical enriched records (schema v2)
│   ├── desktop.json
│   ├── mobile.json
│   ├── tablet.json
│   └── bot.json
├── common/                  # Legacy plain-string views, regenerated each build
│   ├── desktop.json
│   ├── mobile.json
│   ├── tablet.json
│   └── bot.json
├── state/history.json       # Per-source run history, for shrinkage baselines
├── scraper.py               # Build entry point
├── uadata/                  # Ingestion package
├── tests/                   # unittest suite
└── .github/workflows/       # Weekly build + source health reporting
```

`common/` is **generated from** `data/` on every run. It is not maintained
separately, so the two cannot drift apart.

## Data format

### `data/<category>.json` — canonical, schema v2

```json
{
  "schema_version": 2,
  "generated_at": "2026-09-29T09:47:35.722530+00:00",
  "category": "desktop",
  "sources": [
    {
      "name": "useragents.me",
      "status": "ok",
      "error": null,
      "records": 126,
      "by_category": {"bot": 20, "desktop": 45, "mobile": 39, "tablet": 20},
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
      "os": "Windows 10",
      "browser": "Chrome 153.0.0.0",
      "device": null,
      "count": 1029,
      "percentage": 2.59,
      "sources": ["useragents.me"]
    }
  ]
}
```

**`count` and `percentage` are only populated for strings a source actually
measured.** A `null` count does not mean zero traffic — it means nobody measured.
Those records are ordered after the measured ones so that anything with a real
frequency claim leads the file.

### `common/<category>.json` — legacy shape, unchanged keys

```json
{
  "scraped_at": "2026-09-29T09:47:35.722530+00:00",
  "scraped_from": ["useragents.me"],
  "type": "most_common_desktop",
  "user_agents": ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36"]
}
```

Only strings with a measured count appear here. This file exists to answer "what do
people actually send", and filling it with strings we cannot make that claim for
would defeat it.

## Migrating from the old layout

| Before | Now |
| --- | --- |
| `latest/*.json` (8 files) | **Removed.** The concept did not survive the source redesign. Use `common/` or `data/`. |
| `common/{desktop,mobile}.json` | Unchanged keys; still a plain array of strings |
| — | `common/{tablet,bot}.json` added |
| — | `data/*.json` added, with parsed OS/browser/count/provenance |
| `scraped_from: "https://useragents.me"` (string) | `scraped_from: ["useragents.me"]` (array) |

The `scraped_from` type change is the only breaking one. `jq -r '.user_agents[0]'`
and equivalent code in Python, Node or `curl` is unaffected.

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

| Source | Kind | Licence | Notes |
| --- | --- | --- | --- |
| [useragents.me](https://useragents.me) | Observed traffic | **None published** | The only source publishing measured frequency. See below. |
| Browser vendor release APIs | Version manifest | Public APIs | ChromiumDash, Mozilla product-details. Used only for the freshness assertion. |

Vendor APIs contribute **version numbers, never user agent strings**. A browser's
version number is not a user agent.

### Attribution and licensing

`useragents.me` publishes no licence, no terms of service, and no licence page; by
default that means all rights reserved. We use it anyway, because it is the only
source of real frequency data and dropping it would leave the dataset unable to
answer the question most people have. This is a deliberate decision, recorded in
[ADR-0006](docs/adr/0006-useragents-me-used-despite-no-licence.md).

Nothing is load-bearing. Removing that source costs this dataset its `count` and
`percentage` fields and nothing else — that is what the second source in Phase 2 is
for.

## How staleness is prevented

Three checks run on every build. Any failure aborts the build and leaves the
published data untouched.

| Check | Guards against |
| --- | --- |
| `freshness/<browser>` | Data that parses, builds and publishes while being months old. Fails if the dataset's newest version is more than one major behind what vendors report as shipping. Compared against Chrome and Firefox, which have machine-readable current versions. |
| `regression/<category>/<browser>` | Losing a version we already published, or a browser family dropping out of a file entirely. Checked against **every** family, not only those with a vendor feed. A dataset that goes backwards is never published. |
| `shrinkage/<source>` | A source that stays up, returns valid JSON, and quietly returns less. Compared against the median of that source's last 8 runs: warn below 70%, fail below 50%. |

A source that is **down** is reported and skipped, not counted as shrinkage — the
run continues on the surviving sources and publishes their combined output
([ADR-0003](docs/adr/0003-sources-degrade-shrinkage-must-be-attributable.md)). After
two consecutive failures a rolling GitHub issue is opened and kept updated.

Builds run **weekly on Saturdays**. Sources publish weekly or every 48 hours, and
Chrome and Edge ship a major every two weeks; a daily schedule produced nothing but
no-op commits.

## Local development

```bash
git clone https://github.com/ShrekBytes/useragents-data.git
cd useragents-data

pip install -r requirements.txt

python -m unittest discover -s tests -t .   # 48 tests, no network
python scraper.py --check                   # run every check, write nothing
python scraper.py                           # build and publish locally
```

Requires Python 3.10+. The only dependency is `requests`.

### Adding a source

Implement `fetch(session) -> SourceResult` (see `uadata/sources.py`) and add it to
`SOURCES` in `scraper.py`. The core pipeline does not change: merging, provenance,
ordering, all three checks and both output formats are already per-source.

## Documentation

- [`CONTEXT.md`](CONTEXT.md) — vocabulary: Observed vs Synthetic UA, Provenance, Device Category
- [`docs/adr/`](docs/adr/) — why the pipeline is shaped this way

## Licence

MIT — see [LICENSE](LICENSE).

## Disclaimer

User agent strings are factual strings sent by HTTP clients. The frequency figures
attributed to `useragents.me` are that site's measurement and are redistributed as
described in [ADR-0006](docs/adr/0006-useragents-me-used-despite-no-licence.md).
Do not use this data to evade bot detection.
