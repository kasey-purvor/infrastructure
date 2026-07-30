"""Tests for downloader.py — direct CDN download with validation."""

from __future__ import annotations

import time
import pytest
import respx
import httpx

from image_harvester.downloader import Downloader, DownloadFailure

# Real JPEG magic bytes header
JPEG_MAGIC = b"\xff\xd8\xff\xe0" + b"\x00" * 100
PNG_MAGIC = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
WEBP_MAGIC = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 100

# A valid-ish URL with non-expired oe param (far future: 0x7FFFFFFF = year 2038)
FUTURE_URL = "https://scontent.cdninstagram.com/v/img.jpg?oe=7FFFFFFF&other=x"
# Expired oe param (oe=1 = epoch + 1 second)
EXPIRED_URL = "https://scontent.cdninstagram.com/v/img.jpg?oe=00000001&other=x"


class TestValidJpeg:
    @respx.mock
    def test_valid_jpeg_returns_success(self):
        respx.get(FUTURE_URL).mock(
            return_value=httpx.Response(
                200,
                content=JPEG_MAGIC,
                headers={"Content-Type": "image/jpeg", "Content-Length": str(len(JPEG_MAGIC))},
            )
        )
        dl = Downloader(sleep_fn=lambda s: None)
        result = dl.fetch(FUTURE_URL)
        assert result.success is True
        assert result.content == JPEG_MAGIC
        assert result.content_type == "image/jpeg"

    @respx.mock
    def test_valid_png_returns_success(self):
        respx.get(FUTURE_URL).mock(
            return_value=httpx.Response(
                200,
                content=PNG_MAGIC,
                headers={"Content-Type": "image/png"},
            )
        )
        dl = Downloader(sleep_fn=lambda s: None)
        result = dl.fetch(FUTURE_URL)
        assert result.success is True
        assert result.content_type == "image/png"

    @respx.mock
    def test_valid_webp_returns_success(self):
        respx.get(FUTURE_URL).mock(
            return_value=httpx.Response(
                200,
                content=WEBP_MAGIC,
                headers={"Content-Type": "image/webp"},
            )
        )
        dl = Downloader(sleep_fn=lambda s: None)
        result = dl.fetch(FUTURE_URL)
        assert result.success is True
        assert result.content_type == "image/webp"


class TestValidationFailures:
    @respx.mock
    def test_200_but_html_content_type_is_failure(self):
        respx.get(FUTURE_URL).mock(
            return_value=httpx.Response(
                200,
                content=b"<html></html>",
                headers={"Content-Type": "text/html"},
            )
        )
        dl = Downloader(sleep_fn=lambda s: None)
        result = dl.fetch(FUTURE_URL)
        assert result.success is False
        assert "content-type" in result.error.lower() or "content_type" in result.error.lower() or "image" in result.error.lower()

    @respx.mock
    def test_200_bytes_mismatch_content_length_is_failure(self):
        body = JPEG_MAGIC
        respx.get(FUTURE_URL).mock(
            return_value=httpx.Response(
                200,
                content=body,
                # Claim more bytes than we actually send
                headers={"Content-Type": "image/jpeg", "Content-Length": str(len(body) + 500)},
            )
        )
        dl = Downloader(sleep_fn=lambda s: None)
        result = dl.fetch(FUTURE_URL)
        assert result.success is False
        assert result.error is not None

    @respx.mock
    def test_403_is_failure(self):
        respx.get(FUTURE_URL).mock(
            return_value=httpx.Response(403, content=b"Forbidden", headers={"Content-Type": "text/plain"})
        )
        dl = Downloader(sleep_fn=lambda s: None)
        result = dl.fetch(FUTURE_URL)
        assert result.success is False

    @respx.mock
    def test_magic_byte_mismatch_is_failure(self):
        """File claims to be JPEG but starts with bad bytes."""
        bad_body = b"\x00\x00\x00\x00" * 30  # not JPEG/PNG/WEBP
        respx.get(FUTURE_URL).mock(
            return_value=httpx.Response(
                200,
                content=bad_body,
                headers={"Content-Type": "image/jpeg"},
            )
        )
        dl = Downloader(sleep_fn=lambda s: None)
        result = dl.fetch(FUTURE_URL)
        assert result.success is False
        assert result.error is not None


class TestOeExpiry:
    def test_expired_oe_fails_without_http_request(self):
        """Pre-check: expired oe param must fail before any network call."""
        # Use a mock that would fail if called — but the pre-check should prevent any call
        with respx.mock(assert_all_called=False) as mock:
            route = mock.get(EXPIRED_URL).mock(
                return_value=httpx.Response(200, content=JPEG_MAGIC, headers={"Content-Type": "image/jpeg"})
            )
            dl = Downloader(sleep_fn=lambda s: None, time_fn=lambda: time.time())
            result = dl.fetch(EXPIRED_URL)

        assert result.success is False
        assert "expired" in result.error.lower() or "oe" in result.error.lower()
        assert not route.called  # no HTTP call was made

    @respx.mock
    def test_future_oe_does_not_fail_expiry_check(self):
        """URL with far-future oe passes the pre-check (reaches network)."""
        respx.get(FUTURE_URL).mock(
            return_value=httpx.Response(
                200,
                content=JPEG_MAGIC,
                headers={"Content-Type": "image/jpeg"},
            )
        )
        dl = Downloader(sleep_fn=lambda s: None)
        result = dl.fetch(FUTURE_URL)
        assert result.success is True


class TestRetry:
    @respx.mock
    def test_transient_5xx_then_success_retries(self):
        """One 500 then a 200 — downloader should retry and succeed."""
        sleep_calls = []
        dl = Downloader(sleep_fn=lambda s: sleep_calls.append(s), max_retries=3)

        route = respx.get(FUTURE_URL)
        route.side_effect = [
            httpx.Response(500, content=b"error", headers={"Content-Type": "text/plain"}),
            httpx.Response(
                200,
                content=JPEG_MAGIC,
                headers={"Content-Type": "image/jpeg"},
            ),
        ]

        result = dl.fetch(FUTURE_URL)
        assert result.success is True
        assert len(sleep_calls) >= 1  # backoff sleep was called

    @respx.mock
    def test_exhausted_retries_returns_failure(self):
        """All retries return 500 — should fail after max_retries."""
        dl = Downloader(sleep_fn=lambda s: None, max_retries=2)

        respx.get(FUTURE_URL).mock(
            return_value=httpx.Response(500, content=b"err", headers={"Content-Type": "text/plain"})
        )

        result = dl.fetch(FUTURE_URL)
        assert result.success is False
