"""Shared test doubles.

Every remote service in this repository is someone else's server, so most tests
need a session that serves a fixed URL -> payload map and refuses anything else.
One definition, used by every test module that talks to a vendor.
"""

from typing import Any


class Response:
    def __init__(self, payload: Any, text: str | None = None):
        self._payload = payload
        self.text = text if text is not None else ""

    def raise_for_status(self) -> None:
        pass

    def json(self) -> Any:
        return self._payload


class FakeSession:
    """Serves a fixed URL -> payload map. Any other URL is a hard error."""

    def __init__(self, routes: dict[str, Any]):
        self.routes = routes
        self.requested: list[str] = []

    def get(self, url, timeout=None):
        self.requested.append(url)
        if url not in self.routes:
            raise AssertionError(f"unexpected request: {url}")
        return self.routes[url]
