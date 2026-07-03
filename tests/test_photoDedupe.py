"""
test_photoDedupe.py — unit tests for perceptual hash deduplication.
"""
import shutil
import pytest
from pathlib import Path
from src.scripts.photoDedupe import dedupePhotos


def test_dedupe_identical_files(tmp_path, sharpImagePath):
    copy1 = str(tmp_path / "a.png")
    copy2 = str(tmp_path / "b.png")
    shutil.copy(sharpImagePath, copy1)
    shutil.copy(sharpImagePath, copy2)

    r = dedupePhotos([copy1, copy2])
    assert r["success"] is True
    assert len(r["output"]["unique_paths"]) == 1
    assert r["output"]["removed_count"] == 1


def test_dedupe_different_files(tmp_path, sharpImagePath, blurryImagePath):
    r = dedupePhotos([sharpImagePath, blurryImagePath])
    assert r["success"] is True
    assert len(r["output"]["unique_paths"]) == 2
    assert r["output"]["removed_count"] == 0


def test_dedupe_empty_list():
    r = dedupePhotos([])
    assert r["success"] is True
    assert r["output"]["unique_paths"] == []


def test_dedupe_missing_file_kept(tmp_path, sharpImagePath):
    r = dedupePhotos([sharpImagePath, "/nonexistent/x.jpg"])
    assert r["success"] is True
    assert len(r["output"]["unique_paths"]) == 2  # bad file kept on error
