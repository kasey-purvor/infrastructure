"""Instagram source — enumerate posts via the private user-feed API.

Why the feed API (i.instagram.com/api/v1/feed/user/{id}/) and not GraphQL:
- It paginates logged-out via `next_max_id` / `more_available` (the
  www.instagram.com/graphql/query doc_id path is gated + rotates and returns 400).
- It returns full-resolution image candidates (candidates[0] ≈ 1440px) vs the
  ~1080px display_url from web_profile_info.

web_profile_info is used only to resolve username -> numeric user id.
"""

from __future__ import annotations

import datetime
import random
import re
import time
from typing import Callable, Iterator, Protocol

from image_harvester.models import MediaItem, Post


class InstagramParseError(Exception):
    """Raised when an Instagram API response has an unexpected shape.

    The message is actionable: it states what was missing and what to check
    (API drift, private/blocked profile, rate-limit, or a ScrapFly error page).
    """


class _ClientProtocol(Protocol):
    """Minimal interface InstagramSource needs from its client."""

    def fetch_api_json(self, url: str, headers: dict | None = None) -> dict:
        ...


_IG_APP_ID = "936619743392459"
_PROFILE_INFO_URL = (
    "https://i.instagram.com/api/v1/users/web_profile_info/?username={username}"
)
_FEED_URL = "https://i.instagram.com/api/v1/feed/user/{user_id}/?count={count}"
_PAGE_COUNT = 12  # posts per feed page (verified logged-out); raise to cut credits

# media_type values in the private API
_MEDIA_IMAGE = 1
_MEDIA_VIDEO = 2
_MEDIA_CAROUSEL = 8


def _normalize_username(username_or_url: str) -> str:
    """Accept a bare username or a full profile URL; return the username."""
    s = username_or_url.strip().rstrip("/")
    m = re.match(r"https?://(?:www\.)?instagram\.com/([A-Za-z0-9_.]+)/?$", s)
    if m:
        return m.group(1)
    if "/" not in s:
        return s
    raise InstagramParseError(
        f"Cannot parse username from: {username_or_url!r}. "
        "Pass a bare username (e.g. 'madtev') or a full profile URL."
    )


def _headers() -> dict:
    return {"x-ig-app-id": _IG_APP_ID}


def _largest_candidate(node: dict) -> dict | None:
    """Return the largest image candidate (candidates[0]) for a media node, or None.

    Instagram sorts image_versions2.candidates largest-first.
    """
    candidates = node.get("image_versions2", {}).get("candidates", [])
    return candidates[0] if candidates else None


def _extract_media(item: dict) -> tuple[list[MediaItem], int]:
    """Return (images, skipped_videos) for a feed item.

    - media_type 2 (video post): no images, 1 skipped video.
    - media_type 8 (carousel): every image child; video children skipped.
    - media_type 1 (single image): one image.

    Carousel image indices are sequential (1-based) over images only, so a
    skipped video child does not leave a gap.
    """
    media_type = item.get("media_type")

    if media_type == _MEDIA_VIDEO:
        return [], 1

    if media_type == _MEDIA_CAROUSEL:
        images: list[MediaItem] = []
        skipped = 0
        index = 1
        for child in item.get("carousel_media", []):
            if child.get("media_type") == _MEDIA_VIDEO:
                skipped += 1
                continue
            cand = _largest_candidate(child)
            if cand is None:
                continue
            images.append(
                MediaItem(
                    index=index,
                    url=cand["url"],
                    width=cand.get("width", 0),
                    height=cand.get("height", 0),
                )
            )
            index += 1
        return images, skipped

    # single image (media_type 1), or an unknown type that still carries an image
    cand = _largest_candidate(item)
    if cand is None:
        return [], 0
    return [
        MediaItem(
            index=1,
            url=cand["url"],
            width=cand.get("width", 0),
            height=cand.get("height", 0),
        )
    ], 0


def _parse_item(item: dict) -> Post:
    """Parse a single feed item into a Post (image-only media items)."""
    try:
        shortcode = item["code"]
    except (KeyError, TypeError) as exc:
        raise InstagramParseError(
            "Feed item missing 'code' (shortcode). The API shape may have changed."
        ) from exc

    taken_at = datetime.datetime.fromtimestamp(
        item.get("taken_at", 0), tz=datetime.timezone.utc
    )
    caption_obj = item.get("caption") or {}
    caption = caption_obj.get("text", "") if isinstance(caption_obj, dict) else ""
    like_count = item.get("like_count", 0) or 0
    comment_count = item.get("comment_count", 0) or 0
    owner = (item.get("user") or {}).get("username", "")

    images, skipped_videos = _extract_media(item)

    return Post(
        shortcode=shortcode,
        taken_at=taken_at,
        owner=owner,
        caption=caption,
        like_count=like_count,
        comment_count=comment_count,
        images=images,
        skipped_videos=skipped_videos,
    )


class InstagramSource:
    """Enumerate public Instagram posts via the private user-feed API.

    All network calls go through the injected client (ScrapflyClient in
    production, a fake in tests).
    """

    def __init__(
        self,
        client: _ClientProtocol,
        page_delay: float = 2.0,
        sleep_fn: Callable[[float], None] | None = None,
    ) -> None:
        self._client = client
        # Politeness pause between feed pages during --all, so Instagram is less
        # likely to rate-limit deep pagination. Only the (sequential) enumeration
        # is paced; image downloads are unaffected. sleep_fn is injectable for tests.
        self._page_delay = page_delay
        self._sleep = sleep_fn if sleep_fn is not None else time.sleep

    def resolve_user_id(self, username: str) -> str:
        """Resolve a username to its numeric Instagram user id via web_profile_info."""
        raw = self._client.fetch_api_json(
            _PROFILE_INFO_URL.format(username=username), headers=_headers()
        )
        try:
            return raw["data"]["user"]["id"]
        except (KeyError, TypeError) as exc:
            raise InstagramParseError(
                f"Could not resolve a user id for {username!r}. The profile may not "
                "exist or be blocked, or ScrapFly returned an error page instead of JSON."
            ) from exc

    def iter_posts(
        self, username_or_url: str, fetch_all: bool = False
    ) -> Iterator[Post]:
        """Yield Post objects for the profile.

        fetch_all=False yields only the first feed page; True follows
        next_max_id to the end. Fail-loud (InstagramParseError) on any
        unexpected shape — already-yielded posts are preserved by the caller.
        """
        username = _normalize_username(username_or_url)
        user_id = self.resolve_user_id(username)

        max_id: str | None = None
        page = 0
        while True:
            page += 1
            if max_id and self._page_delay > 0:
                # Pace only subsequent pages (the first page has no max_id).
                self._sleep(self._page_delay + random.uniform(0, self._page_delay * 0.5))
            url = _FEED_URL.format(user_id=user_id, count=_PAGE_COUNT)
            if max_id:
                url += f"&max_id={max_id}"

            try:
                raw = self._client.fetch_api_json(url, headers=_headers())
            except Exception as exc:
                raise InstagramParseError(
                    f"Feed request failed on page {page}: {exc}. "
                    "Posts downloaded so far have been saved; re-run to resume."
                ) from exc

            if not isinstance(raw, dict) or raw.get("status") != "ok":
                got = raw.get("status") if isinstance(raw, dict) else type(raw).__name__
                raise InstagramParseError(
                    f"Feed page {page} did not return status 'ok' (got {got!r}). "
                    "Instagram may have changed the API, rate-limited the request, or "
                    "ScrapFly returned an error page. Posts downloaded so far are saved."
                )

            for item in raw.get("items", []):
                yield _parse_item(item)

            if not fetch_all:
                return
            if not raw.get("more_available") or not raw.get("next_max_id"):
                return
            max_id = raw["next_max_id"]
