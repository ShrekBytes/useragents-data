# User Agents Data

A published dataset of user agent strings for people who need a realistic one — web
scraping, testing, HTTP client configuration. Not an application; a data product
whose only job is to be current and honest about where each record came from.

## Language

**User Agent (UA)**:
The string an HTTP client sends in its `User-Agent` header to describe itself.
_Avoid_: user agent string (say User Agent), agent, fingerprint

**Observed UA**:
A User Agent recorded from real client traffic by a source that publishes
telemetry. It is never constructed, so it is never a fiction — but a source is not
obliged to say how often it saw a string, so a frequency is carried only when one
was measured, and never invented from a source's ordering.
_Avoid_: real UA, live UA, scraped UA

**Synthetic UA**:
A User Agent constructed from genuine, currently-shipping product versions rather
than recorded from traffic. Plausible, never witnessed — therefore never carries a
frequency claim.
_Avoid_: generated UA, fake UA, made-up UA

**Provenance**:
The record of where an Observed UA came from and when it was collected. Which
source confirmed each string is held per record; when the collection happened is
held once per source per fetch, not repeated across every record. Never inferred,
never guessed, always present on Observed UAs.
_Avoid_: source, origin (too vague — pick one)

**Measurement Attribution**:
Naming the source that measured an Observed UA's frequency, held separately from
Provenance because confirming a string and counting it are different acts. A count
is only comparable within the source that measured it, so a frequency without
attribution is not publishable and two sources' counts are never ranked together.
_Avoid_: combined count, merged frequency, popularity

**Device Category**:
One of `desktop`, `mobile`, `tablet`, `bot`. Bots are a category in their own right,
not a flavour of desktop: roughly 69% of real traffic is non-browser clients.
_Avoid_: platform, form factor, device type

## Rules

- An Observed UA and a Synthetic UA are never mixed in one file. A consumer who
  assumes they are reading real traffic data must never receive a fabricated string.
- Synthetic UAs are held to a fidelity bar that keeps them indistinguishable from
  Observed UAs to a real User Agent parser. The bar is defined by test, not by eye.
