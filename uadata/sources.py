"""Source plugins.

A source is anything that can turn a remote service into categorised Records.
Adding a source means adding an implementation here and listing it in
`scraper.py` — nothing in the core pipeline changes.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any, Protocol

import requests

from .model import Record, SourceError, SourceResult

USER_AGENT = "useragents-data/2.0 (+https://github.com/ShrekBytes/useragents-data)"
TIMEOUT = 30

# The published week range moves (observed shifting between two fetches minutes
# apart), so it is always discovered rather than computed. Computing it is how you
# end up requesting a 404 on the week the archive has not rolled to.
_WINDOW_RE = re.compile(r"/data/(\d{4}-\d{2}-\d{2})-to-(\d{4}-\d{2}-\d{2})-desktop\.json")


class Source(Protocol):
    name: str

    def fetch(self, session: requests.Session) -> SourceResult: ...


def get_json(session: requests.Session, url: str) -> Any:
    """GET and parse JSON, retrying once.

    A single retry because CI networks drop packets occasionally. Not more: a
    source that is genuinely down should fail fast and let the run continue on the
    other sources rather than spending the job's time budget being polite.
    """
    last: Exception | None = None
    for attempt in range(2):
        try:
            response = session.get(url, timeout=TIMEOUT)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last = exc
            if attempt == 0:
                time.sleep(2)
    raise SourceError(f"{url}: {last}")


def require_records(payload: Any, what: str) -> list[dict]:
    """Validate a source payload.

    A source returning an empty list, a dict, or rows without a `user_agent` is a
    failure, not an empty result. Treating those as "nothing to report" is exactly
    how this repo shipped the same 12 desktop strings for 13 months.
    """
    if not isinstance(payload, list):
        raise SourceError(f"{what}: expected a JSON list, got {type(payload).__name__}")
    if not payload:
        raise SourceError(f"{what}: source returned zero rows")
    for index, row in enumerate(payload):
        if not isinstance(row, dict) or not isinstance(row.get("user_agent"), str):
            raise SourceError(f"{what}: row {index} has no user_agent string")
        if not row["user_agent"].strip():
            raise SourceError(f"{what}: row {index} has a blank user_agent")
    return payload


class UserAgentsMe:
    """https://useragents.me

    Publishes dated JSON under /data/. Two families per category:

      <week>-<category>.json        measured traffic, has count/percentage
      <week>-latest-<category>.json newest observed, no counts

    The two overlap very little (2 of 27 on desktop, none on mobile or tablet), so
    taking both roughly triples what a single family yields.

    Unlicensed and all rights reserved by default (ADR-0006). Nothing here is
    load-bearing: removing it costs the dataset its frequency counts and nothing
    else.
    """

    name = "useragents.me"
    base_url = "https://useragents.me"
    # The site's own file set, which is not the same as CATEGORIES: there is a
    # `-latest-bot.json` equivalent nowhere on the site, so bots contribute measured
    # traffic only.
    categories = ("desktop", "mobile", "tablet", "bot")
    latest_categories = ("desktop", "mobile", "tablet")

    def fetch(self, session: requests.Session) -> SourceResult:
        window = self._discover_window(session)
        data_url = f"{self.base_url}/data/{window}"
        records: dict[str, list[Record]] = {}

        for category in self.categories:
            rows = require_records(
                get_json(session, f"{data_url}-{category}.json"),
                f"{window}-{category}",
            )
            records[category] = [self._to_record(r) for r in rows]

        for category in self.latest_categories:
            rows = require_records(
                get_json(session, f"{data_url}-latest-{category}.json"),
                f"{window}-latest-{category}",
            )
            records[category].extend(self._to_record(r) for r in rows)

        return SourceResult(
            name=self.name,
            records=records,
            meta={"window": window},
            collected_at=datetime.now(timezone.utc).isoformat(),
        )

    def _discover_window(self, session: requests.Session) -> str:
        try:
            response = session.get(self.base_url, timeout=TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise SourceError(f"homepage unreachable: {exc}") from exc

        windows = set(_WINDOW_RE.findall(response.text))
        if not windows:
            raise SourceError("no /data/<start>-to-<end>-desktop.json link on homepage")
        # Newest window wins; the homepage may advertise more than one.
        start, end = max(windows, key=lambda w: w[1])
        return f"{start}-to-{end}"

    def _to_record(self, row: dict) -> Record:
        def opt(value: Any, cast):
            if value is None:
                return None
            try:
                return cast(value)
            except (TypeError, ValueError) as exc:
                raise SourceError(f"unusable {row.get('user_agent')!r}: {exc}") from exc

        return Record(
            user_agent=row["user_agent"].strip(),
            os=row.get("os"),
            browser=row.get("browser"),
            device=row.get("device"),
            count=opt(row.get("count"), int),
            percentage=opt(row.get("percentage"), float),
            sources=(self.name,),
        )
