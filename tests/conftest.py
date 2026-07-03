"""
conftest.py — shared test fixtures.
"""
import os
import numpy as np
import pytest
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURES_DIR.mkdir(exist_ok=True)


@pytest.fixture
def sampleImagePath(tmp_path):
    """Create a simple 200x200 solid-color PNG for tests that don't need a real face."""
    import cv2
    p = tmp_path / "sample.png"
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    img[:] = (120, 80, 200)
    cv2.imwrite(str(p), img)
    return str(p)


@pytest.fixture
def blurryImagePath(tmp_path):
    """Create a blurry image."""
    import cv2
    p = tmp_path / "blurry.png"
    img = np.random.randint(0, 256, (200, 200, 3), dtype=np.uint8)
    blurred = cv2.GaussianBlur(img, (51, 51), 0)
    cv2.imwrite(str(p), blurred)
    return str(p)


@pytest.fixture
def sharpImagePath(tmp_path):
    """Create a sharp image (checkerboard pattern = high Laplacian variance)."""
    import cv2
    p = tmp_path / "sharp.png"
    img = np.zeros((200, 200, 3), dtype=np.uint8)
    img[::10, :] = 255
    img[:, ::10] = 255
    cv2.imwrite(str(p), img)
    return str(p)


@pytest.fixture
def sampleEmbedding():
    return np.random.rand(512).tolist()
