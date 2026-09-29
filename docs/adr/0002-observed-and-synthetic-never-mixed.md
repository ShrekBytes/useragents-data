# Observed and Synthetic UAs never share a file

Observed UAs are recorded from real traffic and carry a real-world frequency.
Synthetic UAs are constructed from currently-shipping product versions and carry no
frequency claim at all. They live in separate files and are never merged into one
list, even when that would be more convenient.

A consumer who picks a random entry from `common/desktop.json` to put in a
`requests.get()` header is making an implicit trust claim: this string is what real
clients send. Mixing in a fabricated string would quietly break that claim for
anyone who later reports "our tests never see this UA in production."

This will look like an opportunity to simplify. It is not one.
