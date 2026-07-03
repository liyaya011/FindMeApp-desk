"""
travelMap.py — Playbook C: extract GPS+time from matched photos and return map points.

Inputs:  myPhotoPaths
Outputs: map_points list sorted by taken_at, missing_gps_count
Success: always (GPS may be absent; caller handles manual pin fallback)
"""
import time
from pathlib import Path

from src.scripts.exifExtract import extractExif
from src.utils.logger import getLogger
from src.utils.result import makeResult

log = getLogger(__name__)


def runTravelMap(myPhotoPaths: list[str]) -> dict:
    startTime = time.time()

    mapPoints = []
    missingGps = 0

    for photoPath in myPhotoPaths:
        r = extractExif(photoPath)
        if not r["success"]:
            log.warning("EXIF extract failed for %s: %s", photoPath, r["error"])
            continue

        data = r["output"]
        point = {
            "photo_path": photoPath,
            "taken_at": data["taken_at"],
            "has_gps": data["has_gps"],
            "lat": data["lat"],
            "lng": data["lng"],
        }
        if not data["has_gps"]:
            missingGps += 1
        mapPoints.append(point)

    # Sort chronologically; photos without timestamp go to end
    mapPoints.sort(key=lambda p: p["taken_at"] or "9999")

    log.info("C done: %d points, %d missing GPS", len(mapPoints), missingGps)
    return makeResult(
        True,
        output={
            "map_points": mapPoints,
            "total": len(mapPoints),
            "missing_gps_count": missingGps,
        },
        startTime=startTime,
    )
