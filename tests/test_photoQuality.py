"""
test_photoQuality.py — unit tests for blur detection.
"""
import pytest
from src.scripts.photoQuality import assessQuality, isFaceLargeEnough


def test_assessQuality_sharp(sharpImagePath):
    r = assessQuality(sharpImagePath)
    assert r["success"] is True
    assert r["output"]["is_blurry"] is False
    assert r["output"]["blur_score"] > 100


def test_assessQuality_blurry(blurryImagePath):
    r = assessQuality(blurryImagePath, blurThreshold=200.0)
    assert r["success"] is True
    assert r["output"]["is_blurry"] is True


def test_assessQuality_missing_file():
    r = assessQuality("/nonexistent/path.jpg")
    assert r["success"] is False


def test_isFaceLargeEnough_passes():
    assert isFaceLargeEnough([0, 0, 100, 100], minSizePx=40) is True


def test_isFaceLargeEnough_fails_small():
    assert isFaceLargeEnough([0, 0, 30, 30], minSizePx=40) is False
