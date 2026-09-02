"""Resolve the ffmpeg executable in development and packaged applications."""
import shutil


def getFfmpegPath() -> str | None:
    """Prefer the bundled imageio-ffmpeg binary, then a system installation."""
    try:
        from imageio_ffmpeg import get_ffmpeg_exe

        bundledPath = get_ffmpeg_exe()
        if bundledPath:
            return bundledPath
    except (ImportError, RuntimeError):
        pass
    return shutil.which("ffmpeg")
