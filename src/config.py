import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
SESSIONS_DIR = DATA_DIR / "sessions"

load_dotenv(BASE_DIR / "config" / ".env")

AMAP_KEY = os.getenv("AMAP_KEY", "")

# Face matching
FACE_SIMILARITY_THRESHOLD = 0.50   # cosine distance; lower = stricter

# Video sampling
VIDEO_SAMPLE_FPS = 2                # frames per second to sample (PDF spec: 1–2 fps)
MIN_SEGMENT_DURATION_S = 1.0       # min duration to emit a segment
MERGE_GAP_S = 5.0                  # max gap between hits to still merge

# Photo quality
BLUR_THRESHOLD = 100.0             # Laplacian variance; below = blurry
MIN_FACE_SIZE_PX = 40              # face bounding box min dimension

# Highlight
MAX_HIGHLIGHT_PHOTOS = 20
MAX_HIGHLIGHT_DURATION_S = 60
PHOTO_SLIDE_DURATION_S = 3         # each photo on screen in slideshow
