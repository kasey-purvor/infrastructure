"""Manifest — append one JSON object per post to a JSONL file."""

from __future__ import annotations

import datetime
import hashlib
import json
from pathlib import Path

from image_harvester.models import DownloadResult, Post


class Manifest:
    """
    JSONL (JSON Lines) manifest — one object per post.

    Schema per line:
    {
      "shortcode": "...",
      "post_url": "https://www.instagram.com/p/.../",
      "taken_at": "ISO8601",
      "caption": "...",
      "like_count": N,
      "comment_count": N,
      "owner": "...",
      "images": [
        {
          "index": 1,
          "url": "https://...",
          "local_path": "2023-09-16_CxQwZ0gOIFp_01.jpg",
          "width": 1440,
          "height": 1711,
          "bytes": 184600,
          "sha256": "..."
        }
      ],
      "skipped_videos": 0,
      "fetched_at": "ISO8601",
      "source": "ig:web_profile_info"
    }
    """

    def __init__(self, path: Path) -> None:
        self._path = Path(path)

    def record(self, post: Post, image_results: list[DownloadResult]) -> None:
        """
        Append one JSON line for *post* to the manifest.

        Only successful DownloadResults (success=True) are included in the
        ``images`` array. Failed downloads are silently omitted from the list
        (the caller tracks failure counts separately).
        """
        images_data = []
        for result in image_results:
            if not result.success or result.content is None:
                continue
            local_path = getattr(result, "local_path", None)
            # Find the matching MediaItem by URL
            media = next(
                (m for m in post.images if m.url == result.url), None
            )
            images_data.append({
                "index": media.index if media else None,
                "url": result.url,
                "local_path": local_path,
                "width": media.width if media else None,
                "height": media.height if media else None,
                "bytes": len(result.content),
                "sha256": hashlib.sha256(result.content).hexdigest(),
            })

        record = {
            "shortcode": post.shortcode,
            "post_url": post.post_url,
            "taken_at": post.taken_at.isoformat(),
            "caption": post.caption,
            "like_count": post.like_count,
            "comment_count": post.comment_count,
            "owner": post.owner,
            "images": images_data,
            "skipped_videos": post.skipped_videos,
            "fetched_at": datetime.datetime.now(tz=datetime.timezone.utc).isoformat(),
            "source": "ig:feed",
        }

        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
