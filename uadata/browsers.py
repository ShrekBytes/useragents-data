"""Browser family detection and version extraction.

Used by the staleness assertion to ask "how current is the newest thing in this
dataset?", and in Phase 2 to validate synthetic UAs. Kept separate from the
manifest because these answer different questions: this one reads versions out of
strings we hold, the manifest asks the vendors what is current.
"""

from __future__ import annotations

import re
from typing import Iterable

# Ordered: the first match wins. Chromium forks all carry "Chrome/", so they must
# be tested first or every Edge and Opera string reads as Chrome — which would let
# a dataset full of stale Edge strings look current because one Chrome string is
# new. Safari is matched on "Version/" because every WebKit UA carries "Safari/"
# but only Safari carries "Version/".
FAMILIES: tuple[tuple[str, re.Pattern[str], re.Pattern[str]], ...] = (
    ("edge", re.compile(r"\b(?:Edg|Edge)/(\d+)"), re.compile(r"\b(?:Edg|Edge)/")),
    ("opera", re.compile(r"\b(?:OPR|OPiOS)/(\d+)"), re.compile(r"\b(?:OPR|OPiOS)/")),
    ("samsung", re.compile(r"\bSamsungBrowser/(\d+)"), re.compile(r"\bSamsungBrowser/")),
    ("chrome_ios", re.compile(r"\bCriOS/(\d+)"), re.compile(r"\bCriOS/")),
    ("firefox_ios", re.compile(r"\bFxiOS/(\d+)"), re.compile(r"\bFxiOS/")),
    ("chrome", re.compile(r"\bChrom(?:e|ium)/(\d+)"), re.compile(r"\bChrom(?:e|ium)/")),
    ("firefox", re.compile(r"\bFirefox/(\d+)"), re.compile(r"\bFirefox/")),
    ("safari", re.compile(r"\bVersion/(\d+)"), re.compile(r"\bVersion/")),
)

FAMILY_NAMES = tuple(name for name, _, _ in FAMILIES)

_BY_NAME = {name: version_re for name, version_re, _ in FAMILIES}


def detect(ua: str) -> str | None:
    """The browser family a user agent string belongs to, or None if unrecognised."""
    for _name, version_re, present_re in FAMILIES:
        if present_re.search(ua):
            return _name
    return None


def major(ua: str, family: str) -> int | None:
    """The major version a string reports for a family, or None if it reports none.

    Gated on `detect` so a family is only ever read from a string that belongs to
    it. Edge and Opera strings carry "Chrome/" as well, and reading their version
    as Chrome's would let a dataset holding nothing but stale fork strings report a
    current Chrome major.
    """
    if detect(ua) != family:
        return None
    match = _BY_NAME[family].search(ua)
    return int(match.group(1)) if match else None


def max_major(uas: Iterable[str], family: str) -> int | None:
    """Newest major version for a family across a set of user agent strings."""
    majors = [m for m in (major(ua, family) for ua in uas) if m is not None]
    return max(majors) if majors else None


def majors(uas: Iterable[str]) -> dict[str, int | None]:
    """Newest major per family, for every family we track."""
    uas = list(uas)
    return {family: max_major(uas, family) for family in FAMILY_NAMES}
