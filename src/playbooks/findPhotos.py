"""
findPhotos.py — Playbook A1: identify photos containing the user.

Inputs:  referencePhotoPaths, targetPhotoPaths, outputDir, threshold
Outputs: matched_paths, unmatched_paths, total, matched_count
Success: at least one match found OR target list is empty
"""
import shutil
import time
from pathlib import Path

from src.config import FACE_SIMILARITY_THRESHOLD
from src.scripts.faceDetect import detectFaces
from src.scripts.faceMatch import matchFace
from src.utils.logger import getLogger
from src.utils.result import makeResult

log = getLogger(__name__)


def _extractReferenceEmbeddings(refPaths: list[str]) -> tuple[list, list]:
    embeddings, errors = [], []
    for p in refPaths:
        r = detectFaces(p)
        if not r["success"]:
            errors.append(f"Detect failed ({Path(p).name}): {r.get('error', 'unknown')}")
            log.error("_extractReferenceEmbeddings: detect failed for %s: %s", p, r.get('error'))
            continue
        if r["output"]["count"] == 0:
            errors.append(f"No face in reference ({Path(p).name})")
            log.warning("_extractReferenceEmbeddings: no face detected in %s", p)
            continue
        # Pick highest-confidence face from each reference photo
        bestFace = max(r["output"]["faces"], key=lambda f: f["det_score"])
        embeddings.append(bestFace["embedding"])
    return embeddings, errors


def _matchPhotoFaces(photoPath: str, refEmbeddings: list, threshold: float,
                     applyExif: bool) -> tuple[bool, float | None, int]:
    """
    Detect faces in one photo (raw pixels or EXIF-rotated) and check whether
    any face matches the references. Returns (matched, bestDist, faceCount).
    """
    r = detectFaces(photoPath, applyExif=applyExif)
    if not r["success"] or r["output"]["count"] == 0:
        return False, None, 0

    bestDist: float | None = None
    for face in r["output"]["faces"]:
        mr = matchFace(face["embedding"], refEmbeddings, threshold)
        if mr["success"] and mr["output"]["matched"]:
            return True, mr["output"]["best_dist"], r["output"]["count"]
        dist = mr["output"].get("best_dist") if mr["success"] else None
        if dist is not None and (bestDist is None or dist < bestDist):
            bestDist = dist
    return False, bestDist, r["output"]["count"]


def runFindPhotos(referencePhotoPaths: list[str], targetPhotoPaths: list[str],
                   outputDir: str, threshold: float = FACE_SIMILARITY_THRESHOLD) -> dict:
    startTime = time.time()
    Path(outputDir).mkdir(parents=True, exist_ok=True)

    refEmbeddings, refErrors = _extractReferenceEmbeddings(referencePhotoPaths)
    if not refEmbeddings:
        return makeResult(False, error=f"Could not extract any reference face. Details: {refErrors}", startTime=startTime)

    log.info("A1: %d reference embeddings extracted, scanning %d photos", len(refEmbeddings), len(targetPhotoPaths))

    matchedPaths, unmatchedPaths = [], []
    for photoPath in targetPhotoPaths:
        # Dual-path match: try RAW pixels first (stable, matches pre-EXIF behavior);
        # if no match, retry with EXIF Orientation applied (fixes sideways phone
        # photos that yield 0 faces in raw form). Take the better result.
        photoMatched, bestDist, faceCount = _matchPhotoFaces(
            photoPath, refEmbeddings, threshold, applyExif=False)
        matchedVia = "raw"
        if not photoMatched:
            exifMatched, exifDist, exifFaceCount = _matchPhotoFaces(
                photoPath, refEmbeddings, threshold, applyExif=True)
            if exifMatched:
                photoMatched, bestDist = True, exifDist
                matchedVia = "exif"
                faceCount = exifFaceCount
            elif exifDist is not None and (bestDist is None or exifDist < bestDist):
                bestDist = exifDist
                faceCount = exifFaceCount

        if photoMatched:
            log.info("A1: %s matched via %s pixels (best_dist=%.3f, faces=%d)",
                     Path(photoPath).name, matchedVia, bestDist if bestDist is not None else -1.0, faceCount)
            dest = Path(outputDir) / Path(photoPath).name
            shutil.copy2(photoPath, dest)
            matchedPaths.append(str(dest))
        else:
            unmatchedPaths.append(photoPath)

    log.info("A1 done: %d/%d photos matched", len(matchedPaths), len(targetPhotoPaths))
    return makeResult(
        True,
        output={
            "matched_paths": matchedPaths,
            "unmatched_paths": unmatchedPaths,
            "total": len(targetPhotoPaths),
            "matched_count": len(matchedPaths),
        },
        startTime=startTime,
    )
