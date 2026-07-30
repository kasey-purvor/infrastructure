"""CLI entry point — argparse layer → builds objects → calls harvest()."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from image_harvester.config import resolve_api_key
from image_harvester.downloader import Downloader
from image_harvester.harvest import harvest
from image_harvester.instagram import InstagramSource, _normalize_username
from image_harvester.manifest import Manifest
from image_harvester.output_store import OutputStore
from image_harvester.scrapfly_client import ScrapflyClient


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="image-harvester",
        description="Harvest all images from a public Instagram profile via ScrapFly.",
    )
    p.add_argument("username", help="Instagram username or profile URL")
    p.add_argument(
        "--limit",
        type=int,
        default=12,
        metavar="N",
        help="Max posts to fetch (default: 12). Ignored when --all is set.",
    )
    p.add_argument(
        "--all",
        dest="all_",
        action="store_true",
        help="Paginate the entire profile (overrides --limit).",
    )
    p.add_argument(
        "--output",
        type=Path,
        default=Path("output"),
        metavar="DIR",
        help="Output root directory (default: ./output).",
    )
    p.add_argument(
        "--concurrency",
        type=int,
        default=6,
        metavar="N",
        help="Parallel image download workers (default: 6).",
    )
    p.add_argument(
        "--page-delay",
        dest="page_delay",
        type=float,
        default=2.0,
        metavar="SECS",
        help="Polite delay between feed-page requests during --all, to avoid "
        "Instagram rate-limiting enumeration (default: 2.0; 0 disables).",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Enumerate posts + report counts without downloading anything.",
    )
    p.add_argument(
        "--yes",
        dest="confirm",
        action="store_true",
        help="Skip the confirmation prompt when using --all.",
    )
    p.add_argument(
        "--api-key",
        dest="api_key",
        default=None,
        metavar="KEY",
        help="ScrapFly API key (overrides SCRAPFLY_KEY env variable).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    """
    CLI entry point.

    Returns:
        0 on success, non-zero on error.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)

    # Resolve API key
    try:
        api_key = resolve_api_key(args.api_key)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # Normalize username for directory naming
    try:
        username = _normalize_username(args.username)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    # --all confirmation prompt
    confirm = args.confirm
    if args.all_ and not confirm and not args.dry_run:
        try:
            response = input(
                f"Fetch ALL posts for @{username}? This may use many ScrapFly credits. "
                "Type 'yes' to continue: "
            )
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.", file=sys.stderr)
            return 1
        if response.strip().lower() != "yes":
            print("Aborted. Pass --yes to skip this prompt.", file=sys.stderr)
            return 1
        confirm = True

    # Wire up components
    client = ScrapflyClient(api_key=api_key)
    source = InstagramSource(client, page_delay=args.page_delay)
    downloader = Downloader()
    store = OutputStore(base_dir=args.output, username=username)
    manifest_path = args.output / username / "manifest.jsonl"
    manifest = Manifest(manifest_path)

    # Run
    try:
        summary = harvest(
            source=source,
            store=store,
            manifest=manifest,
            downloader=downloader,
            username=username,
            limit=args.limit,
            all_=args.all_,
            concurrency=args.concurrency,
            dry_run=args.dry_run,
            confirm=confirm,
        )
    except Exception as exc:
        print(f"Fatal error: {exc}", file=sys.stderr)
        return 1

    # Report
    mode = "[DRY RUN] " if args.dry_run else ""
    print(
        f"{mode}Done. "
        f"Posts: {summary.posts_seen} | "
        f"Downloaded: {summary.images_downloaded} | "
        f"Skipped (on disk): {summary.images_skipped} | "
        f"Failed: {summary.images_failed} | "
        f"Videos skipped: {summary.videos_skipped}"
    )
    if summary.errors:
        print(f"Errors ({len(summary.errors)}):", file=sys.stderr)
        for err in summary.errors[:10]:
            print(f"  - {err}", file=sys.stderr)
        if len(summary.errors) > 10:
            print(f"  ... and {len(summary.errors) - 10} more", file=sys.stderr)

    return 1 if summary.images_failed > 0 and summary.images_downloaded == 0 else 0
