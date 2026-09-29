"""What is shipping right now.

This is the input to the staleness assertion (ADR-0005), and in Phase 2 also to
synthetic UA generation. One manifest, so the two can never disagree about what
"current" means — which is the whole point.

Sources are vendor release APIs. They never contribute user agent strings to the
published data; a browser's version number is not a user agent.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

import requests

from .model import SourceError
from .sources import TIMEOUT, get_json

CHROMIUMDASH = "https://chromiumdash.appspot.com/fetch_releases?channel=Stable&platform={platform}&num=1"
FIREFOX_VERSIONS = "https://product-details.mozilla.org/1.0/firefox_versions.json"

# Microsoft's public release feed for Edge. Microsoft does not document it, but
# `ProductVersion` is the number the `Edg/` token already carries: stable Windows
# reads 154.0.4258.37, of which the freshness check compares the major.
EDGE_PRODUCTS = "https://edgeupdates.microsoft.com/api/products"

# Apple publishes no current-version feed of any kind. This is the documentation
# index behind developer.apple.com, which is JSON and is grouped by Safari major.
# It carries betas alongside shipped releases, so a major is only read once one of
# its notes is not labelled a beta.
SAFARI_RELEASE_NOTES = (
    "https://developer.apple.com/tutorials/data/documentation/safari-release-notes.json"
)

# Chrome publishes a channel per platform, so it is the one product that costs
# several requests. Every other vendor publishes one current version.
PLATFORMS = ("Windows", "Mac", "Linux", "Android")

# The platforms whose user agents carry `Edg/`. Edge on iOS and Android is
# `EdgiOS/` and `EdgA/`, which are not this repository's `edge` family, so an
# entry for them would assert freshness about strings we do not hold.
EDGE_PLATFORMS = {"Windows": "edge_windows", "MacOS": "edge_macos", "Linux": "edge_linux"}

# Apple titles a pre-release article "Safari 27.2 Beta Release Notes" and the
# shipped one "Safari 27 Release Notes". However recent it is, a beta has not
# shipped, and a manifest that counted one would leave the build red for the
# months before it does.
_BETA_TITLE = re.compile(r"\bbeta\b", re.IGNORECASE)
_MAJOR_SECTION = re.compile(r"Version\s+(\d+)")


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


def _ships(section: dict[str, Any], references: dict[str, Any]) -> bool:
    """Has this Safari major a release Apple has not labelled a beta?

    Conservative on purpose. A note we cannot resolve proves nothing either way,
    so the major is not claimed: the worst outcome is a freshness check that skips
    and says why, rather than one that fails every run over a beta.
    """
    identifiers = section.get("identifiers")
    if not isinstance(identifiers, list):
        return False
    for identifier in identifiers:
        reference = references.get(identifier)
        title = reference.get("title") if isinstance(reference, dict) else None
        if isinstance(title, str) and title and not _BETA_TITLE.search(title):
            return True
    return False


def _safari(session: requests.Session) -> list[tuple[str, int]]:
    """The newest Safari major that has shipped, read from Apple's own index."""
    payload = get_json(session, SAFARI_RELEASE_NOTES)
    if not isinstance(payload, dict):
        raise SourceError("safari_release_notes: expected an object")
    sections = payload.get("topicSections")
    references = payload.get("references")
    if not isinstance(sections, list) or not isinstance(references, dict):
        raise SourceError("safari_release_notes: expected topicSections and references")

    shipped = [
        match.group(1)
        for section in sections
        if isinstance(section, dict)
        and (match := _MAJOR_SECTION.fullmatch(str(section.get("title", ""))))
        and _ships(section, references)
    ]
    if not shipped:
        raise SourceError("safari_release_notes: no shipped release in the index")
    return [("safari", max(int(major) for major in shipped))]


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
    _collect(manifest, "safari", lambda: _safari(session))
    return manifest
