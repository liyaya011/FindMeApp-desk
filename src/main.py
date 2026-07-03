"""
main.py — FastAPI application entry point.
Run: uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from src.config import DATA_DIR, SESSIONS_DIR
from src.routes import router
from src.utils.logger import getLogger

log = getLogger(__name__)

SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="FindMeApp", version="0.1.0")

# API routes
app.include_router(router)

# Serve session result files (photos, clips, highlight video)
app.mount("/data", StaticFiles(directory=str(DATA_DIR)), name="data")

# Serve frontend
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR / "static")), name="static")


@app.get("/test-upload")
def testUpload():
    return FileResponse(str(FRONTEND_DIR / "templates" / "test_upload.html"))


@app.get("/")
def index():
    return FileResponse(str(FRONTEND_DIR / "templates" / "index.html"))


@app.get("/health")
def health():
    return {"status": "ok"}
