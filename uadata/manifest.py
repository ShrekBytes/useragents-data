"""What is shipping right now.

This is the input to the staleness assertion and to synthetic UA generation
(ADR-0005). One manifest, so the two can never disagree about what "current"
means — which is the whole point.

Sources are vendor release APIs. They never contribute user agent strings to the
published data; a browser's version number is not a user agent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import requests

from .model import SourceError
from .sources import get_json

CHROMIUMDASH = "https://chromiumdash.appspot.com/fetch_releases?channel=Stable&platform={platform}&num=1"
FIREFOX_VERSIONS = "https://product-details.mozilla.org/1.0/firefox_versions.json"

# Microsoft's public release feed for Edge. Microsoft does not document it, but
# `ProductVersion` is the number the `Edg/` token already carries: stable Windows
# reads 154.0.4258.37, of which the freshness check compares the major.
EDGE_PRODUCTS = "https://edgeupdates.microsoft.com/api/products"

# Safari is deliberately absent, and ADR-0010 records why: the only machine-readable
# thing Apple publishes about its current version is a documentation index, which
# reports versions Apple has not released to anyone and interleaves them with the
# ones it has. The regression check covers Safari instead.

# Chrome publishes a channel per platform, so it is the one product that costs
# several requests. Every other vendor publishes one current version.
PLATFORMS = ("Windows", "Mac", "Linux", "Android")

# The platforms whose user agents carry `Edg/`. Edge on iOS and Android is
# `EdgiOS/` and `EdgA/`, which are not this repository's `edge` family, so an
# entry for them would assert freshness about strings we do not hold.
EDGE_PLATFORMS = {"Windows": "edge_windows", "MacOS": "edge_macos", "Linux": "edge_linux"}


@dataclass
class Manifest:
    """Current major versions, keyed the same way as the dataset's browsers."""

    versions: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def major(self, product: str) -> int | None:
        return self.versions.get(product)

    def to_json(self) -> dict[str, Any]:
        return {"versions": dict(sorted(self.versions.items())), "errors": self.errors}


def _chrome(session: requests.Session, platform: str) -> list[tuple[str, int]]:
    payload = get_json(session, CHROMIUMDASH.format(platform=platform))
    if not isinstance(payload, list) or not payload:
        raise SourceError(f"chromiumdash {platform}: no releases returned")
    return [(platform.lower(), int(str(payload[0]["version"]).split(".")[0]))]


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


def _edge(session: requests.Session) -> list[tuple[str, int]]:
    """Current Edge stable, one entry per platform the dataset holds Edge for."""
    payload = get_json(session, EDGE_PRODUCTS)
    if not isinstance(payload, list):
        raise SourceError("edge_products: expected a list of products")
    stable = [p for p in payload if isinstance(p, dict) and p.get("Product") == "Stable"]
    if not stable:
        raise SourceError("edge_products: no Stable product in the response")

    majors: dict[str, int] = {}
    for release in stable[0].get("Releases") or []:
        if not isinstance(release, dict):
            continue
        product = EDGE_PLATFORMS.get(release.get("Platform"))
        version = release.get("ProductVersion")
        try:
            major = int(str(version).split(".")[0])
        except (AttributeError, IndexError, ValueError):
            continue
        if product is None:
            continue
        # A platform ships several builds, one per architecture, in no particular
        # order. The newest of them is the one that is current.
        majors[product] = max(majors.get(product, 0), major)
    if not majors:
        raise SourceError("edge_products: no stable build for a platform we hold Edge for")
    return sorted(majors.items())


def _collect(
    manifest: Manifest, label: str, read: Callable[[], list[tuple[str, int]]]
) -> None:
    """Record one vendor's products, or the reason we could not read them.

    A vendor we cannot read leaves no entry at all, which is what makes its
    freshness check skip with a stated reason. It never leaves a zero, and never
    leaves the last value we happened to see.
    """
    try:
        for product, major in read():
            manifest.versions[product] = major
    except (SourceError, KeyError, IndexError, ValueError) as exc:
        manifest.errors.append(f"{label}: {exc}")


def fetch_manifest(session: requests.Session) -> Manifest:
    """Collect current versions, degrading per-product rather than all-or-nothing.

    A vendor outage must not block ingestion. What it must do is stop us
    confidently declaring a stale dataset fresh, so failures are recorded and the
    affected freshness checks are skipped rather than silently passed.
    """
    manifest = Manifest()
    for platform in PLATFORMS:
        _collect(manifest, f"chrome/{platform}", lambda: _chrome(session, platform))
    _collect(manifest, "firefox", lambda: _firefox(session))
    _collect(manifest, "edge", lambda: _edge(session))
    return manifest
