"""The fidelity bar: two real parsers, asked the same question.

CONTEXT.md defines the bar as "indistinguishable from Observed UAs to a real User
Agent parser", and the plural is doing the work. One parser is one regex
database: it agrees with our templates whenever both were written against the
same idea of what Chrome sends. Two independent implementations only agree when
the string is genuinely the string.

The two are independent in the way that matters. `ua-parser` is the Python port
of the uap-core regex database; `ua-parser-js` is a separate project with its own
rules, and the two visibly disagree about vocabulary — `Mac OS X` against `macOS`,
`Chrome Mobile` against `Mobile Chrome`. That disagreement is the reason for two
parsers rather than one, and it is why the OS expectation carries a per-parser
alias instead of being compared case-insensitively.

Neither parser is a dependency of ingestion. They are needed to prove a Synthetic
string is real, and a string that cannot be proven is not published.
"""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable

from .sources import TIMEOUT

# ua-parser-js is a Node module, so the adapter runs Node. The repository root is
# where `npm install` put it, and it is not necessarily the working directory: the
# build's own tests run inside a temporary one.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

UAP_CORE = "uap-core"
UA_PARSER = "ua-parser"

# Each parser's own spelling of the families we generate. These live here rather
# than in the templates because they are facts about the parsers, not about the
# strings: uap-core calls macOS "Mac OS X" and ua-parser-js calls it "macOS", and
# both call Chrome on a phone something other than "Chrome". The tables are
# complete rather than sparse on purpose — a family added to the templates without
# an entry here raises, instead of quietly being compared against a name no parser
# would ever produce.
BROWSER_SPELLINGS: dict[str, dict[str, str]] = {
    UAP_CORE: {
        "chrome": "Chrome",
        "edge": "Edge",
        "firefox": "Firefox",
        "chrome mobile": "Chrome Mobile",
    },
    UA_PARSER: {
        "chrome": "Chrome",
        "edge": "Edge",
        "firefox": "Firefox",
        "chrome mobile": "Mobile Chrome",
    },
}

OS_SPELLINGS: dict[str, dict[str, str]] = {
    UAP_CORE: {
        "windows": "Windows",
        "macos": "Mac OS X",
        "linux": "Linux",
        "android": "Android",
    },
    UA_PARSER: {
        "windows": "Windows",
        "macos": "macOS",
        "linux": "Linux",
        "android": "Android",
    },
}

# Reads a JSON list of user agents on stdin and writes back a list of
# [browser family, browser major, os family] triples, in order. Written to fail
# loudly on a missing token rather than report an empty parse, which would read
# as "this string says nothing" instead of "the parser is wrong".
_JS = (
    "const parse = require('ua-parser-js');"
    "let raw = '';"
    "process.stdin.on('data', (chunk) => { raw += chunk; });"
    "process.stdin.on('end', () => {"
    "  const out = JSON.parse(raw).map((ua) => {"
    "    const r = parse(ua);"
    "    return [r.browser.name || null, r.browser.major || null, r.os.name || null];"
    "  });"
    "  process.stdout.write(JSON.stringify(out));"
    "});"
)


class ParserUnavailable(RuntimeError):
    """A declared parser could not be run, so nothing it says can be trusted.

    Not a skip. The whole point of this module is that published Synthetic
    strings were verified, and a verification that did not run is not a
    verification.
    """


@dataclass(frozen=True)
class Parse:
    """What one parser made of one string."""

    browser_family: str | None
    browser_major: int | None
    os_family: str | None

    def __str__(self) -> str:
        major = "-" if self.browser_major is None else self.browser_major
        return f"{self.browser_family} {major} on {self.os_family}"


def _int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=None)
def _uap_core(user_agents: tuple[str, ...]) -> dict[str, Parse]:
    try:
        from ua_parser import user_agent_parser
    except ImportError as exc:
        raise ParserUnavailable(f"{UAP_CORE}: {exc}") from exc
    out = {}
    for user_agent in user_agents:
        parsed = user_agent_parser.Parse(user_agent)
        out[user_agent] = Parse(
            parsed["user_agent"]["family"],
            _int(parsed["user_agent"]["major"]),
            parsed["os"]["family"],
        )
    return out


@lru_cache(maxsize=None)
def _ua_parser(user_agents: tuple[str, ...]) -> dict[str, Parse]:
    try:
        done = subprocess.run(
            ["node", "-e", _JS],
            input=json.dumps(list(user_agents)),
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
            cwd=REPO_ROOT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ParserUnavailable(f"{UA_PARSER}: {exc}") from exc
    if done.returncode != 0:
        raise ParserUnavailable(f"{UA_PARSER}: {done.stderr.strip() or done.returncode}")
    try:
        rows = json.loads(done.stdout)
    except ValueError as exc:
        raise ParserUnavailable(f"{UA_PARSER}: unparseable output: {exc}") from exc
    # A short reply is a broken adapter, not a short answer. Letting `zip` truncate
    # would leave the missing strings absent from the dict, and the caller's lookup
    # would raise a KeyError about a User Agent string — which reads as a bad string
    # rather than a parser that did not do its job.
    if not isinstance(rows, list) or len(rows) != len(user_agents):
        raise ParserUnavailable(
            f"{UA_PARSER}: {len(rows) if isinstance(rows, list) else '?'} results "
            f"for {len(user_agents)} user agents"
        )

    return {
        user_agent: Parse(family, _int(major), os_family)
        for user_agent, (family, major, os_family) in zip(user_agents, rows)
    }


ADAPTERS: dict[str, Callable[[tuple[str, ...]], dict[str, Parse]]] = {
    UAP_CORE: _uap_core,
    UA_PARSER: _ua_parser,
}

# The parsers this build must satisfy, in the order they are asked. Derived from
# the registry rather than declared beside it, so the two cannot disagree about
# which parsers exist. The order is the registry's insertion order and nothing
# depends on it: `check_fidelity` walks the registry itself.
PARSERS = tuple(ADAPTERS)


def browser_family(parser: str, family: str, mobile: bool = False) -> str:
    """The family name `parser` is expected to report.

    `mobile` because a phone is the one case where a parser's answer differs by
    more than capitalisation, and it differs *between* the two: `Mobile` in the
    string is the whole of the signal, and each parser resolves it to its own
    spelling of the same thing.
    """
    return BROWSER_SPELLINGS[parser]["chrome mobile" if mobile else family]


def os_family(parser: str, family: str) -> str:
    """The OS name `parser` is expected to report."""
    return OS_SPELLINGS[parser][family]
