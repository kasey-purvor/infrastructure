"""Tests for harvest.py — orchestration, skip-by-presence, dry-run, limit."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Iterator

import pytest

from image_harvester.models import Post, MediaItem, DownloadResult, HarvestSummary
from image_harvester.harvest import harvest
from image_harvester.output_store import OutputStore
from image_harvester.manifest import Manifest

TAKEN_AT = datetime.datetime(2023, 9, 16, 10, 0, 0, tzinfo=datetime.timezone.utc)

# A real JPEG magic header for valid content
JPEG_CONTENT = b"\xff\xd8\xff\xe0" + b"\x00" * 200


def make_post(shortcode: str, n_images: int = 2) -> Post:
    images = [
        MediaItem(
            index=i + 1,
            url=f"https://example.com/{shortcode}_{i+1}.jpg",
            width=1080,
            height=1350,
        )
        for i in range(n_images)
    ]
    return Post(
        shortcode=shortcode,
        taken_at=TAKEN_AT,
        owner="testuser",
        caption="caption",
        like_count=100,
        comment_count=10,
        images=images,
    )


class FakeSource:
    """Fake InstagramSource — yields Posts from a fixed list."""

    def __init__(self, posts: list[Post]):
        self._posts = posts

    def iter_posts(self, username: str, fetch_all: bool = False) -> Iterator[Post]:
        yield from self._posts


class FakeDownloader:
    """Fake Downloader — returns canned bytes, records what was fetched."""

    def __init__(self, content: bytes = JPEG_CONTENT, success: bool = True):
        self._content = content
        self._success = success
        self.fetched_urls: list[str] = []

    def fetch(self, url: str) -> DownloadResult:
        self.fetched_urls.append(url)
        if self._success:
            return DownloadResult(
                url=url,
                success=True,
                content=self._content,
                content_type="image/jpeg",
            )
        return DownloadResult(url=url, success=False, error="fake failure")


class TestFilesWritten:
    def test_files_written_with_correct_names(self, tmp_path):
        posts = [make_post("POST001", n_images=2)]
        source = FakeSource(posts)
        downloader = FakeDownloader()
        store = OutputStore(base_dir=tmp_path, username="testuser")
        manifest = Manifest(tmp_path / "testuser" / "manifest.jsonl")

        summary = harvest(
            source=source,
            store=store,
            manifest=manifest,
            downloader=downloader,
            username="testuser",
            limit=12,
            all_=False,
            concurrency=1,
            dry_run=False,
            confirm=True,
        )

        output_dir = tmp_path / "testuser"
        files = list(output_dir.glob("*.jpg"))
        # 2 images from 1 post
        assert len(files) == 2
        stems = sorted(f.stem for f in files)
        assert stems == ["2023-09-16_POST001_01", "2023-09-16_POST001_02"]

    def test_manifest_line_per_post(self, tmp_path):
        posts = [make_post("POST001"), make_post("POST002")]
        source = FakeSource(posts)
        downloader = FakeDownloader()
        store = OutputStore(base_dir=tmp_path, username="testuser")
        manifest_path = tmp_path / "testuser" / "manifest.jsonl"
        manifest = Manifest(manifest_path)

        harvest(
            source=source,
            store=store,
            manifest=manifest,
            downloader=downloader,
            username="testuser",
            limit=12,
            all_=False,
            concurrency=1,
            dry_run=False,
            confirm=True,
        )

        # Manifest dir is created by the store on first commit
        lines = manifest_path.read_text().strip().splitlines()
        assert len(lines) == 2
        shortcodes = [json.loads(l)["shortcode"] for l in lines]
        assert "POST001" in shortcodes
        assert "POST002" in shortcodes


class TestSkipByPresence:
    def test_second_run_skips_existing_files(self, tmp_path):
        posts = [make_post("POST001", n_images=2)]
        source = FakeSource(posts)
        store = OutputStore(base_dir=tmp_path, username="testuser")
        manifest_path = tmp_path / "testuser" / "manifest.jsonl"

        # First run
        downloader1 = FakeDownloader()
        harvest(
            source=source,
            store=store,
            manifest=Manifest(manifest_path),
            downloader=downloader1,
            username="testuser",
            limit=12,
            all_=False,
            concurrency=1,
            dry_run=False,
            confirm=True,
        )
        first_run_fetches = len(downloader1.fetched_urls)
        assert first_run_fetches == 2  # 2 images fetched

        # Second run — same source, same store
        source2 = FakeSource(posts)
        downloader2 = FakeDownloader()
        summary2 = harvest(
            source=source2,
            store=store,
            manifest=Manifest(manifest_path),
            downloader=downloader2,
            username="testuser",
            limit=12,
            all_=False,
            concurrency=1,
            dry_run=False,
            confirm=True,
        )

        # Downloader should NOT have been called for existing files
        assert len(downloader2.fetched_urls) == 0
        assert summary2.images_skipped == 2

    def test_summary_reflects_skip_count(self, tmp_path):
        posts = [make_post("POST001", n_images=3)]
        source = FakeSource(posts)
        store = OutputStore(base_dir=tmp_path, username="testuser")
        manifest_path = tmp_path / "testuser" / "manifest.jsonl"

        # First run
        harvest(
            source=source,
            store=store,
            manifest=Manifest(manifest_path),
            downloader=FakeDownloader(),
            username="testuser",
            limit=12,
            all_=False,
            concurrency=1,
            dry_run=False,
            confirm=True,
        )

        # Second run
        source2 = FakeSource(posts)
        downloader2 = FakeDownloader()
        summary = harvest(
            source=source2,
            store=store,
            manifest=Manifest(manifest_path),
            downloader=downloader2,
            username="testuser",
            limit=12,
            all_=False,
            concurrency=1,
            dry_run=False,
            confirm=True,
        )
        assert summary.images_skipped == 3
        assert summary.images_downloaded == 0


class TestDryRun:
    def test_dry_run_writes_nothing(self, tmp_path):
        posts = [make_post("POST001", n_images=2), make_post("POST002", n_images=1)]
        source = FakeSource(posts)
        downloader = FakeDownloader()
        store = OutputStore(base_dir=tmp_path, username="testuser")
        manifest_path = tmp_path / "testuser" / "manifest.jsonl"

        harvest(
            source=source,
            store=store,
            manifest=Manifest(manifest_path),
            downloader=downloader,
            username="testuser",
            limit=12,
            all_=False,
            concurrency=1,
            dry_run=True,
            confirm=True,
        )

        # No files on disk
        output_dir = tmp_path / "testuser"
        if output_dir.exists():
            files = list(output_dir.glob("*.jpg")) + list(output_dir.glob("*.png"))
            assert len(files) == 0
            # No manifest either
            assert not manifest_path.exists()

    def test_dry_run_downloader_not_called(self, tmp_path):
        posts = [make_post("POST001", n_images=2)]
        source = FakeSource(posts)
        downloader = FakeDownloader()
        store = OutputStore(base_dir=tmp_path, username="testuser")
        manifest_path = tmp_path / "testuser" / "manifest.jsonl"

        harvest(
            source=source,
            store=store,
            manifest=Manifest(manifest_path),
            downloader=downloader,
            username="testuser",
            limit=12,
            all_=False,
            concurrency=1,
            dry_run=True,
            confirm=True,
        )

        assert len(downloader.fetched_urls) == 0


class TestLimit:
    def test_limit_honoured(self, tmp_path):
        posts = [make_post(f"POST{i:03d}", n_images=1) for i in range(10)]
        source = FakeSource(posts)
        downloader = FakeDownloader()
        store = OutputStore(base_dir=tmp_path, username="testuser")
        manifest_path = tmp_path / "testuser" / "manifest.jsonl"

        summary = harvest(
            source=source,
            store=store,
            manifest=Manifest(manifest_path),
            downloader=downloader,
            username="testuser",
            limit=3,
            all_=False,
            concurrency=1,
            dry_run=False,
            confirm=True,
        )

        assert summary.posts_seen == 3
        assert summary.images_downloaded == 3

    def test_limit_ignored_when_all_is_true(self, tmp_path):
        posts = [make_post(f"POST{i:03d}", n_images=1) for i in range(5)]
        source = FakeSource(posts)
        downloader = FakeDownloader()
        store = OutputStore(base_dir=tmp_path, username="testuser")
        manifest_path = tmp_path / "testuser" / "manifest.jsonl"

        summary = harvest(
            source=source,
            store=store,
            manifest=Manifest(manifest_path),
            downloader=downloader,
            username="testuser",
            limit=2,
            all_=True,
            concurrency=1,
            dry_run=False,
            confirm=True,
        )

        assert summary.posts_seen == 5


class TestSummary:
    def test_summary_counts_downloaded(self, tmp_path):
        posts = [make_post("POST001", n_images=3)]
        source = FakeSource(posts)
        downloader = FakeDownloader()
        store = OutputStore(base_dir=tmp_path, username="testuser")
        manifest_path = tmp_path / "testuser" / "manifest.jsonl"

        summary = harvest(
            source=source,
            store=store,
            manifest=Manifest(manifest_path),
            downloader=downloader,
            username="testuser",
            limit=12,
            all_=False,
            concurrency=1,
            dry_run=False,
            confirm=True,
        )

        assert summary.posts_seen == 1
        assert summary.images_downloaded == 3
        assert summary.images_failed == 0
