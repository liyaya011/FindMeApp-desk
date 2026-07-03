"""
exifExtract.py — extract GPS coordinates and datetime from image EXIF.
"""
import time
from pathlib import Path
from datetime import datetime

import exifread

from src.utils.logger import getLogger
from src.utils.result import makeResult

log = getLogger(__name__)


def _dmsToDecimal(dmsTag, refTag) -> float | None:
    """Convert EXIF DMS rational values to decimal degrees."""
    try:
        dms = dmsTag.values
        degrees = float(dms[0].num) / float(dms[0].den)
        minutes = float(dms[1].num) / float(dms[1].den)
        seconds = float(dms[2].num) / float(dms[2].den)
        decimal = degrees + minutes / 60.0 + seconds / 3600.0
        if str(refTag.values) in ("S", "W"):
            decimal = -decimal
        return round(decimal, 6)
    except Exception:
        return None


def extractExif(imagePath: str) -> dict:
    """
    Extract GPS lat/lng and datetime from image EXIF.
    output: {"lat": float|None, "lng": float|None, "taken_at": str|None, "has_gps": bool}
    """
    startTime = time.time()
    try:
        with open(str(imagePath), "rb") as f:
            tags = exifread.process_file(f, stop_tag="GPS GPSLongitude", details=False)

        lat, lng = None, None
        if "GPS GPSLatitude" in tags and "GPS GPSLatitudeRef" in tags:
            lat = _dmsToDecimal(tags["GPS GPSLatitude"], tags["GPS GPSLatitudeRef"])
        if "GPS GPSLongitude" in tags and "GPS GPSLongitudeRef" in tags:
            lng = _dmsToDecimal(tags["GPS GPSLongitude"], tags["GPS GPSLongitudeRef"])

        takenAt = None
        for dateTag in ("EXIF DateTimeOriginal", "EXIF DateTime", "Image DateTime"):
            if dateTag in tags:
                try:
                    takenAt = str(tags[dateTag].values)
                except Exception:
                    pass
                break

        return makeResult(
            True,
            output={"lat": lat, "lng": lng, "taken_at": takenAt, "has_gps": lat is not None and lng is not None},
            startTime=startTime,
        )
    except Exception as e:
        log.exception("extractExif failed: %s", imagePath)
        return makeResult(False, error=str(e), startTime=startTime)
