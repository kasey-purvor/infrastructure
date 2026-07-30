"""Data models for image-harvester."""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class MediaItem:
    """A single image within a post (carousel slot or standalone)."""

    index: int  # 1-based carousel position
    url: str
    width: int
    height: int


@dataclass
class Post:
    """A single Instagram post with its image-only media items."""

    shortcode: str
    taken_at: datetime.datetime
    owner: str
    caption: str
    like_count: int
    comment_count: int
    images: list[MediaItem]
    skipped_videos: int = 0

    @property
    def post_url(self) -> str:
        return f"https://www.instagram.com/p/{self.shortcode}/"


@dataclass
class DownloadResult:
    """Result of a single image download attempt."""

    url: str
    success: bool
    content: Optional[bytes] = None
    content_type: Optional[str] = None
    error: Optional[str] = None

    @property
    def ext(self) -> str:
        """Derive file extension from content_type."""
        if not self.content_type:
            return "jpg"
        mapping = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
            "image/gif": "gif",
        }
        base = self.content_type.split(";")[0].strip().lower()
        return mapping.get(base, "jpg")


@dataclass
class PlannedPath:
    """The intended filesystem path for a media item."""

    stem: str  # e.g. "2023-09-16_CxQwZ0gOIFp_01"
    username: str
    post: Post
    media_item: MediaItem


@dataclass
class HarvestSummary:
    """Summary returned by harvest()."""

    posts_seen: int = 0
    images_downloaded: int = 0
    images_skipped: int = 0  # already on disk
    images_failed: int = 0
    videos_skipped: int = 0
    errors: list[str] = field(default_factory=list)
