"""
videoClip.py — cut a sub-clip from a video using ffmpeg.
"""
import subprocess
import time
from pathlib import Path

from src.utils.logger import getLogger
from src.utils.result import makeResult

log = getLogger(__name__)


def cutClip(videoPath: str, startS: float, endS: float, outputPath: str, timeoutS: float = 120.0) -> dict:
    """
    Extract [startS, endS] from videoPath into outputPath using ffmpeg stream copy.
    output: {"output_path": str, "duration_s": float}
    """
    startTime = time.time()
    try:
        durationS = endS - startS
        if durationS <= 0:
            return makeResult(False, error=f"Invalid clip range: {startS}–{endS}", startTime=startTime)

        Path(outputPath).parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(startS),
            "-i", str(videoPath),
            "-t", str(durationS),
            "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-avoid_negative_ts", "make_zero",
            str(outputPath),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeoutS)
        if result.returncode != 0:
            return makeResult(False, error=result.stderr[-500:], startTime=startTime)

        return makeResult(True, output={"output_path": outputPath, "duration_s": round(durationS, 3)}, startTime=startTime)
    except subprocess.TimeoutExpired:
        return makeResult(False, error="ffmpeg timeout", startTime=startTime)
    except Exception as e:
        log.exception("cutClip failed")
        return makeResult(False, error=str(e), startTime=startTime)
