"""
faceMatch.py — compare face embeddings against reference embeddings using cosine distance.
"""
import time

import numpy as np

from src.utils.logger import getLogger
from src.utils.result import makeResult

log = getLogger(__name__)


def cosineDist(a: list, b: list) -> float:
    va, vb = np.array(a, dtype=np.float32), np.array(b, dtype=np.float32)
    normA, normB = np.linalg.norm(va), np.linalg.norm(vb)
    if normA == 0 or normB == 0:
        return 1.0
    return float(1.0 - np.dot(va, vb) / (normA * normB))


def matchFace(faceEmbedding: list, referenceEmbeddings: list[list], threshold: float = 0.45) -> dict:
    """
    Check if faceEmbedding matches any of referenceEmbeddings.
    output: {"matched": bool, "best_dist": float, "best_ref_idx": int}
    """
    startTime = time.time()
    try:
        if not referenceEmbeddings:
            return makeResult(False, error="No reference embeddings provided", startTime=startTime)

        bestDist = 1.0
        bestIdx = -1
        for idx, refEmb in enumerate(referenceEmbeddings):
            dist = cosineDist(faceEmbedding, refEmb)
            if dist < bestDist:
                bestDist = dist
                bestIdx = idx

        matched = bestDist <= threshold
        return makeResult(
            True,
            output={"matched": matched, "best_dist": round(bestDist, 4), "best_ref_idx": bestIdx},
            startTime=startTime,
        )
    except Exception as e:
        log.exception("matchFace failed")
        return makeResult(False, error=str(e), startTime=startTime)
