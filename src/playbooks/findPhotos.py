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
        if not r["success"] or r["output"]["count"] == 0:
            errors.append(f"No face in reference: {p}")
            continue
        # Pick highest-confidence face from each reference photo
        bestFace = max(r["output"]["faces"], key=lambda f: f["det_score"])
        embeddings.append(bestFace["embedding"])
    return embeddings, errors


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
        r = detectFaces(photoPath)
        if not r["success"] or r["output"]["count"] == 0:
            unmatchedPaths.append(photoPath)
            continue

        photoMatched = False
        for face in r["output"]["faces"]:
            mr = matchFace(face["embedding"], refEmbeddings, threshold)
            if mr["success"] and mr["output"]["matched"]:
                photoMatched = True
                break

        if photoMatched:
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
