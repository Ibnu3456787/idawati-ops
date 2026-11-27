"""HTTP helpers for IDAWATI Ops.

All calls are unauthenticated reads of public endpoints. The runtime this
tool was built on has no direct internet egress: traffic must go through
the HTTP_PROXY/HTTPS_PROXY environment variables. ``requests`` honors those
automatically; this module additionally sanitizes NO_PROXY, because some
proxy libraries choke on bracketed IPv6 entries (e.g. ``[::1]``) in that
list. The sanitization only runs inside this process.
"""

from __future__ import annotations

import json
import os

import requests

USER_AGENT = "idawati-ops/1.0 (read-only public endpoints; no auth)"
DEFAULT_TIMEOUT = 25


class HttpError(Exception):
    """Raised when a public endpoint cannot be read."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def _sanitize_no_proxy() -> None:
    """Drop bracketed IPv6 literals from NO_PROXY (they break some clients).

    Those entries only ever match localhost addresses, which this tool never
    calls. Everything else in the list is left untouched.
    """
    for key in ("NO_PROXY", "no_proxy"):
        raw = os.environ.get(key)
        if not raw or "[" not in raw:
            continue
        cleaned = ",".join(
            part for part in raw.split(",") if not part.strip().startswith("[")
        )
        os.environ[key] = cleaned


_sanitize_no_proxy()
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": USER_AGENT})


def get_json(url: str, timeout: int = DEFAULT_TIMEOUT) -> object:
    """GET a URL and return the parsed JSON body.

    Raises HttpError on transport failure, non-2xx status, or bad JSON.
    """
    try:
        resp = _SESSION.get(url, timeout=timeout)
    except requests.RequestException as exc:
        raise HttpError(f"GET {url} failed: {exc}") from exc
    if resp.status_code >= 400:
        raise HttpError(
            f"GET {url} returned HTTP {resp.status_code}", status=resp.status_code
        )
    try:
        return resp.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise HttpError(f"GET {url} did not return JSON: {exc}") from exc


def get_text(url: str, timeout: int = DEFAULT_TIMEOUT) -> str:
    """GET a URL and return the response body as text (follows redirects)."""
    try:
        resp = _SESSION.get(url, timeout=timeout)
    except requests.RequestException as exc:
        raise HttpError(f"GET {url} failed: {exc}") from exc
    if resp.status_code >= 400:
        raise HttpError(
            f"GET {url} returned HTTP {resp.status_code}", status=resp.status_code
        )
    return resp.text


def post_text(
    url: str,
    payload: dict,
    timeout: int = DEFAULT_TIMEOUT,
    headers: dict | None = None,
) -> str:
    """POST a JSON body and return the raw response body as text.

    Same failure handling as post_json, but the body is returned
    unparsed — needed for endpoints that may answer with
    text/event-stream (SSE) instead of plain JSON.

    Raises HttpError on transport failure or non-2xx status.
    """
    merged = dict(_SESSION.headers)
    if headers:
        merged.update(headers)
    try:
        resp = _SESSION.post(url, json=payload, timeout=timeout, headers=merged)
    except requests.RequestException as exc:
        raise HttpError(f"POST {url} failed: {exc}") from exc
    if resp.status_code >= 400:
        raise HttpError(
            f"POST {url} returned HTTP {resp.status_code}", status=resp.status_code
        )
    return resp.text


def post_json(
    url: str,
    payload: dict,
    timeout: int = DEFAULT_TIMEOUT,
    headers: dict | None = None,
) -> object:
    """POST a JSON body and return the parsed JSON response.

    Raises HttpError on transport failure, non-2xx status, or bad JSON.
    ``headers`` (e.g. a stricter Accept) are merged over the defaults.
    """
    merged = dict(_SESSION.headers)
    if headers:
        merged.update(headers)
    try:
        resp = _SESSION.post(url, json=payload, timeout=timeout, headers=merged)
    except requests.RequestException as exc:
        raise HttpError(f"POST {url} failed: {exc}") from exc
    if resp.status_code >= 400:
        raise HttpError(
            f"POST {url} returned HTTP {resp.status_code}", status=resp.status_code
        )
    try:
        return resp.json()
    except (json.JSONDecodeError, ValueError) as exc:
        raise HttpError(f"POST {url} did not return JSON: {exc}") from exc
