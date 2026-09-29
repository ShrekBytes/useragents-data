# Sources are consumed as data files, never parsed from HTML

The scraper parsed HTML tables located by `h2 id="..."` anchors on useragents.me.
When those anchors were renamed, every extraction silently returned an empty list
and the dataset froze at browser version 134 for roughly 13 months while `scraped_at`
kept advancing and CI reported success.

The same site now publishes dated files at `/data/<start>-to-<end>-<category>.json`
carrying `user_agent`, `count`, `percentage`, `os`, `browser`, `device`. Ingestion
reads those files. No source's *data* is obtained by scraping a rendered page.

There is one narrow exception. The current published week range is not derivable —
weeks publish after they close, and the range advertised on the homepage moved
between two requests minutes apart — so it is discovered by matching the homepage's
`/data/...json` *links*. This is URL discovery, not scraping: nothing is read out of
page content, and if the pattern does not match the source fails loudly rather than
continuing on a guessed range.

The tradeoff is real: data files are versioned and can disappear when a site's
schema changes, exactly as HTML anchors did. Accepted anyway, because a changed
data schema fails loudly on the field we require, whereas changed markup fails
silently. The 13-month outage was not caused by scraping — it was caused by
scraping that could not tell it had failed.
