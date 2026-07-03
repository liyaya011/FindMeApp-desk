"""
photoDedupe.py — remove near-duplicate images using perceptual hashing.
"""
import time
from pathlib import Path

import imagehash
from PIL import Image

from src.utils.logger import getLogger
from src.utils.result import makeResult

log = getLogger(__name__)


def dedupePhotos(photoPaths: list[str], hashThreshold: int = 8) -> dict:
    """
    Return unique photos filtered by perceptual hash (dHash).
    output: {"unique_paths": list[str], "removed_count": int}
    hashThreshold: max hamming distance to still be considered duplicate.
    """
    startTime = time.time()
    try:
        seen: dict[imagehash.ImageHash, str] = {}
        uniquePaths = []
        removedCount = 0

        for path in photoPaths:
            try:
                img = Image.open(path)
                h = imagehash.dhash(img)
            except Exception as e:
                log.warning("Cannot hash %s: %s", path, e)
                uniquePaths.append(path)  # keep on error
                continue

            isDuplicate = any(abs(h - existingHash) <= hashThreshold for existingHash in seen)
            if isDuplicate:
                removedCount += 1
            else:
                seen[h] = path
                uniquePaths.append(path)

        return makeResult(
            True,
            output={"unique_paths": uniquePaths, "removed_count": removedCount},
            startTime=startTime,
        )
    except Exception as e:
        log.exception("dedupePhotos failed")
        return makeResult(False, error=str(e), startTime=startTime)
