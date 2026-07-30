"""ScrapFly API client — the single seam for all ScrapFly calls."""

from __future__ import annotations

import httpx


class ScrapflyError(Exception):
    """Raised when the ScrapFly API returns an unexpected response."""


class ScrapflyClient:
    """
    Thin wrapper around the ScrapFly scraping API.

    All ScrapFly calls go through here. ASP (anti-scraping protection) mode
    is always enabled; JS rendering is disabled (we only need JSON APIs).
    """

    _BASE = "https://api.scrapfly.io/scrape"

    def __init__(self, api_key: str, country: str = "us") -> None:
        self._api_key = api_key
        self._country = country
        self._client = httpx.Client(timeout=30.0)

    def fetch_api_json(self, url: str, headers: dict | None = None) -> dict:
        """
        Fetch *url* through ScrapFly and return the parsed JSON body.

        ScrapFly wraps the response in an envelope; this method unpacks it and
        returns only the scraped-page body (already parsed as JSON because we
        request format=json).

        Raises:
            ScrapflyError: on non-2xx ScrapFly response or malformed envelope.
        """
        params: dict = {
            "key": self._api_key,
            "url": url,
            "asp": "true",
            "render_js": "false",
            "country": self._country,
            "format": "json",
        }
        if headers:
            # ScrapFly takes custom request headers as bracketed query params,
            # one per header: `headers[Header-Name]=value` — NOT a JSON blob.
            # (Without this, x-ig-app-id never reaches Instagram and
            # web_profile_info returns an error/empty body.)
            for name, value in headers.items():
                params[f"headers[{name}]"] = value

        resp = self._client.get(self._BASE, params=params)
        if resp.status_code != 200:
            raise ScrapflyError(
                f"ScrapFly returned HTTP {resp.status_code} for {url}: {resp.text[:300]}"
            )

        envelope = resp.json()
        # ScrapFly response envelope: {"result": {"content": "...", "status_code": ...}, ...}
        try:
            result = envelope["result"]
            if result.get("status_code", 200) not in (200, 201):
                raise ScrapflyError(
                    f"Target returned HTTP {result['status_code']} via ScrapFly for {url}"
                )
            content = result["content"]
            if isinstance(content, str):
                import json
                return json.loads(content)
            return content
        except (KeyError, ValueError) as exc:
            raise ScrapflyError(
                f"Unexpected ScrapFly envelope shape for {url}: {exc}"
            ) from exc
