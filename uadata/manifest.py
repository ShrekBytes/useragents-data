"""What is shipping right now.

This is the input to the staleness assertion (ADR-0005), and in Phase 2 also to
synthetic UA generation. One manifest, so the two can never disagree about what
"current" means — which is the whole point.

Sources are vendor release APIs. They never contribute user agent strings to the
published data; a browser's version number is not a user agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import requests

from .model import SourceError
from .sources import TIMEOUT, get_json

CHROMIUMDASH = "https://chromiumdash.appspot.com/fetch_releases?channel=Stable&platform={platform}&num=1"
FIREFOX_VERSIONS = "https://product-details.mozilla.org/1.0/firefox_versions.json"

# Only browsers whose stable version moves fast enough to prove a freeze. Safari
# publishes no machine-readable current version, and Edge's is markdown-scraped;
# both are added in Phase 2 if they earn it. Chrome and Firefox alone are enough to
# catch a dataset that stopped updating.
PLATFORMS = ("Windows", "Mac", "Linux", "Android")


@dataclass
class Manifest:
    """Current major versions, keyed the same way as the dataset's browsers."""

    versions: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def major(self, product: str) -> int | None:
        return self.versions.get(product)

    def to_json(self) -> dict[str, Any]:
        return {"versions": dict(sorted(self.versions.items())), "errors": self.errors}


def _chrome(session: requests.Session, platform: str) -> tuple[str, int]:
    payload = get_json(session, CHROMIUMDASH.format(platform=platform))
    if not isinstance(payload, list) or not payload:
        raise SourceError(f"chromiumdash {platform}: no releases returned")
    return platform.lower(), int(str(payload[0]["version"]).split(".")[0])


def _firefox(session: requests.Session) -> list[tuple[str, int]]:
    payload = get_json(session, FIREFOX_VERSIONS)
    if not isinstance(payload, dict):
        raise SourceError("firefox_versions: expected an object")
    versions = []
    for key, product in (("LATEST_FIREFOX_VERSION", "firefox"), ("FIREFOX_ESR", "firefox_esr")):
        raw = payload.get(key)
        if raw:
            versions.append((product, int(str(raw).split(".")[0])))
    if not versions:
        raise SourceError("firefox_versions: no released version fields present")
    return versions


def fetch_manifest(session: requests.Session) -> Manifest:
    """Collect current versions, degrading per-product rather than all-or-nothing.

    A vendor outage must not block ingestion. What it must do is stop us
    confidently declaring a stale dataset fresh, so failures are recorded and the
    affected freshness checks are skipped rather than silently passed.
    """
    manifest = Manifest()
    for platform in PLATFORMS:
        try:
            product, major = _chrome(session, platform)
            manifest.versions[product] = major
        except (SourceError, KeyError, IndexError, ValueError) as exc:
            manifest.errors.append(f"chrome/{platform}: {exc}")
    try:
        for product, major in _firefox(session):
            manifest.versions[product] = major
    except (SourceError, KeyError, ValueError) as exc:
        manifest.errors.append(f"firefox: {exc}")
    return manifest
