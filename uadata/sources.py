"""Source plugins.

A source is anything that can turn a remote service into categorised Records: a
`name`, and a `fetch(session) -> SourceResult`. Adding a source means adding an
implementation here and listing it in `scraper.py` — nothing in the core pipeline
changes.

A source that measures frequency sets `count_source` on every record it measured;
one that does not must leave `count` alone. Getting that wrong is not a formatting
bug, it decides whether the record is ranked (ADR-0009).
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Any

import requests

from .model import Record, SourceError, SourceResult

USER_AGENT = "useragents-data/2.0 (+https://github.com/ShrekBytes/useragents-data)"
# Seconds one HTTP request may take, and — because `fidelity` reuses the same number
# for its Node subprocess — the whole budget for one fidelity oracle. A parser that
# cannot be run within it is reported as a failure, not a skip (ADR-0011).
TIMEOUT = 30

_PERIOD_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\s*(?:to|-)\s*(\d{4}-\d{2}-\d{2})")


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


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _named(product: Any) -> str | None:
    """`{"name": "Chrome", "version": "154.0.0"}` -> `"Chrome 154.0.0"`.

    The shape WinFuture23 publishes. Absent or malformed parts are dropped rather
    than rendered as "None", because a browser we cannot name is a null browser,
    not a browser called None.
    """
    if not isinstance(product, dict):
        return None
    parts = [str(p) for p in (product.get("name"), product.get("version")) if p]
    return " ".join(parts) or None


class UserAgentsMe:
    """https://useragents.me

    Publishes JSON via /api. Two families per category:

      common.<category>.data        measured traffic
      latest.<category>.data        newest observed

    The two overlap very little (2 of 27 on desktop, none on mobile or tablet), so
    taking both roughly triples what a single family yields.

    No licence published, all rights reserved by default, but the site owner has
    permitted the use (ADR-0006). Nothing here is load-bearing: removing it costs the
    dataset its frequency counts and nothing else.
    """

    name = "useragents.me"
    base_url = "https://useragents.me"
    api_url = f"{base_url}/api"
    # The site's own file set, which is not the same as CATEGORIES: there is no
    # latest bot bucket, so bots contribute measured traffic only.
    categories = ("desktop", "mobile", "tablet", "bot")
    latest_categories = ("desktop", "mobile", "tablet")

    def fetch(self, session: requests.Session) -> SourceResult:
        payload = get_json(session, self.api_url)
        response = self._response(payload)
        window = self._window(response)
        records: dict[str, list[Record]] = {}

        for category in self.categories:
            rows = self._rows(response, "common", category, f"{window}-common-{category}")
            records[category] = [self._to_record(r) for r in rows]

        for category in self.latest_categories:
            rows = self._rows(
                response,
                "latest",
                category,
                f"{window}-latest-{category}",
                required_measurement=False,
            )
            records[category].extend(self._to_record(r) for r in rows)

        return SourceResult(
            name=self.name,
            records=records,
            meta={"window": window},
            collected_at=_now(),
        )

    def _response(self, payload: Any) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise SourceError(f"api: expected an object, got {type(payload).__name__}")
        response = payload.get("response", payload)
        if not isinstance(response, dict):
            raise SourceError(
                f"api.response: expected an object, got {type(response).__name__}"
            )
        return response

    def _window(self, response: dict[str, Any]) -> str:
        period = response.get("period") or response.get("window")
        if not isinstance(period, str) or not period.strip():
            raise SourceError("api: missing period/window string")
        period = period.strip()
        match = _PERIOD_RE.search(period)
        if match:
            return f"{match.group(1)}-to-{match.group(2)}"
        return period

    def _rows(
        self,
        response: dict[str, Any],
        family: str,
        category: str,
        what: str,
        required_measurement: bool = True,
    ) -> list[dict[str, Any]]:
        buckets = response.get(family)
        if not isinstance(buckets, dict):
            raise SourceError(f"api.{family}: expected an object")
        bucket = buckets.get(category)
        if isinstance(bucket, dict):
            payload = bucket.get("data")
        else:
            payload = bucket

        if not isinstance(payload, list):
            raise SourceError(
                f"api.{family}.{category}.data: expected a JSON list, got {type(payload).__name__}"
            )
        rows = require_records(
            [self._normalise_row(row, what, index, required_measurement) for index, row in enumerate(payload)],
            what,
        )
        return rows

    def _normalise_row(
        self, row: Any, what: str, index: int, required_measurement: bool
    ) -> dict[str, Any]:
        if not isinstance(row, dict):
            raise SourceError(f"{what}: row {index} is not an object")
        user_agent = row.get("user_agent")
        if not isinstance(user_agent, str):
            user_agent = row.get("useragent")
        if not isinstance(user_agent, str):
            user_agent = ""

        count = self._value_int(row.get("count"), f"{what}: row {index} count")
        percentage = self._value_float(
            row.get("percentage"), f"{what}: row {index} percentage"
        )
        frequency = row.get("frequency")
        if count is None and frequency is not None:
            count = self._integral_frequency(frequency, what, index)
        elif percentage is None and frequency is not None:
            percentage = self._value_float(
                frequency, f"{what}: row {index} frequency"
            )
        if required_measurement and count is None:
            raise SourceError(
                f"{what}: row {index} has no count/frequency measurement"
            )
        if count is None and percentage is not None:
            raise SourceError(f"{what}: row {index} has a percentage but no count")

        return {
            "user_agent": user_agent,
            "os": row.get("os"),
            "browser": row.get("browser"),
            "device": row.get("device"),
            "count": count,
            "percentage": percentage,
        }

    def _value_int(self, value: Any, what: str) -> int | None:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError) as exc:
            raise SourceError(f"{what}: {exc}") from exc
        if not number.is_integer():
            raise SourceError(f"{what}: non-integral value {value!r}")
        return int(number)

    def _value_float(self, value: Any, what: str) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise SourceError(f"{what}: {exc}") from exc

    def _integral_frequency(self, value: Any, what: str, index: int) -> int:
        try:
            frequency = float(value)
        except (TypeError, ValueError) as exc:
            raise SourceError(f"{what}: row {index} frequency: {exc}") from exc
        if not frequency.is_integer():
            raise SourceError(
                f"{what}: row {index} has non-integral frequency {value!r} with no count"
            )
        return int(frequency)

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
            count_source=self.name if row.get("count") is not None else None,
            sources=(self.name,),
        )


class WinFuture23:
    """https://github.com/WinFuture23/real-world-user-agents

    CC0, refreshed every 48 hours, about 150 strings recorded off live traffic at
    WinFuture.de. It is the only source here whose current-version coverage is
    unambiguously redistributable (ADR-0008), which is what makes the dataset
    survive useragents.me going away.

    It publishes no counts. Its list is ordered by prevalence but the ordering is
    the only ranking it offers, so nothing from this source is ever presented as
    measured, and none of it may enter the published ranking (ADR-0009).
    """

    name = "winfuture23"
    url = (
        "https://raw.githubusercontent.com/WinFuture23/real-world-user-agents/"
        "main/user-agents.json"
    )

    # The source's own vocabulary, not ours. A value we do not recognise fails the
    # fetch rather than being filed under a guess: a string in the wrong Device
    # Category is a wrong record, and dropping it silently is the 13-month bug.
    DEVICE_CATEGORIES = {"computer": "desktop", "mobile": "mobile", "tablet": "tablet"}

    def fetch(self, session: requests.Session) -> SourceResult:
        payload = get_json(session, self.url)
        if not isinstance(payload, dict) or not isinstance(payload.get("user_agents"), list):
            raise SourceError("expected an object with a user_agents list")

        records: dict[str, list[Record]] = {}
        # The source names the field `ua`; we name it `user_agent`. Normalising here
        # means the shared validation sees the real payload, not a copy of it.
        rows = require_records(
            [
                {**row, "user_agent": row.get("ua")} if isinstance(row, dict) else {}
                for row in payload["user_agents"]
            ],
            self.name,
        )
        for row in rows:
            category = self.DEVICE_CATEGORIES.get(row.get("device_type"))
            if category is None:
                raise SourceError(f"unrecognised device_type {row.get('device_type')!r}")
            records.setdefault(category, []).append(
                Record(
                    user_agent=row["user_agent"].strip(),
                    os=_named(row.get("os")),
                    browser=_named(row.get("browser")),
                    sources=(self.name,),
                )
            )

        return SourceResult(
            name=self.name,
            records=records,
            meta={"window": payload.get("window")},
            # The source's own collection time, not ours. Provenance is when it was
            # collected, and the source knows that better than we do.
            collected_at=payload.get("generated_at") or _now(),
        )


class CrawlerUserAgents:
    """https://github.com/monperrus/crawler-user-agents

    MIT, around 1500 crawler patterns with the User Agent strings actually observed
    for each, 2100-odd distinct strings in all.

    The patterns are regular expressions and are not data. The `instances` are, and
    every one of them is a `bot` whatever browser token it carries: a Googlebot that
    spoofs iPhone Safari is still a crawler, and filing it under `mobile` because
    the string mentions Safari would be the most popular kind of wrong in this repo.

    No counts, so like WinFuture23 it contributes to the dataset's breadth and
    never to its ranking (ADR-0009).
    """

    name = "crawler-user-agents"
    url = (
        "https://raw.githubusercontent.com/monperrus/crawler-user-agents/"
        "master/crawler-user-agents.json"
    )

    def fetch(self, session: requests.Session) -> SourceResult:
        payload = get_json(session, self.url)
        if not isinstance(payload, list) or not payload:
            raise SourceError("expected a non-empty JSON list")

        observed = [
            instance
            for row in payload
            if isinstance(row, dict) and isinstance(row.get("instances"), list)
            for instance in row["instances"]
        ]
        rows = require_records([{"user_agent": ua} for ua in observed], self.name)

        return SourceResult(
            name=self.name,
            records={
                "bot": [
                    Record(user_agent=row["user_agent"].strip(), sources=(self.name,))
                    for row in rows
                ]
            },
            meta={"patterns": len(payload)},
            # This source publishes no collection timestamp, so ours is the only
            # honest one available: when we fetched, not when anything was seen.
            collected_at=_now(),
        )
