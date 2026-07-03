"""
videoSample.py — extract frames from a video at a given sample rate using OpenCV.
"""
import time
from pathlib import Path

import cv2
import numpy as np

from src.utils.logger import getLogger
from src.utils.result import makeResult

log = getLogger(__name__)


def sampleFrames(videoPath: str, sampleFps: float = 1.0, timeoutS: float = 300.0) -> dict:
    """
    Sample frames from videoPath at sampleFps frames per second.
    output: {
        "frames": [{"timestamp_s": float, "frame_idx": int, "frame": ndarray}],
        "video_fps": float,
        "duration_s": float,
        "total_frames_sampled": int,
    }
    frames are kept as numpy arrays (BGR) for downstream face detection.
    """
    startTime = time.time()
    try:
        cap = cv2.VideoCapture(str(videoPath))
        if not cap.isOpened():
            return makeResult(False, error=f"Cannot open video: {videoPath}", startTime=startTime)

        videoFps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        totalFrames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        durationS = totalFrames / videoFps
        sampleInterval = max(1, int(videoFps / sampleFps))

        sampledFrames = []
        frameIdx = 0
        while True:
            if time.time() - startTime > timeoutS:
                log.warning("sampleFrames timeout reached for %s", videoPath)
                break

            ret, frame = cap.read()
            if not ret:
                break
            if frameIdx % sampleInterval == 0:
                timestampS = frameIdx / videoFps
                sampledFrames.append({"timestamp_s": round(timestampS, 3), "frame_idx": frameIdx, "frame": frame})
            frameIdx += 1

        cap.release()
        return makeResult(
            True,
            output={
                "frames": sampledFrames,
                "video_fps": videoFps,
                "duration_s": round(durationS, 3),
                "total_frames_sampled": len(sampledFrames),
            },
            startTime=startTime,
        )
    except Exception as e:
        log.exception("sampleFrames failed: %s", videoPath)
        return makeResult(False, error=str(e), startTime=startTime)
