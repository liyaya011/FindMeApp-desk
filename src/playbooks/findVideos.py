"""
findVideos.py — Playbook A2: locate and clip video segments containing the user.

Inputs:  referencePhotoPaths, targetVideoPaths, outputDir, sampleFps, threshold
Outputs: per-video segment lists + cut sub-clip paths
Success: at least one segment found OR video list empty
"""
import time
from pathlib import Path

from src.config import (
    FACE_SIMILARITY_THRESHOLD,
    MERGE_GAP_S,
    MIN_SEGMENT_DURATION_S,
    VIDEO_SAMPLE_FPS,
)
from src.scripts.faceDetect import detectFaces, _getApp
from src.scripts.faceMatch import matchFace
from src.scripts.videoSample import sampleFrames
from src.scripts.videoClip import cutClip
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
        bestFace = max(r["output"]["faces"], key=lambda f: f["det_score"])
        embeddings.append(bestFace["embedding"])
    return embeddings, errors


def _mergeSegments(hitTimestamps: list[float], mergeGapS: float, minDurationS: float) -> list[dict]:
    """Merge consecutive hit timestamps into [start, end] segments."""
    if not hitTimestamps:
        return []
    segments = []
    segStart = hitTimestamps[0]
    segEnd = hitTimestamps[0]
    for ts in hitTimestamps[1:]:
        if ts - segEnd <= mergeGapS:
            segEnd = ts
        else:
            if segEnd - segStart >= minDurationS:
                segments.append({"start_s": round(segStart, 3), "end_s": round(segEnd, 3)})
            segStart = ts
            segEnd = ts
    if segEnd - segStart >= minDurationS:
        segments.append({"start_s": round(segStart, 3), "end_s": round(segEnd, 3)})
    return segments


def _detectFrameFromArray(frameArray, refEmbeddings: list, threshold: float) -> bool:
    """Run face detection on a numpy frame array and match against references."""
    faces = _getApp().get(frameArray)
    for face in faces:
        mr = matchFace(face.embedding.tolist(), refEmbeddings, threshold)
        if mr["success"] and mr["output"]["matched"]:
            return True
    return False


def runFindVideos(referencePhotoPaths: list[str], targetVideoPaths: list[str],
                   outputDir: str, sampleFps: float = VIDEO_SAMPLE_FPS,
                   threshold: float = FACE_SIMILARITY_THRESHOLD) -> dict:
    startTime = time.time()
    Path(outputDir).mkdir(parents=True, exist_ok=True)

    refEmbeddings, refErrors = _extractReferenceEmbeddings(referencePhotoPaths)
    if not refEmbeddings:
        return makeResult(False, error=f"No reference face extracted. {refErrors}", startTime=startTime)

    log.info("A2: %d ref embeddings, scanning %d videos at %.1f fps", len(refEmbeddings), len(targetVideoPaths), sampleFps)

    allVideoResults = []
    for videoPath in targetVideoPaths:
        videoName = Path(videoPath).stem
        sr = sampleFrames(videoPath, sampleFps=sampleFps)
        if not sr["success"]:
            log.warning("sampleFrames failed for %s: %s", videoPath, sr["error"])
            allVideoResults.append({"video": videoPath, "segments": [], "clips": [], "error": sr["error"]})
            continue

        hitTimestamps = []
        for frameData in sr["output"]["frames"]:
            try:
                matched = _detectFrameFromArray(frameData["frame"], refEmbeddings, threshold)
                if matched:
                    hitTimestamps.append(frameData["timestamp_s"])
            except Exception as e:
                log.debug("frame detection error: %s", e)

        segments = _mergeSegments(hitTimestamps, MERGE_GAP_S, MIN_SEGMENT_DURATION_S)
        log.info("A2: %s → %d segments from %d hits", videoName, len(segments), len(hitTimestamps))

        clips = []
        for i, seg in enumerate(segments):
            clipPath = str(Path(outputDir) / f"{videoName}_seg{i:02d}.mp4")
            cr = cutClip(videoPath, seg["start_s"], seg["end_s"], clipPath)
            if cr["success"]:
                clips.append({"path": clipPath, **seg})
            else:
                log.warning("cutClip failed for %s seg %d: %s", videoName, i, cr["error"])

        allVideoResults.append({"video": videoPath, "segments": segments, "clips": clips, "error": None})

    totalClips = sum(len(v["clips"]) for v in allVideoResults)
    log.info("A2 done: %d clips from %d videos", totalClips, len(targetVideoPaths))
    return makeResult(True, output={"videos": allVideoResults, "total_clips": totalClips}, startTime=startTime)
