"""Tests for output_store.py — filename convention, extension, exists(), commit()."""

from __future__ import annotations

import datetime
from pathlib import Path
import pytest

from image_harvester.models import Post, MediaItem, PlannedPath
from image_harvester.output_store import OutputStore

TAKEN_AT = datetime.datetime(2023, 9, 16, 10, 0, 0, tzinfo=datetime.timezone.utc)


def make_post(shortcode="CxQwZ0gOIFp") -> Post:
    return Post(
        shortcode=shortcode,
        taken_at=TAKEN_AT,
        owner="madtev",
        caption="test",
        like_count=100,
        comment_count=10,
        images=[],
    )


def make_media(index=1, url="https://example.com/img.jpg") -> MediaItem:
    return MediaItem(index=index, url=url, width=1080, height=1350)


class TestNamingConvention:
    def test_stem_format(self, tmp_path):
        store = OutputStore(base_dir=tmp_path, username="madtev")
        post = make_post("CxQwZ0gOIFp")
        media = make_media(index=1)
        planned = store.target_for(post, media)
        assert planned.stem == "2023-09-16_CxQwZ0gOIFp_01"

    def test_index_zero_padded_two_digits(self, tmp_path):
        store = OutputStore(base_dir=tmp_path, username="madtev")
        post = make_post("CxQwZ0gOIFp")
        media = make_media(index=7)
        planned = store.target_for(post, media)
        assert planned.stem == "2023-09-16_CxQwZ0gOIFp_07"

    def test_index_double_digit(self, tmp_path):
        store = OutputStore(base_dir=tmp_path, username="madtev")
        post = make_post("CxQwZ0gOIFp")
        media = make_media(index=10)
        planned = store.target_for(post, media)
        assert planned.stem == "2023-09-16_CxQwZ0gOIFp_10"


class TestExtensionDerivation:
    def test_jpeg_ext(self, tmp_path):
        store = OutputStore(base_dir=tmp_path, username="madtev")
        planned = store.target_for(make_post(), make_media())
        path = store.commit(planned, b"\xff\xd8\xff" + b"\x00" * 50, "image/jpeg")
        assert path.suffix == ".jpg"

    def test_png_ext(self, tmp_path):
        store = OutputStore(base_dir=tmp_path, username="madtev")
        planned = store.target_for(make_post(), make_media())
        path = store.commit(planned, b"\x89PNG\r\n\x1a\n" + b"\x00" * 50, "image/png")
        assert path.suffix == ".png"

    def test_webp_ext(self, tmp_path):
        store = OutputStore(base_dir=tmp_path, username="madtev")
        planned = store.target_for(make_post(), make_media())
        path = store.commit(planned, b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 50, "image/webp")
        assert path.suffix == ".webp"

    def test_content_type_with_params(self, tmp_path):
        """Content-Type like 'image/jpeg; charset=...' — should still give jpg."""
        store = OutputStore(base_dir=tmp_path, username="madtev")
        planned = store.target_for(make_post(), make_media())
        path = store.commit(planned, b"\xff\xd8\xff" + b"\x00" * 50, "image/jpeg; charset=utf-8")
        assert path.suffix == ".jpg"


class TestExistsAndCommit:
    def test_exists_false_before_commit(self, tmp_path):
        store = OutputStore(base_dir=tmp_path, username="madtev")
        planned = store.target_for(make_post(), make_media())
        assert store.exists(planned) is False

    def test_exists_true_after_commit(self, tmp_path):
        store = OutputStore(base_dir=tmp_path, username="madtev")
        planned = store.target_for(make_post(), make_media())
        store.commit(planned, b"\xff\xd8\xff" + b"\x00" * 50, "image/jpeg")
        assert store.exists(planned) is True

    def test_exists_matches_any_extension(self, tmp_path):
        """exists() globs by stem — extension on disk may differ from the check."""
        store = OutputStore(base_dir=tmp_path, username="madtev")
        post = make_post("SHORT001")
        media = make_media(index=1)
        planned = store.target_for(post, media)
        # Commit as PNG
        store.commit(planned, b"\x89PNG\r\n\x1a\n" + b"\x00" * 50, "image/png")
        # exists() must still return True regardless of ext
        assert store.exists(planned) is True

    def test_commit_writes_correct_bytes(self, tmp_path):
        store = OutputStore(base_dir=tmp_path, username="madtev")
        planned = store.target_for(make_post(), make_media())
        content = b"\xff\xd8\xff\xe0" + b"X" * 200
        path = store.commit(planned, content, "image/jpeg")
        assert path.read_bytes() == content

    def test_commit_creates_directory(self, tmp_path):
        store = OutputStore(base_dir=tmp_path, username="newuser")
        planned = store.target_for(make_post(), make_media())
        path = store.commit(planned, b"\xff\xd8\xff" + b"\x00" * 50, "image/jpeg")
        assert path.exists()
        assert path.parent.name == "newuser"

    def test_commit_is_atomic_no_partial_file_on_failure(self, tmp_path):
        """
        If commit() fails mid-write (simulated by patching), the final path should
        not exist (no partial file left behind).
        This verifies the temp-file + rename pattern.
        """
        import unittest.mock as mock

        store = OutputStore(base_dir=tmp_path, username="madtev")
        planned = store.target_for(make_post(), make_media())
        # Determine the final target path
        content = b"\xff\xd8\xff" + b"\x00" * 50

        # Patch os.replace to fail
        with mock.patch("os.replace", side_effect=OSError("simulated")):
            with pytest.raises(OSError):
                store.commit(planned, content, "image/jpeg")

        # The final path must not exist
        final_dir = tmp_path / "madtev"
        # If the dir was not even created that's fine too
        if final_dir.exists():
            matching = list(final_dir.glob("2023-09-16_CxQwZ0gOIFp_01.*"))
            assert len(matching) == 0
