"""
photoQuality.py — assess photo sharpness and face size.
"""
import time

import cv2
import numpy as np

from src.utils.logger import getLogger
from src.utils.result import makeResult

log = getLogger(__name__)


def assessQuality(imagePath: str, blurThreshold: float = 100.0, minFaceSizePx: int = 40) -> dict:
    """
    Return blur score, whether blurry, and whether any detected face meets minimum size.
    output: {"blur_score": float, "is_blurry": bool, "face_ok": bool}
    face_ok is True when at least one face in the image has both dimensions >= minFaceSizePx.
    Pass faces=None to skip face-size check.
    """
    startTime = time.time()
    try:
        img = cv2.imread(str(imagePath))
        if img is None:
            return makeResult(False, error=f"Cannot read image: {imagePath}", startTime=startTime)

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        blurScore = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        isBlurry = blurScore < blurThreshold

        return makeResult(
            True,
            output={"blur_score": round(blurScore, 2), "is_blurry": isBlurry},
            startTime=startTime,
        )
    except Exception as e:
        log.exception("assessQuality failed: %s", imagePath)
        return makeResult(False, error=str(e), startTime=startTime)


def isFaceLargeEnough(bbox: list, minSizePx: int = 40) -> bool:
    """Check if face bounding box meets minimum display size."""
    x1, y1, x2, y2 = bbox
    return (x2 - x1) >= minSizePx and (y2 - y1) >= minSizePx
