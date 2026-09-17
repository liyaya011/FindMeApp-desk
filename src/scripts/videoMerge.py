"""
videoMerge.py — assemble clips and/or photo slideshow into a single video using ffmpeg.
"""
import subprocess
import time
from pathlib import Path

from src.utils.logger import getLogger
from src.utils.result import makeResult
from src.utils.ffmpeg import getFfmpegPath
from src.config import HIGHLIGHT_WIDTH, HIGHLIGHT_HEIGHT, HIGHLIGHT_FPS

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
        # Canvas is the shared HIGHLIGHT canvas so the slideshow can be safely
        # concatenated with video clips (same resolution/fps everywhere).
        filterParts, inputArgs = [], []
        for i, p in enumerate(photoPaths):
            inputArgs += ["-loop", "1", "-t", str(slideDurationS), "-i", str(p)]
            filterParts.append(f"[{i}:v]scale={HIGHLIGHT_WIDTH}:{HIGHLIGHT_HEIGHT}:force_original_aspect_ratio=decrease,"
                               f"pad={HIGHLIGHT_WIDTH}:{HIGHLIGHT_HEIGHT}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
                               f"fps={HIGHLIGHT_FPS}[v{i}]")

        concatInputs = "".join(f"[v{i}]" for i in range(len(photoPaths)))
        filterParts.append(f"{concatInputs}concat=n={len(photoPaths)}:v=1:a=0[vout]")
        filterGraph = ";".join(filterParts)

        cmd = inputArgs + ["-filter_complex", filterGraph, "-map", "[vout]",
                           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-y", str(outputPath)]
        if audioPath:
            cmd = ["-i", str(audioPath)] + cmd + ["-shortest"]
        ffmpegPath = getFfmpegPath()
        if not ffmpegPath:
            return makeResult(False, error="ffmpeg is not available", startTime=startTime)
        cmd = [ffmpegPath] + cmd

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
    Concatenate video clips into one file.

    Every input is normalized to the shared HIGHLIGHT canvas (scale+pad,
    unified fps, yuv420p) and re-encoded via the ffmpeg concat FILTER.
    The concat demuxer + `-c copy` is NOT safe here: inputs can have different
    resolutions/fps (e.g. 1080p@30 video clips + 720p@25 slideshow); stream
    copying mismatched streams yields a corrupt file whose frames decoders
    render with ghosting / duplicated-image artifacts and broken seeking.

    output: {"output_path": str}
    """
    startTime = time.time()
    try:
        if not clipPaths:
            return makeResult(False, error="No clips provided", startTime=startTime)

        Path(outputPath).parent.mkdir(parents=True, exist_ok=True)

        filterParts, inputArgs = [], []
        for i, p in enumerate(clipPaths):
            inputArgs += ["-i", str(p)]
            filterParts.append(
                f"[{i}:v]scale={HIGHLIGHT_WIDTH}:{HIGHLIGHT_HEIGHT}:force_original_aspect_ratio=decrease,"
                f"pad={HIGHLIGHT_WIDTH}:{HIGHLIGHT_HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
                f"setsar=1,fps={HIGHLIGHT_FPS},format=yuv420p[v{i}]"
            )
        concatInputs = "".join(f"[v{i}]" for i in range(len(clipPaths)))
        filterParts.append(f"{concatInputs}concat=n={len(clipPaths)}:v=1:a=0[vout]")
        filterGraph = ";".join(filterParts)

        ffmpegPath = getFfmpegPath()
        if not ffmpegPath:
            return makeResult(False, error="ffmpeg is not available", startTime=startTime)
        cmd = [ffmpegPath, "-y"] + inputArgs + [
            "-filter_complex", filterGraph, "-map", "[vout]",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(HIGHLIGHT_FPS),
            str(outputPath),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeoutS)
        if result.returncode != 0:
            return makeResult(False, error=result.stderr[-500:], startTime=startTime)
        return makeResult(True, output={"output_path": outputPath}, startTime=startTime)
    except subprocess.TimeoutExpired:
        return makeResult(False, error="ffmpeg concat timeout", startTime=startTime)
    except Exception as e:
        log.exception("concatClips failed")
        return makeResult(False, error=str(e), startTime=startTime)
