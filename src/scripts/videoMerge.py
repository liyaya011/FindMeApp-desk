"""
videoMerge.py — assemble clips and/or photo slideshow into a single video using ffmpeg.
"""
import subprocess
import tempfile
import time
from pathlib import Path

from src.utils.logger import getLogger
from src.utils.result import makeResult

log = getLogger(__name__)


def buildSlideshow(photoPaths: list[str], outputPath: str, slideDurationS: float = 3.0,
                   audioPath: str | None = None, timeoutS: float = 300.0) -> dict:
    """
    Create a video slideshow from photos.  Each photo shown for slideDurationS seconds.
    output: {"output_path": str}
    """
    startTime = time.time()
    try:
        if not photoPaths:
            return makeResult(False, error="No photos provided", startTime=startTime)

        Path(outputPath).parent.mkdir(parents=True, exist_ok=True)

        # Build ffmpeg concat input using -loop + -t per image
        filterParts, inputArgs = [], []
        for i, p in enumerate(photoPaths):
            inputArgs += ["-loop", "1", "-t", str(slideDurationS), "-i", str(p)]
            filterParts.append(f"[{i}:v]scale=1280:720:force_original_aspect_ratio=decrease,"
                               f"pad=1280:720:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=25[v{i}]")

        concatInputs = "".join(f"[v{i}]" for i in range(len(photoPaths)))
        filterParts.append(f"{concatInputs}concat=n={len(photoPaths)}:v=1:a=0[vout]")
        filterGraph = ";".join(filterParts)

        cmd = inputArgs + ["-filter_complex", filterGraph, "-map", "[vout]",
                           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(outputPath)]
        if audioPath:
            cmd = ["-i", str(audioPath)] + cmd + ["-shortest"]
        cmd = ["ffmpeg"] + cmd

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeoutS)
        if result.returncode != 0:
            return makeResult(False, error=result.stderr[-500:], startTime=startTime)
        return makeResult(True, output={"output_path": outputPath}, startTime=startTime)
    except subprocess.TimeoutExpired:
        return makeResult(False, error="ffmpeg slideshow timeout", startTime=startTime)
    except Exception as e:
        log.exception("buildSlideshow failed")
        return makeResult(False, error=str(e), startTime=startTime)


def concatClips(clipPaths: list[str], outputPath: str, timeoutS: float = 300.0) -> dict:
    """
    Concatenate video clips into one file using ffmpeg concat demuxer.
    output: {"output_path": str}
    """
    startTime = time.time()
    try:
        if not clipPaths:
            return makeResult(False, error="No clips provided", startTime=startTime)

        Path(outputPath).parent.mkdir(parents=True, exist_ok=True)

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            listPath = f.name
            for p in clipPaths:
                f.write(f"file '{Path(p).resolve()}'\n")

        cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", listPath,
               "-c", "copy", str(outputPath)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeoutS)
        Path(listPath).unlink(missing_ok=True)

        if result.returncode != 0:
            return makeResult(False, error=result.stderr[-500:], startTime=startTime)
        return makeResult(True, output={"output_path": outputPath}, startTime=startTime)
    except subprocess.TimeoutExpired:
        return makeResult(False, error="ffmpeg concat timeout", startTime=startTime)
    except Exception as e:
        log.exception("concatClips failed")
        return makeResult(False, error=str(e), startTime=startTime)
