"""Tests for manifest.py — JSONL schema and append behaviour."""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path
import pytest

from image_harvester.models import Post, MediaItem, DownloadResult
from image_harvester.manifest import Manifest

TAKEN_AT = datetime.datetime(2023, 9, 16, 10, 0, 0, tzinfo=datetime.timezone.utc)


def make_post(shortcode="CxQwZ0gOIFp") -> Post:
    img1 = MediaItem(index=1, url="https://example.com/img1.jpg", width=1080, height=1350)
    img2 = MediaItem(index=2, url="https://example.com/img2.jpg", width=1080, height=1350)
    return Post(
        shortcode=shortcode,
        taken_at=TAKEN_AT,
        owner="madtev",
        caption="test caption",
        like_count=16200,
        comment_count=279,
        images=[img1, img2],
        skipped_videos=1,
    )


def make_result(media: MediaItem, content: bytes, local_path: str) -> DownloadResult:
    r = DownloadResult(
        url=media.url,
        success=True,
        content=content,
        content_type="image/jpeg",
    )
    r.local_path = local_path
    return r


class TestManifestRecord:
    def test_record_appends_jsonl(self, tmp_path):
        manifest_path = tmp_path / "manifest.jsonl"
        m = Manifest(manifest_path)
        post = make_post()
        content = b"\xff\xd8\xff" + b"X" * 100
        results = [
            make_result(post.images[0], content, "2023-09-16_CxQwZ0gOIFp_01.jpg"),
            make_result(post.images[1], content, "2023-09-16_CxQwZ0gOIFp_02.jpg"),
        ]
        m.record(post, results)

        lines = manifest_path.read_text().strip().splitlines()
        assert len(lines) == 1
        obj = json.loads(lines[0])
        assert obj["shortcode"] == "CxQwZ0gOIFp"

    def test_schema_top_level_fields(self, tmp_path):
        manifest_path = tmp_path / "manifest.jsonl"
        m = Manifest(manifest_path)
        post = make_post()
        content = b"\xff\xd8\xff" + b"X" * 100
        results = [make_result(post.images[0], content, "2023-09-16_CxQwZ0gOIFp_01.jpg")]
        m.record(post, results)

        obj = json.loads(manifest_path.read_text().strip())
        assert obj["shortcode"] == "CxQwZ0gOIFp"
        assert obj["post_url"] == "https://www.instagram.com/p/CxQwZ0gOIFp/"
        assert obj["owner"] == "madtev"
        assert obj["caption"] == "test caption"
        assert obj["like_count"] == 16200
        assert obj["comment_count"] == 279
        assert obj["skipped_videos"] == 1
        assert "taken_at" in obj
        assert "fetched_at" in obj
        assert obj["source"] == "ig:feed"

    def test_schema_images_array(self, tmp_path):
        manifest_path = tmp_path / "manifest.jsonl"
        m = Manifest(manifest_path)
        post = make_post()
        content = b"\xff\xd8\xff" + b"X" * 100
        sha = hashlib.sha256(content).hexdigest()
        results = [
            make_result(post.images[0], content, "2023-09-16_CxQwZ0gOIFp_01.jpg"),
            make_result(post.images[1], content, "2023-09-16_CxQwZ0gOIFp_02.jpg"),
        ]
        m.record(post, results)

        obj = json.loads(manifest_path.read_text().strip())
        assert len(obj["images"]) == 2
        img = obj["images"][0]
        assert img["index"] == 1
        assert img["url"] == "https://example.com/img1.jpg"
        assert img["local_path"] == "2023-09-16_CxQwZ0gOIFp_01.jpg"
        assert img["bytes"] == len(content)
        assert img["sha256"] == sha
        assert img["width"] == 1080
        assert img["height"] == 1350

    def test_multiple_posts_multiple_lines(self, tmp_path):
        manifest_path = tmp_path / "manifest.jsonl"
        m = Manifest(manifest_path)
        content = b"\xff\xd8\xff" + b"X" * 100
        for sc in ["POST001", "POST002", "POST003"]:
            post = make_post(sc)
            results = [make_result(post.images[0], content, f"2023-09-16_{sc}_01.jpg")]
            m.record(post, results)

        lines = manifest_path.read_text().strip().splitlines()
        assert len(lines) == 3
        shortcodes = [json.loads(l)["shortcode"] for l in lines]
        assert shortcodes == ["POST001", "POST002", "POST003"]

    def test_failed_downloads_excluded_from_images(self, tmp_path):
        """Failed DownloadResults should not appear in the manifest images array."""
        manifest_path = tmp_path / "manifest.jsonl"
        m = Manifest(manifest_path)
        post = make_post()
        content = b"\xff\xd8\xff" + b"X" * 100

        good = make_result(post.images[0], content, "2023-09-16_CxQwZ0gOIFp_01.jpg")
        bad = DownloadResult(
            url=post.images[1].url,
            success=False,
            content=None,
            content_type=None,
            error="timeout",
        )
        bad.local_path = None
        m.record(post, [good, bad])

        obj = json.loads(manifest_path.read_text().strip())
        assert len(obj["images"]) == 1
        assert obj["images"][0]["index"] == 1
