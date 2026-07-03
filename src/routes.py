"""
routes.py — FastAPI route handlers for all API endpoints.
"""
import asyncio
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from src import sessions
from src.config import DATA_DIR, SESSIONS_DIR
from src.utils.logger import getLogger

log = getLogger(__name__)
router = APIRouter(prefix="/api")
_executor = ThreadPoolExecutor(max_workers=2)

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}


# ── Sessions ──────────────────────────────────────────────────────────────────

@router.post("/sessions")
def createSession():
    sessionId = sessions.createSession()
    return {"session_id": sessionId}


@router.get("/sessions/{sessionId}")
def getSession(sessionId: str):
    state = sessions.getSession(sessionId)
    if not state:
        raise HTTPException(404, "Session not found")
    return state


# ── File uploads ──────────────────────────────────────────────────────────────

@router.post("/sessions/{sessionId}/references")
async def uploadReferences(sessionId: str, files: list[UploadFile] = File(...)):
    state = sessions.getSession(sessionId)
    if not state:
        raise HTTPException(404, "Session not found")

    refDir = sessions.sessionDir(sessionId) / "references"
    savedPaths = []
    for f in files:
        dest = refDir / f.filename
        dest.write_bytes(await f.read())
        savedPaths.append(str(dest))

    allRefs = list(set(state.get("reference_paths", []) + savedPaths))
    sessions.updateSession(sessionId, {"reference_paths": allRefs})
    return {"saved": savedPaths, "total_references": len(allRefs)}


@router.post("/sessions/{sessionId}/media")
async def uploadMedia(sessionId: str, files: list[UploadFile] = File(...)):
    state = sessions.getSession(sessionId)
    if not state:
        raise HTTPException(404, "Session not found")

    mediaDir = sessions.sessionDir(sessionId) / "media"
    savedPaths = []
    for f in files:
        dest = mediaDir / f.filename
        dest.write_bytes(await f.read())
        savedPaths.append(str(dest))

    allMedia = list(set(state.get("media_paths", []) + savedPaths))
    sessions.updateSession(sessionId, {"media_paths": allMedia})
    return {"saved": savedPaths, "total_media": len(allMedia)}


# ── Feature A: Find Me ────────────────────────────────────────────────────────

def _runFindMe(sessionId: str):
    from src.playbooks.findPhotos import runFindPhotos
    from src.playbooks.findVideos import runFindVideos

    try:
        state = sessions.getSession(sessionId)
        refPaths = state["reference_paths"]
        mediaPaths = state["media_paths"]

        photoPaths = [p for p in mediaPaths if Path(p).suffix.lower() in PHOTO_EXTS]
        videoPaths = [p for p in mediaPaths if Path(p).suffix.lower() in VIDEO_EXTS]

        resultsBase = sessions.sessionDir(sessionId) / "results"
        findResults = {}

        if photoPaths:
            sessions.updateSession(sessionId, {"status": "processing_photos"})
            pr = runFindPhotos(refPaths, photoPaths, str(resultsBase / "my_photos"))
            findResults["photos"] = pr

        if videoPaths:
            sessions.updateSession(sessionId, {"status": "processing_videos"})
            vr = runFindVideos(refPaths, videoPaths, str(resultsBase / "my_clips"))
            findResults["videos"] = vr

        sessions.updateSession(sessionId, {"status": "done", "results": findResults})
        log.info("Find Me complete for session %s", sessionId)
    except Exception as e:
        log.exception("_runFindMe failed for session %s", sessionId)
        sessions.updateSession(sessionId, {"status": "error", "error": str(e)})


@router.post("/sessions/{sessionId}/find")
def startFind(sessionId: str, background_tasks: BackgroundTasks):
    state = sessions.getSession(sessionId)
    if not state:
        raise HTTPException(404, "Session not found")
    if not state.get("reference_paths"):
        raise HTTPException(400, "Upload at least one reference photo first")
    if not state.get("media_paths"):
        raise HTTPException(400, "Upload media files first")

    sessions.updateSession(sessionId, {"status": "processing", "error": None})
    background_tasks.add_task(_runFindMe, sessionId)
    return {"status": "processing"}


# ── Feature B: Highlight ──────────────────────────────────────────────────────

def _runHighlight(sessionId: str, audioPath: str | None):
    from src.playbooks.buildHighlight import runBuildHighlight

    try:
        state = sessions.getSession(sessionId)
        results = state.get("results", {})
        photosResult = results.get("photos", {})
        videosResult = results.get("videos", {})

        myPhotos = photosResult.get("output", {}).get("matched_paths", []) if photosResult.get("success") else []
        myClips = []
        if videosResult.get("success"):
            for v in videosResult["output"].get("videos", []):
                myClips.extend(c["path"] for c in v.get("clips", []))

        outputDir = str(sessions.sessionDir(sessionId) / "results" / "highlight")
        hr = runBuildHighlight(myPhotos, myClips, outputDir, audioPath)

        results["highlight"] = hr
        sessions.updateSession(sessionId, {"results": results, "highlight_status": "done" if hr["success"] else "error"})
    except Exception as e:
        log.exception("_runHighlight failed for session %s", sessionId)
        sessions.updateSession(sessionId, {"highlight_status": "error"})


@router.post("/sessions/{sessionId}/highlight")
def startHighlight(sessionId: str, background_tasks: BackgroundTasks, audioPath: str | None = None):
    state = sessions.getSession(sessionId)
    if not state:
        raise HTTPException(404, "Session not found")
    background_tasks.add_task(_runHighlight, sessionId, audioPath)
    return {"status": "processing"}


# ── Feature C: Travel Map ─────────────────────────────────────────────────────

@router.get("/sessions/{sessionId}/map")
def getTravelMap(sessionId: str):
    from src.playbooks.travelMap import runTravelMap

    state = sessions.getSession(sessionId)
    if not state:
        raise HTTPException(404, "Session not found")

    results = state.get("results", {})
    # Prefer B1-selected (curated, time-sorted) photos; fall back to raw A1 matches
    hlOutput = results.get("highlight", {}).get("output", {}) or {}
    myPhotos = hlOutput.get("selected_photos") or \
               results.get("photos", {}).get("output", {}).get("matched_paths", [])
    if not myPhotos:
        return {"map_points": [], "total": 0, "missing_gps_count": 0}

    tr = runTravelMap(myPhotos)
    if not tr["success"]:
        raise HTTPException(500, tr["error"])

    # Attach URL to each point — strip DATA_DIR prefix so URL matches /data mount
    dataDir = str(DATA_DIR)
    for point in tr["output"]["map_points"]:
        p = point["photo_path"]
        if p.startswith(dataDir):
            point["photo_url"] = "/data/" + p[len(dataDir):].lstrip("/")
        else:
            point["photo_url"] = p

    return tr["output"]


# ── Config (exposes non-sensitive client config) ──────────────────────────────

@router.get("/config")
def getConfig():
    from src.config import AMAP_KEY
    return {"amap_key": AMAP_KEY}
