"""Output store — filename convention, extension derivation, skip-by-presence, atomic write."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from image_harvester.models import MediaItem, PlannedPath, Post


_CONTENT_TYPE_TO_EXT: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/avif": "avif",
    "image/heic": "heic",
}


def _ext_from_content_type(content_type: str) -> str:
    """Derive a file extension from a Content-Type header value."""
    base = content_type.split(";")[0].strip().lower()
    return _CONTENT_TYPE_TO_EXT.get(base, "jpg")


class OutputStore:
    """
    Owns the file layout for downloaded images.

    Layout: ``{base_dir}/{username}/{stem}.{ext}``

    Filename convention: ``{taken_at:%Y-%m-%d}_{shortcode}_{index:02d}.{ext}``

    All writes are atomic (temp file in the same directory + os.replace).
    ``exists()`` matches by stem regardless of extension (glob).
    """

    def __init__(self, base_dir: Path, username: str) -> None:
        self._base_dir = Path(base_dir)
        self._username = username

    @property
    def _user_dir(self) -> Path:
        return self._base_dir / self._username

    def target_for(self, post: Post, media: MediaItem) -> PlannedPath:
        """
        Return the PlannedPath for a given (post, media item) pair.

        The extension is NOT known yet (we don't have the content-type until
        download time), so PlannedPath carries only the stem.
        """
        stem = (
            f"{post.taken_at:%Y-%m-%d}"
            f"_{post.shortcode}"
            f"_{media.index:02d}"
        )
        return PlannedPath(
            stem=stem,
            username=self._username,
            post=post,
            media_item=media,
        )

    def exists(self, planned: PlannedPath) -> bool:
        """
        Return True if *any* file with this stem already exists in the user dir.

        Extension-agnostic: if a JPEG was previously saved as .jpg, a later call
        that would produce .webp will still report the file as present.
        """
        user_dir = self._user_dir
        if not user_dir.exists():
            return False
        return any(user_dir.glob(f"{planned.stem}.*"))

    def commit(
        self,
        planned: PlannedPath,
        content: bytes,
        content_type: str,
    ) -> Path:
        """
        Write *content* to disk atomically.

        Creates the user directory if it doesn't exist.
        Uses a temp file in the same directory + ``os.replace`` (rename),
        which is atomic on POSIX systems.

        Returns the final Path.
        """
        ext = _ext_from_content_type(content_type)
        user_dir = self._user_dir
        user_dir.mkdir(parents=True, exist_ok=True)

        final_path = user_dir / f"{planned.stem}.{ext}"

        # Write to a temp file in the same directory, then rename
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=user_dir,
            prefix=f".tmp_{planned.stem}_",
            suffix=f".{ext}",
        )
        try:
            with os.fdopen(tmp_fd, "wb") as f:
                f.write(content)
            os.replace(tmp_path, final_path)
        except Exception:
            # Clean up temp file on failure
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        return final_path
