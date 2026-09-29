"""Synthetic User Agents, built from the manifest and from nothing else.

A Synthetic UA is a string we constructed. It carries no frequency claim and no
Provenance, because nobody witnessed it. What it does carry is a fidelity bar
defined by test, not by eye: two real User Agent parsers must read it exactly as
they would read the same browser on a real machine (CONTEXT.md).

Two rules decide what can be generated, and both come from the manifest.

**Versions come from the manifest, never from here.** The staleness oracle and
this generator read the same artifact, so they cannot disagree about what
"current" means (ADR-0005). A template whose manifest entry is missing produces
nothing and says so, rather than a string with a plausible number in it.

**Platform tokens are literals, and that is not a shortcut.** Chromium's User
Agent reduction froze the platform segment of every Chrome string it sends:
`Windows NT 10.0; Win64; x64` for Windows 10 *and* 11, `10_15_7` on macOS, and
the static `Linux; Android 10; K` on Android. Chromium documents these as literal
values that "will not update even if a user is on an updated operating system or
device". So the current Chrome-on-Android string carries no Android version at
all, and none needs sourcing. A platform token that *is* a live version is
exactly what this module refuses to invent.

What is deliberately absent, and why:

- **Firefox on Android.** Mozilla publishes no Android Firefox version in the
  product-details feed, and unlike Chromium it has not reduced the platform
  segment away — the string carries the device's real Android version, which we
  would have to invent. (Gecko does floor versions below 10 to `Android 10` to
  reduce fingerprinting, but everything from 10 up is reported as it is.) Desktop
  Firefox has no such problem and is generated.
- **Safari, and every iOS string.** Apple publishes no current version anywhere
  (ADR-0010), and iOS forks are `CriOS`/`FxiOS` whose only current version would
  come from that same absent feed.
- **Opera and Samsung Internet.** No vendor feed, same as above.
- **Bots.** A fabricated crawler string is a fabricated identity: it would name a
  bot that does not exist, under someone else's product.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable

from . import browsers
from .manifest import Manifest
from .model import SYNTHETIC, Record

WEBKIT = "AppleWebKit/537.36 (KHTML, like Gecko)"
SAFARI = "Safari/537.36"

# Chromium's frozen platform tokens, keyed by manifest platform.
CHROMIUM_PLATFORMS = {
    "windows": "Windows NT 10.0; Win64; x64",
    "mac": "Macintosh; Intel Mac OS X 10_15_7",
    "linux": "X11; Linux x86_64",
    "android": "Linux; Android 10; K",
}

# Gecko keeps the platform's own punctuation, which is one of the two platform
# tokens easy to get wrong: `10.15` with dots, against Chromium's `10_15_7` with
# underscores. Neither is the macOS version, but only Chromium's is a *frozen* one.
# Gecko did no User-Agent reduction: `nsHttpHandler.cpp` hardcodes `Intel Mac OS X
# 10.15` in `nsHttpHandler::InitUserAgentComponents` for Web compatibility (bug
# 1679929, Firefox 87), and `BuildUserAgent` appends it verbatim. The literal is
# keyed to no build and no channel, so ESR carries it as much as the release does.
# These are literals for the same practical reason — no version needs sourcing — by
# a different mechanism, and the mechanism is what has to be re-checked when a token
# changes.
#
# Do not "fix" `10.15` from the Observed corpus. Two Firefox-on-macOS strings in it
# report a live `15.8`, and the corpus cannot settle the question: at Firefox 156.0
# its two sources disagree about the token, so it is reporting what its clients send
# rather than what Firefox ships. ADR-0011 records the evidence and the two rejected
# alternatives.
GECKO_PLATFORMS = {
    "windows": "Windows NT 10.0; Win64; x64",
    "mac": "Macintosh; Intel Mac OS X 10.15",
    "linux": "X11; Linux x86_64",
}

# The label each platform's `os` field carries, which is also the OS family the
# fidelity check expects a parser to report. Lower-case because the two parsers
# disagree about presentation ("Mac OS X" versus "macOS") and `fidelity` holds the
# one alias each of them needs.
OS_FAMILIES = {
    "windows": "windows",
    "mac": "macos",
    "linux": "linux",
    "android": "android",
}

OS_LABELS = {
    "windows": "Windows 10",
    "mac": "macOS",
    "linux": "Linux",
    "android": "Android",
}

BROWSER_LABELS = {"chromium": "Chrome", "gecko": "Firefox", "edge": "Edge"}


@dataclass(frozen=True)
class Template:
    """One shape of User Agent, and everything the fidelity bar needs to judge it.

    `family`, `os` and `category` are expectations, not decoration: they are what
    two independent parsers must agree on, and a generated string is refused if
    it does not read back as them.
    """

    @property
    def mobile(self) -> bool:
        """Whether this is a phone. The one case where a parser's answer differs
        by more than capitalisation, and it differs *between* the two parsers."""
        return bool(self.form_factor)


    name: str
    product: str  # the manifest entry that supplies the version
    platform: str  # which platform token to use, keyed by engine's own table
    engine: str  # chromium | gecko | edge
    family: str  # a name from browsers.FAMILY_NAMES
    category: str  # Device Category, and the file it is published to
    os: str  # our OS vocabulary; the family each parser must report
    form_factor: str = ""  # "Mobile" on phones, "" on desktop and tablet


def _chromium(template: Template, major: int) -> str:
    suffix = f" {template.form_factor}" if template.form_factor else ""
    return (
        f"Mozilla/5.0 ({CHROMIUM_PLATFORMS[template.platform]}) {WEBKIT} "
        f"Chrome/{major}.0.0.0{suffix} {SAFARI}"
    )


def _edge(template: Template, major: int) -> str:
    # Chromium Edge ships the same Chromium major it reports in `Edg/`, so both
    # tokens carry it. Taking them from two different feeds would produce a string
    # no Edge build has ever sent, and the observed corpus shows the reduced
    # `Edg/<major>.0.0.0` form is what current builds actually send.
    return (
        f"Mozilla/5.0 ({CHROMIUM_PLATFORMS[template.platform]}) {WEBKIT} "
        f"Chrome/{major}.0.0.0 Safari/537.36 Edg/{major}.0.0.0"
    )


def _gecko(template: Template, major: int) -> str:
    # Firefox carries no AppleWebKit and no Safari token at all, and repeats the
    # version inside the platform comment as `rv:`. It is the shape most often
    # reconstructed as if it were a Chromium string.
    return (
        f"Mozilla/5.0 ({GECKO_PLATFORMS[template.platform]}; rv:{major}.0) "
        f"Gecko/20100101 Firefox/{major}.0"
    )


RENDERERS: dict[str, Callable[[Template, int], str]] = {
    "chromium": _chromium,
    "gecko": _gecko,
    "edge": _edge,
}

_DESKTOP = ("windows", "mac", "linux")

# Every browser the staleness oracle already asserts, on every platform its
# manifest entry covers. Read the table as the specification of a current string:
# if a real client would not send this, it is wrong here too.
TEMPLATES: tuple[Template, ...] = tuple(
    [
        Template(
            name=f"chrome-{platform}",
            product=platform,
            platform=platform,
            engine="chromium",
            family="chrome",
            category="desktop",
            os=OS_FAMILIES[platform],
        )
        for platform in _DESKTOP
    ]
    + [
        # `Mobile` and its absence are both real: Chromium keeps the token for
        # phones and drops it for tablets, and that single token is the only
        # difference between the two Android strings a reduced Chrome sends.
        Template(
            name="chrome-android",
            product="android",
            platform="android",
            engine="chromium",
            family="chrome",
            category="mobile",
            os="android",
            form_factor="Mobile",
        ),
        Template(
            name="chrome-android-tablet",
            product="android",
            platform="android",
            engine="chromium",
            family="chrome",
            category="tablet",
            os="android",
        ),
    ]
    + [
        # The manifest names Edge's macOS entry `edge_macos`, not `edge_mac`: it is
        # Microsoft's own platform string, and guessing our own would silently skip
        # Edge on the one platform where a guess looks like a pass.
        Template(
            name=f"edge-{platform}",
            product=f"edge_{'macos' if platform == 'mac' else platform}",
            platform=platform,
            engine="edge",
            family="edge",
            category="desktop",
            os=OS_FAMILIES[platform],
        )
        for platform in _DESKTOP
    ]
    + [
        # Two Firefox channels, because one is not enough. The manifest reads both
        # `firefox` and `firefox_esr`, ESR is a supported release rather than a
        # back-port, and the two rarely collide with the Observed corpus: a
        # current release Firefox is one of the most observed strings there is, so
        # without ESR the Synthetic set would lose Firefox outright on any run
        # where the release is in the corpus.
        Template(
            name=f"firefox-{channel}-{platform}",
            product=channel,
            platform=platform,
            engine="gecko",
            family="firefox",
            category="desktop",
            os=OS_FAMILIES[platform],
        )
        for channel in ("firefox", "firefox_esr")
        for platform in _DESKTOP
    ]
)

TEMPLATES_BY_NAME = {template.name: template for template in TEMPLATES}


def browser_label(template: Template, major: int) -> str:
    """The `browser` field this template's record carries.

    One function, read by the generator and by `check_fidelity`, so the label
    published next to a string and the label the fidelity check demands cannot
    drift apart into two different definitions of the same product.

    Deliberately the product's own name and not the parser's: a phone publishes
    `Chrome 155`, and both parsers read it as `Mobile Chrome 155`. Those are the
    same fact in two vocabularies, and the published one is the dataset's.
    """
    return f"{BROWSER_LABELS[template.engine]} {major}"


def os_label(template: Template) -> str:
    """The `os` field this template's record carries."""
    return OS_LABELS[template.platform]


class SyntheticError(RuntimeError):
    """The generator produced a string it cannot stand behind.

    Raised at construction, for the same reason `Record` refuses a count with no
    source: by the time the string is published, it is already in the file.
    """


def render(template: Template, major: int) -> str:
    """Build one User Agent, then read it back with this repository's own parser.

    The cross-check is the cheapest fidelity test there is. `browsers` is the same
    family detection the staleness oracle uses, so a typo in a platform token or a
    token in the wrong order shows up here rather than shipping a string the
    dataset's own tooling cannot classify.
    """
    user_agent = RENDERERS[template.engine](template, major)
    if browsers.detect(user_agent) != template.family:
        raise SyntheticError(
            f"{template.name}: {user_agent!r} reads as "
            f"{browsers.detect(user_agent)!r}, not {template.family!r}"
        )
    if browsers.major(user_agent, template.family) != major:
        raise SyntheticError(
            f"{template.name}: {user_agent!r} reports "
            f"{browsers.major(user_agent, template.family)}, not {major}"
        )
    return user_agent


@dataclass(frozen=True)
class Withheld:
    """A template that produced no record, and why.

    Both reasons are silent by nature — a version we could not read, or a string we
    already hold as Observed — and a template that vanishes without a name is how a
    browser leaves a published dataset without anybody deciding to. So every
    withheld template carries its reason out to the check that reports it.
    """

    name: str
    reason: str


def build(
    manifest: Manifest, observed: Iterable[str]
) -> tuple[list[Record], list[Withheld]]:
    """Every Synthetic record the manifest supports, minus what we have observed.

    A string that is already in the Observed corpus is not published as Synthetic.
    It is a real string, we hold it as real, and calling it a fabrication would
    make the Synthetic dataset's one promise — never witnessed — untrue
    (ADR-0002). It leaves the set instead, named in the returned `Withheld` list so
    `check_synthetic` can say so out loud rather than letting the count shrink.

    Returns the records and the templates that produced none.
    """
    seen = set(observed)
    records: list[Record] = []
    withheld: list[Withheld] = []
    for template in TEMPLATES:
        major = manifest.major(template.product)
        if major is None:
            # No manifest entry means no version we can vouch for. Skipped, not
            # guessed, and the freshness check is skipped for the same reason —
            # but named, because a vendor outage would otherwise take six of the
            # fourteen templates out of the dataset with nothing to show for it.
            withheld.append(Withheld(template.name, f"no manifest entry for {template.product}"))
            continue
        user_agent = render(template, major)
        if user_agent in seen:
            withheld.append(Withheld(template.name, "already Observed"))
            continue
        seen.add(user_agent)
        records.append(
            Record(
                user_agent=user_agent,
                kind=SYNTHETIC,
                os=os_label(template),
                browser=browser_label(template, major),
                synthesized_from=template.name,
            )
        )
    return records, withheld


def by_category(records: list[Record]) -> dict[str, list[Record]]:
    """The generated records grouped into the files they are published to.

    Grouped by the template's Device Category rather than by anything the record
    says, so the file a string lands in cannot disagree with the one its generation
    was written for.
    """
    grouped: dict[str, list[Record]] = {}
    for record in records:
        template = TEMPLATES_BY_NAME[record.synthesized_from]
        grouped.setdefault(template.category, []).append(record)
    return grouped
