"""
faceDetect.py — detect all faces in an image and return embeddings.
Singleton model load; buffalo_l downloads on first run (~300 MB).
"""
import time
from pathlib import Path

import cv2
import numpy as np

from src.utils.logger import getLogger
from src.utils.result import makeResult

log = getLogger(__name__)

_app = None  # insightface FaceAnalysis singleton


def _getApp():
    global _app
    if _app is None:
        import insightface
        _app = insightface.app.FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
        _app.prepare(ctx_id=0, det_size=(640, 640))
        log.info("insightface buffalo_l model loaded")
    return _app


def detectFaces(imagePath: str) -> dict:
    """
    Detect all faces in imagePath.
    output: list of {"bbox": [x1,y1,x2,y2], "embedding": list[float], "det_score": float}
    """
    startTime = time.time()
    try:
        img = cv2.imread(str(imagePath))
        if img is None:
            return makeResult(False, error=f"Cannot read image: {imagePath}", startTime=startTime)

        faces = _getApp().get(img)
        faceList = [
            {
                "bbox": face.bbox.tolist(),
                "embedding": face.embedding.tolist(),
                "det_score": float(face.det_score),
            }
            for face in faces
        ]
        return makeResult(True, output={"faces": faceList, "count": len(faceList)}, startTime=startTime)
    except Exception as e:
        log.exception("detectFaces failed: %s", imagePath)
        return makeResult(False, error=str(e), startTime=startTime)
