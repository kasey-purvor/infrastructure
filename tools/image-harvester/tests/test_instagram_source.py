"""Tests for InstagramSource — feed-API parsing + pagination, fully mocked."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from image_harvester.instagram import (
    InstagramSource,
    InstagramParseError,
    _normalize_username,
)

FIXTURE = Path(__file__).parent / "fixtures" / "feed_user_madtev.json"


def load_feed_page() -> dict:
    return json.loads(FIXTURE.read_text())


class FakeClient:
    """Dispatches by URL: web_profile_info -> id; feed/user -> next queued page."""

    def __init__(self, feed_pages: list[dict], user_id: str = "490875416") -> None:
        self._feed_pages = feed_pages
        self._user_id = user_id
        self._idx = 0
        self.calls: list[str] = []

    def fetch_api_json(self, url: str, headers: dict | None = None) -> dict:
        self.calls.append(url)
        if "web_profile_info" in url:
            return {"data": {"user": {"id": self._user_id, "username": "madtev",
                                      "is_private": False}}}
        if "feed/user" in url:
            page = self._feed_pages[self._idx]
            self._idx += 1
            return page
        raise AssertionError(f"unexpected url: {url}")

    @property
    def feed_calls(self) -> list[str]:
        return [c for c in self.calls if "feed/user" in c]


def page2_one_image(more: bool = False) -> dict:
    return {
        "status": "ok",
        "more_available": more,
        "next_max_id": None,
        "items": [{
            "media_type": 1, "code": "PAGE2AAAAAA", "pk": "123",
            "taken_at": 1700000000, "like_count": 5, "comment_count": 1,
            "caption": {"text": "page 2"}, "user": {"username": "madtev"},
            "image_versions2": {"candidates": [
                {"width": 1080, "height": 1080, "url": "https://cdn.example/p2.jpg"}]},
        }],
    }


# --- parsing ---------------------------------------------------------------

def test_first_page_parses_three_posts():
    client = FakeClient([load_feed_page()])
    posts = list(InstagramSource(client).iter_posts("madtev"))
    by_code = {p.shortcode: p for p in posts}
    assert set(by_code) == {"CxQwZ0gOIFp", "C38txz1Pt1w", "DZIdWpkxarx"}


def test_clean_carousel_yields_all_images():
    client = FakeClient([load_feed_page()])
    post = next(p for p in InstagramSource(client).iter_posts("madtev")
                if p.shortcode == "CxQwZ0gOIFp")
    assert len(post.images) == 4
    assert post.skipped_videos == 0
    assert [m.index for m in post.images] == [1, 2, 3, 4]


def test_carousel_with_video_child_drops_video_no_index_gap():
    client = FakeClient([load_feed_page()])
    post = next(p for p in InstagramSource(client).iter_posts("madtev")
                if p.shortcode == "C38txz1Pt1w")
    assert len(post.images) == 7          # 8 children - 1 video
    assert post.skipped_videos == 1
    assert [m.index for m in post.images] == [1, 2, 3, 4, 5, 6, 7]  # no gap


def test_video_post_yields_no_images():
    client = FakeClient([load_feed_page()])
    post = next(p for p in InstagramSource(client).iter_posts("madtev")
                if p.shortcode == "DZIdWpkxarx")
    assert post.images == []
    assert post.skipped_videos == 1


def test_images_use_full_resolution_candidate():
    client = FakeClient([load_feed_page()])
    post = next(p for p in InstagramSource(client).iter_posts("madtev")
                if p.shortcode == "CxQwZ0gOIFp")
    # candidates[0] is the largest; fixture's first child is 1440 wide
    assert post.images[0].width == 1440


def test_post_metadata_parsed():
    client = FakeClient([load_feed_page()])
    post = next(p for p in InstagramSource(client).iter_posts("madtev")
                if p.shortcode == "CxQwZ0gOIFp")
    assert post.owner == "madtev"
    assert post.like_count > 0
    assert post.taken_at.year == 2023


# --- pagination ------------------------------------------------------------

def test_no_pagination_when_not_fetch_all():
    page1 = load_feed_page()  # has more_available=True
    client = FakeClient([page1, page2_one_image()])
    posts = list(InstagramSource(client).iter_posts("madtev", fetch_all=False))
    assert len(posts) == 3
    assert len(client.feed_calls) == 1  # did NOT follow the cursor


def test_pagination_follows_cursor_until_exhausted():
    page1 = load_feed_page()  # more_available=True, next_max_id set
    client = FakeClient([page1, page2_one_image(more=False)])
    posts = list(InstagramSource(client).iter_posts("madtev", fetch_all=True))
    assert len(posts) == 4  # 3 from page 1 + 1 from page 2
    assert len(client.feed_calls) == 2
    assert f"max_id={page1['next_max_id']}" in client.feed_calls[1]


def test_pagination_stops_when_more_available_false():
    client = FakeClient([page2_one_image(more=False)])
    posts = list(InstagramSource(client).iter_posts("madtev", fetch_all=True))
    assert len(posts) == 1
    assert len(client.feed_calls) == 1


# --- politeness pacing ------------------------------------------------------

def test_page_delay_applied_between_pages():
    sleeps: list[float] = []
    client = FakeClient([load_feed_page(), page2_one_image(more=False)])
    src = InstagramSource(client, page_delay=2.0, sleep_fn=sleeps.append)
    list(src.iter_posts("madtev", fetch_all=True))
    assert len(sleeps) == 1        # one delay, between page 1 and page 2 only
    assert sleeps[0] >= 2.0        # at least the base delay


def test_no_page_delay_on_single_page():
    sleeps: list[float] = []
    client = FakeClient([load_feed_page()])
    src = InstagramSource(client, page_delay=2.0, sleep_fn=sleeps.append)
    list(src.iter_posts("madtev", fetch_all=False))
    assert sleeps == []            # only one page fetched -> no pacing pause


def test_page_delay_zero_disables_pacing():
    sleeps: list[float] = []
    client = FakeClient([load_feed_page(), page2_one_image(more=False)])
    src = InstagramSource(client, page_delay=0, sleep_fn=sleeps.append)
    list(src.iter_posts("madtev", fetch_all=True))
    assert sleeps == []


# --- fail-loud -------------------------------------------------------------

def test_fail_loud_on_non_ok_status():
    client = FakeClient([{"status": "fail", "message": "checkpoint_required"}])
    with pytest.raises(InstagramParseError):
        list(InstagramSource(client).iter_posts("madtev"))


def test_fail_loud_when_user_id_unresolvable():
    class BadClient:
        def fetch_api_json(self, url, headers=None):
            return {}  # no data.user.id

    with pytest.raises(InstagramParseError):
        list(InstagramSource(BadClient()).iter_posts("madtev"))


# --- username normalization ------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("madtev", "madtev"),
    ("https://www.instagram.com/madtev/", "madtev"),
    ("https://instagram.com/madtev", "madtev"),
    ("  madtev  ", "madtev"),
])
def test_normalize_username(raw, expected):
    assert _normalize_username(raw) == expected


def test_normalize_username_rejects_garbage():
    with pytest.raises(InstagramParseError):
        _normalize_username("https://example.com/some/deep/path")
