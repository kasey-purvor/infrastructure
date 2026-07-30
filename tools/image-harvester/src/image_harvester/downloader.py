"""Direct CDN image downloader with validation, oe-expiry pre-check, and retry."""

from __future__ import annotations

import re
import time
import random
from typing import Callable
from urllib.parse import urlparse, parse_qs

import httpx

from image_harvester.models import DownloadResult


# Image magic bytes patterns
_MAGIC = {
    b"\xff\xd8\xff": "jpeg",
    b"\x89PNG\r\n\x1a\n": "png",
    b"RIFF": "webp",  # checked more carefully below
}


def _check_magic(content: bytes) -> bool:
    """Return True if content starts with a recognised image magic byte sequence."""
    if len(content) < 4:
        return False
    # JPEG
    if content[:3] == b"\xff\xd8\xff":
        return True
    # PNG
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    # WEBP: RIFF....WEBP
    if content[:4] == b"RIFF" and len(content) >= 12 and content[8:12] == b"WEBP":
        return True
    return False


def _parse_oe(url: str) -> int | None:
    """
    Extract the 'oe' query parameter (hex Unix timestamp) from a CDN URL.

    Returns the int timestamp, or None if 'oe' is not present.
    """
    try:
        qs = parse_qs(urlparse(url).query)
        oe_values = qs.get("oe", [])
        if oe_values:
            return int(oe_values[0], 16)
    except (ValueError, AttributeError):
        pass
    return None


class DownloadFailure(Exception):
    """Raised when all retries are exhausted. Contains the DownloadResult."""

    def __init__(self, result: DownloadResult) -> None:
        self.result = result
        super().__init__(result.error)


class Downloader:
    """
    Downloads images directly from Instagram's CDN.

    Validation pipeline per download:
    1. oe-expiry pre-check (skip doomed URLs before making any request)
    2. HTTP status == 200
    3. Content-Type starts with image/
    4. Magic byte header matches a real image format
    5. Content-Length (if present) matches actual bytes received

    Retries transient failures (5xx, network errors) with exponential backoff + jitter.
    Non-retriable failures (400/403/wrong content-type/magic mismatch/expiry) return
    immediately as a typed DownloadResult(success=False).

    Parameters:
        max_retries: maximum number of retry attempts (default 3)
        sleep_fn: injectable sleep function — pass ``lambda s: None`` in tests to
                  avoid real sleeps
        time_fn: injectable clock — returns current Unix timestamp as float.
                 Defaults to time.time(). Override in tests for deterministic expiry checks.
    """

    def __init__(
        self,
        max_retries: int = 3,
        sleep_fn: Callable[[float], None] | None = None,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self._max_retries = max_retries
        self._sleep = sleep_fn if sleep_fn is not None else time.sleep
        self._now = time_fn if time_fn is not None else time.time
        self._client = httpx.Client(timeout=30.0, follow_redirects=True)

    def fetch(self, url: str) -> DownloadResult:
        """
        Download *url* and return a DownloadResult.

        Never raises — errors are encoded as DownloadResult(success=False, error=...).
        """
        # --- Pre-check: oe expiry ---
        oe_ts = _parse_oe(url)
        if oe_ts is not None and oe_ts < self._now():
            return DownloadResult(
                url=url,
                success=False,
                error=(
                    f"URL has expired: oe={hex(oe_ts)} ({oe_ts}) is in the past "
                    f"(current time: {int(self._now())}). Re-enumerate the profile to get fresh URLs."
                ),
            )

        last_error = "unknown error"
        for attempt in range(self._max_retries + 1):
            if attempt > 0:
                # Exponential backoff with jitter: base 1s * 2^attempt ± 20% jitter
                delay = (2 ** attempt) * (0.8 + 0.4 * random.random())
                self._sleep(delay)

            result = self._attempt(url)
            if result.success:
                return result

            # Decide whether to retry
            if result.error and any(
                marker in result.error.lower()
                for marker in ("content-type", "content_type", "magic", "length mismatch", "image/")
            ):
                # Non-retriable validation failure
                return result

            last_error = result.error or last_error

        return DownloadResult(url=url, success=False, error=f"All retries exhausted: {last_error}")

    def _attempt(self, url: str) -> DownloadResult:
        """Single HTTP GET attempt with full validation."""
        try:
            resp = self._client.get(url)
        except httpx.HTTPError as exc:
            return DownloadResult(url=url, success=False, error=f"Network error: {exc}")

        if resp.status_code != 200:
            return DownloadResult(
                url=url,
                success=False,
                error=f"HTTP {resp.status_code}",
            )

        content_type = resp.headers.get("content-type", "")
        ct_base = content_type.split(";")[0].strip().lower()
        if not ct_base.startswith("image/"):
            return DownloadResult(
                url=url,
                success=False,
                error=f"content-type is not an image: {content_type!r}",
            )

        content = resp.content

        # Validate magic bytes
        if not _check_magic(content):
            return DownloadResult(
                url=url,
                success=False,
                error=(
                    f"magic byte mismatch: content does not start with a recognised "
                    f"image header (first 12 bytes: {content[:12].hex()!r})"
                ),
            )

        # Validate Content-Length if present
        cl_header = resp.headers.get("content-length")
        if cl_header is not None:
            try:
                expected = int(cl_header)
                actual = len(content)
                if expected != actual:
                    return DownloadResult(
                        url=url,
                        success=False,
                        error=(
                            f"length mismatch: Content-Length header says {expected} bytes "
                            f"but received {actual} bytes (truncated download?)"
                        ),
                    )
            except ValueError:
                pass  # malformed Content-Length — ignore

        return DownloadResult(
            url=url,
            success=True,
            content=content,
            content_type=ct_base,
        )
