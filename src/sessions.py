"""
sessions.py — in-memory session store and helper utilities.
"""
import json
import uuid
from pathlib import Path
from typing import Any

from src.config import SESSIONS_DIR
from src.utils.logger import getLogger

log = getLogger(__name__)

SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


def createSession() -> str:
    sessionId = str(uuid.uuid4())
    sessionDir = SESSIONS_DIR / sessionId
    for sub in ("references", "media", "results/my_photos", "results/my_clips", "results/highlight"):
        (sessionDir / sub).mkdir(parents=True, exist_ok=True)

    initialState = {
        "id": sessionId,
        "status": "created",
        "reference_paths": [],
        "media_paths": [],
        "results": {},
        "error": None,
    }
    _writeState(sessionId, initialState)
    return sessionId


def getSession(sessionId: str) -> dict | None:
    stateFile = SESSIONS_DIR / sessionId / "session.json"
    if not stateFile.exists():
        return None
    return json.loads(stateFile.read_text())


def updateSession(sessionId: str, updates: dict) -> None:
    state = getSession(sessionId) or {}
    state.update(updates)
    _writeState(sessionId, state)


def sessionDir(sessionId: str) -> Path:
    return SESSIONS_DIR / sessionId


def _writeState(sessionId: str, state: dict) -> None:
    stateFile = SESSIONS_DIR / sessionId / "session.json"
    stateFile.write_text(json.dumps(state, indent=2))
