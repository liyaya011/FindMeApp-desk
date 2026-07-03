"""
test_exifExtract.py — unit tests for EXIF extraction.
"""
import pytest
from src.scripts.exifExtract import extractExif


def test_exif_no_gps(tmp_path):
    from PIL import Image
    p = tmp_path / "plain.jpg"
    img = Image.new("RGB", (100, 100), color=(200, 100, 50))
    img.save(str(p))

    r = extractExif(str(p))
    assert r["success"] is True
    assert r["output"]["has_gps"] is False
    assert r["output"]["lat"] is None
    assert r["output"]["lng"] is None


def test_exif_missing_file():
    r = extractExif("/nonexistent/photo.jpg")
    assert r["success"] is False
