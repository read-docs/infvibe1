"""Blocking HTTP(S) GET with the app's User-Agent and timeouts."""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, NamedTuple

_USER_AGENT = "SkyWatch/0.1 (school project)"
_TIMEOUT_SECONDS = 20


class HttpError(Exception):
    def __init__(self, status: int, message: str):
        """status is the HTTP status, or 0 when the request never got a response."""
        super().__init__(message)
        self.status = status


class HttpResponse(NamedTuple):
    status: int
    body: str


def http_get(url: str) -> HttpResponse:
    """GET over HTTP or HTTPS, following redirects. Raises HttpError on network
    failure; non-2xx responses are returned so callers can read API error bodies."""
    parts = urllib.parse.urlsplit(url)
    if not parts.scheme or not parts.netloc:
        raise HttpError(0, f"bad url: {url}")
    origin = f"{parts.scheme}://{parts.netloc}"
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS) as res:
            return HttpResponse(res.status, res.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        with e:
            return HttpResponse(e.code, e.read().decode("utf-8", errors="replace"))
    except (urllib.error.URLError, OSError, ValueError) as e:
        reason = getattr(e, "reason", e)
        raise HttpError(0, f"request to {origin} failed: {reason}") from None


def url_encode(s: str) -> str:
    """Percent-encodes a string for use as a URL query parameter value."""
    return urllib.parse.quote(s, safe="")


def parse_json(text: str) -> Any:
    """The parsed JSON, or None when the text isn't JSON."""
    try:
        return json.loads(text)
    except ValueError:
        return None
