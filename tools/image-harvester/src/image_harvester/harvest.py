"""Orchestrator — stream posts, globally-parallel downloads, skip-by-presence, dry-run.

Downloads run in ONE global thread pool with bounded back-pressure, so images
from many posts download concurrently (a single-image post no longer blocks the
next post — the inefficiency that made full-profile runs slow). Enumeration
continues on the main thread while downloads are in flight, so per-page feed
latency overlaps with downloading. A manifest line is written for each post once
all of that post's images have resolved.
"""

from __future__ import annotations

import itertools
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Protocol

from image_harvester.models import DownloadResult, HarvestSummary, Post
from image_harvester.manifest import Manifest
from image_harvester.output_store import OutputStore


class _SourceProtocol(Protocol):
    def iter_posts(self, username: str, fetch_all: bool = False):
        ...


class _DownloaderProtocol(Protocol):
    def fetch(self, url: str) -> DownloadResult:
        ...


class _PostAcc:
    """Accumulates a post's download results so we can write one manifest line."""

    __slots__ = ("post", "remaining", "results")

    def __init__(self, post: Post, remaining: int) -> None:
        self.post = post
        self.remaining = remaining
        self.results: list[DownloadResult] = []


def harvest(
    *,
    source: _SourceProtocol,
    store: OutputStore,
    manifest: Manifest,
    downloader: _DownloaderProtocol,
    username: str,
    limit: int = 12,
    all_: bool = False,
    concurrency: int = 6,
    dry_run: bool = False,
    confirm: bool = False,
) -> HarvestSummary:
    """Harvest pipeline.

    For each post (bounded by *limit* unless *all_*): skip images already on
    disk, download the rest in a shared pool, commit validated bytes, and append
    one manifest line once the post's images resolve.

    dry_run enumerates + counts and writes nothing (downloader never called).
    """
    summary = HarvestSummary()

    post_stream = source.iter_posts(username, fetch_all=all_)
    if not all_:
        post_stream = itertools.islice(post_stream, limit)

    if dry_run:
        for post in post_stream:
            summary.posts_seen += 1
            summary.videos_skipped += post.skipped_videos
            for media in post.images:
                planned = store.target_for(post, media)
                if store.exists(planned):
                    summary.images_skipped += 1
                else:
                    summary.images_downloaded += 1  # "would download"
        return summary

    futures: dict[Future, tuple[_PostAcc, object]] = {}
    max_inflight = max(concurrency * 4, 8)

    def _handle(fut: Future) -> None:
        acc, planned = futures.pop(fut)
        result = fut.result()
        if result.success and result.content is not None:
            try:
                local_path = store.commit(
                    planned, result.content, result.content_type or "image/jpeg"
                )
                result.local_path = local_path.name  # type: ignore[attr-defined]
                summary.images_downloaded += 1
            except OSError as exc:
                result = DownloadResult(
                    url=result.url, success=False, error=f"Failed to write file: {exc}"
                )
                summary.images_failed += 1
                summary.errors.append(result.error)
        else:
            summary.images_failed += 1
            if result.error:
                summary.errors.append(result.error)
        acc.results.append(result)
        acc.remaining -= 1
        if acc.remaining == 0:
            manifest.record(acc.post, acc.results)

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        for post in post_stream:
            summary.posts_seen += 1
            summary.videos_skipped += post.skipped_videos

            to_download = []
            for media in post.images:
                planned = store.target_for(post, media)
                if store.exists(planned):
                    summary.images_skipped += 1
                else:
                    to_download.append((media, planned))

            if not to_download:
                continue

            acc = _PostAcc(post, len(to_download))
            for media, planned in to_download:
                fut = executor.submit(downloader.fetch, media.url)
                futures[fut] = (acc, planned)

            # Back-pressure: keep outstanding downloads bounded so memory stays
            # flat on huge profiles, while still overlapping with enumeration.
            while len(futures) >= max_inflight:
                _handle(next(as_completed(list(futures))))

        # Drain whatever remains.
        for fut in as_completed(list(futures)):
            _handle(fut)

    return summary
