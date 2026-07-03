"""
buildHighlight.py — Playbook B: build a curated photo collection and a short highlight video.

Inputs:  myPhotoPaths, myClipPaths, outputDir, audioPath (optional)
Outputs: selected_photos (sorted by taken_at), highlight_video_path
Success: highlight video created

Template 1 (photos-only): sorted photo slideshow
Template 2 (photos + clips): clips video prepended/appended to slideshow
"""
import shutil
import time
from pathlib import Path

from src.config import (
    BLUR_THRESHOLD,
    MAX_HIGHLIGHT_PHOTOS,
    PHOTO_SLIDE_DURATION_S,
)
from src.scripts.exifExtract import extractExif
from src.scripts.photoDedupe import dedupePhotos
from src.scripts.photoQuality import assessQuality
from src.scripts.videoMerge import buildSlideshow, concatClips
from src.utils.logger import getLogger
from src.utils.result import makeResult

log = getLogger(__name__)


def _takenAt(photoPath: str) -> str:
    """Return EXIF DateTimeOriginal string, or '9999' to sort to end when absent."""
    r = extractExif(photoPath)
    if r["success"] and r["output"]["taken_at"]:
        return r["output"]["taken_at"]
    return "9999"


def runBuildHighlight(myPhotoPaths: list[str], myClipPaths: list[str],
                       outputDir: str, audioPath: str | None = None) -> dict:
    startTime = time.time()
    Path(outputDir).mkdir(parents=True, exist_ok=True)

    # --- B1: Photo selection – dedupe → quality filter → time sort ---
    dedupeResult = dedupePhotos(myPhotoPaths)
    uniquePhotos = dedupeResult["output"]["unique_paths"] if dedupeResult["success"] else myPhotoPaths
    log.info("B1: %d → %d after dedupe", len(myPhotoPaths), len(uniquePhotos))

    qualityPassed = []
    for p in uniquePhotos:
        r = assessQuality(p, blurThreshold=BLUR_THRESHOLD)
        if r["success"] and not r["output"]["is_blurry"]:
            qualityPassed.append(p)
        elif not r["success"]:
            qualityPassed.append(p)  # keep on quality-check error

    # Fall back to all unique photos if quality filter rejects everything
    candidatePhotos = qualityPassed if qualityPassed else uniquePhotos

    # Sort by EXIF capture time (ascending = chronological)
    candidatePhotos.sort(key=_takenAt)
    selectedPhotos = candidatePhotos[:MAX_HIGHLIGHT_PHOTOS]
    log.info("B1: %d photos selected (sorted by time, max %d)", len(selectedPhotos), MAX_HIGHLIGHT_PHOTOS)

    # Copy selected photos to output dir
    selectedDir = Path(outputDir) / "selected_photos"
    selectedDir.mkdir(exist_ok=True)
    copiedPhotos = []
    for p in selectedPhotos:
        dest = selectedDir / Path(p).name
        shutil.copy2(p, dest)
        copiedPhotos.append(str(dest))

    # Attach taken_at metadata for callers (e.g. map feature)
    photoMeta = [{"path": p, "taken_at": _takenAt(p).replace("9999", "") or None}
                 for p in copiedPhotos]

    # --- B2: Highlight video — two explicit templates ---
    highlightPath = str(Path(outputDir) / "highlight.mp4")

    if myClipPaths and copiedPhotos:
        # Template 2: build slideshow then prepend video clips
        slidePath = str(Path(outputDir) / "_slide.mp4")
        sr = buildSlideshow(copiedPhotos, slidePath, PHOTO_SLIDE_DURATION_S, audioPath)
        if sr["success"]:
            finalResult = concatClips(myClipPaths + [slidePath], highlightPath)
        else:
            # Slideshow failed — fall back to clips only
            log.warning("B2 slideshow failed (%s), falling back to clips only", sr.get("error"))
            finalResult = concatClips(myClipPaths, highlightPath)
    elif myClipPaths:
        # Template 2 with no photos: clips concat
        finalResult = concatClips(myClipPaths, highlightPath)
    else:
        # Template 1: photos-only slideshow
        finalResult = buildSlideshow(copiedPhotos, highlightPath, PHOTO_SLIDE_DURATION_S, audioPath)

    if not finalResult["success"]:
        return makeResult(False, error=f"Highlight render failed: {finalResult['error']}", startTime=startTime)

    log.info("B done: highlight at %s (%d photos)", highlightPath, len(copiedPhotos))
    return makeResult(
        True,
        output={
            "selected_photos": copiedPhotos,
            "photo_meta": photoMeta,
            "highlight_video_path": highlightPath,
            "photo_count": len(copiedPhotos),
        },
        startTime=startTime,
    )
