# FindMeApp — Feature Specification (MVP v1)

> Verified against real test data on 2026-04-22. All three features run end-to-end.

---

## Architecture Overview

```
User Upload (selfies + media)
        │
        ▼
  Feature A — Find Me
  ├── A1: findPhotos     → matched photos
  └── A2: findVideos     → clipped video segments
        │
        ▼
  Feature B — Highlight
  └── B1 photo select (time-sorted) + B2 video render → highlight.mp4
        │
        ▼
  Feature C — Travel Map
  └── GPS extraction from B1 photos → map_points (chronological)
```

Data dependency: **A → B → C**. Run in that order per session.

---

## Feature A: Find Me

### A1 — Photo Matching (`src/playbooks/findPhotos.py`)

**Inputs**
- `referencePhotoPaths`: 1–3 selfie photos of the subject
- `targetPhotoPaths`: batch of photos to search
- `outputDir`: destination for matched copies

**Pipeline**
1. Extract face embedding from each reference (insightface `buffalo_l`)
2. For each target photo: detect faces → compute cosine distance to each reference embedding
3. Accept match if `min(distances) < FACE_SIMILARITY_THRESHOLD` (default 0.50)
4. Quality filter: reject blurry (`Laplacian < 100`) or tiny faces (`< 40px`)
5. Copy matched photos to `outputDir`

**Output**
```json
{
  "success": true,
  "output": {
    "matched_paths": ["...jpg"],
    "matched_count": 4,
    "total": 5
  }
}
```

**Tuning**
| Parameter | Default | Effect |
|---|---|---|
| `FACE_SIMILARITY_THRESHOLD` | 0.50 | Lower = stricter. 0.40–0.55 typical range |
| `BLUR_THRESHOLD` | 100.0 | Laplacian variance; raise to keep more blurry photos |
| `MIN_FACE_SIZE_PX` | 40 | Minimum face bounding box side; lower for small/distant faces |

---

### A2 — Video Segment Detection (`src/playbooks/findVideos.py`)

**Inputs**
- `referencePhotoPaths`: same selfies as A1
- `targetVideoPaths`: MP4 / MOV / AVI / MKV files
- `outputDir`: destination for sub-clips

**Pipeline**
1. Extract reference embeddings (same as A1)
2. Sample video at `VIDEO_SAMPLE_FPS` fps (default 2) via OpenCV
3. For each frame: run insightface detection → match against references
4. Collect hit timestamps
5. `_mergeSegments`: merge timestamps within `MERGE_GAP_S` (5s) into segments; drop if `< MIN_SEGMENT_DURATION_S` (1s)
6. `cutClip`: re-encode each segment with `libx264/aac veryfast` for accurate cuts

**Output**
```json
{
  "success": true,
  "output": {
    "videos": [
      {
        "video": "MJ_xxx.MOV",
        "segments": [{"start_s": 6.0, "end_s": 10.0}],
        "clips": [{"path": "...seg00.mp4", "start_s": 6.0, "end_s": 10.0}]
      }
    ],
    "total_clips": 1
  }
}
```

**Tuning**
| Parameter | Default | Effect |
|---|---|---|
| `VIDEO_SAMPLE_FPS` | 2 | Frames/sec sampled. Higher = more hits, slower |
| `MERGE_GAP_S` | 5.0 | Max gap (seconds) to merge into one segment |
| `MIN_SEGMENT_DURATION_S` | 1.0 | Minimum segment length to emit |
| `FACE_SIMILARITY_THRESHOLD` | 0.50 | Same threshold as A1 |

**Known Limitation**: Reference photos taken at very different angles/lighting from the video will yield high distances (0.9+). Supply 2–3 diverse selfies (front, slight angle, good lighting) to maximize recall.

---

## Feature B: Highlight Reel (`src/playbooks/buildHighlight.py`)

### B1 — Photo Selection (time-sorted)

1. **Deduplicate** via perceptual hash (`photoDedupe.py`)
2. **Quality filter**: reject blurry frames; keep on filter error to avoid empty result
3. **Sort chronologically** by `EXIF DateTimeOriginal` ascending; photos without timestamp go to end
4. **Truncate** to `MAX_HIGHLIGHT_PHOTOS` (default 20)
5. Copy to `results/highlight/selected_photos/`

Output includes `photo_meta` list with `{"path", "taken_at"}` per photo, enabling downstream features to use EXIF time.

### B2 — Video Assembly

Two templates selected automatically:

| Condition | Template | Assembly |
|---|---|---|
| Photos only | **Template 1** | `buildSlideshow` — each photo shown for `PHOTO_SLIDE_DURATION_S` (3s) |
| Photos + video clips | **Template 2** | Clips video prepended to photo slideshow, re-encoded to single MP4 |
| Clips only (no photos) | Template 2 fallback | `concatClips` only |

Output: `results/highlight/highlight.mp4` (h264/aac, 1920×1080 for clips, 1280×720 for slideshow).

**BGM**: Pass `audioPath` to the highlight endpoint (`?audioPath=...`) to mix background audio. The shortest stream determines final duration (`-shortest`).

**Config**
| Parameter | Default | Effect |
|---|---|---|
| `MAX_HIGHLIGHT_PHOTOS` | 20 | Max photos in slideshow |
| `MAX_HIGHLIGHT_DURATION_S` | 60 | Unused in assembly; available for future trim |
| `PHOTO_SLIDE_DURATION_S` | 3 | Seconds each photo is shown |

---

## Feature C: Travel Memory Map (`src/playbooks/travelMap.py`)

**Input**: B1 `selected_photos` (preferred) or A1 `matched_paths` as fallback.

**Pipeline**
1. `extractExif` per photo → `lat`, `lng`, `taken_at`
2. Sort by `taken_at` ascending (missing timestamp sorts to end)
3. Return map points

**Output** (from `GET /api/sessions/{id}/map`)
```json
{
  "map_points": [
    {
      "photo_path": "...",
      "photo_url": "/data/sessions/.../selected_photos/xxx.jpg",
      "taken_at": "2025:05:02 08:21:47",
      "has_gps": true,
      "lat": 38.851553,
      "lng": 105.729136
    }
  ],
  "total": 3,
  "missing_gps_count": 0
}
```

**Frontend**: Gaode Maps JS SDK. Set `AMAP_KEY` in `config/.env`. If key absent or empty, map tab shows a friendly fallback message — no JS error.

---

## API Reference

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/sessions` | Create session → `{session_id}` |
| `GET` | `/api/sessions/{id}` | Poll session state |
| `POST` | `/api/sessions/{id}/references` | Upload reference selfies |
| `POST` | `/api/sessions/{id}/media` | Upload photos + videos |
| `POST` | `/api/sessions/{id}/find` | Start Feature A (background) |
| `POST` | `/api/sessions/{id}/highlight` | Start Feature B (background); optional `?audioPath=` |
| `GET` | `/api/sessions/{id}/map` | Feature C — returns map points |
| `GET` | `/api/config` | Returns `amap_key` for frontend SDK init |
| `GET` | `/health` | Server health check |

### Session Status Lifecycle

```
created → processing → processing_photos → processing_videos → done
                                                             └→ error
```

`highlight_status`: `null` → `done` | `error` (independent from main status)

---

## Session Data Layout

```
data/sessions/{session_id}/
├── references/               # Uploaded selfies
├── media/                    # Uploaded photos + videos
└── results/
    ├── my_photos/            # A1 matched photos (copies)
    ├── my_clips/             # A2 sub-clips (re-encoded mp4)
    ├── highlight/
    │   ├── selected_photos/  # B1 curated photos (time-sorted copies)
    │   ├── _slide.mp4        # intermediate
    │   └── highlight.mp4     # final B2 output
    └── map_points.json       # not used currently; map computed on demand
```

---

## Configuration (`src/config.py`)

```python
FACE_SIMILARITY_THRESHOLD = 0.50   # cosine distance; lower = stricter
VIDEO_SAMPLE_FPS = 2               # frames/sec for video scanning
MIN_SEGMENT_DURATION_S = 1.0       # min video segment to emit
MERGE_GAP_S = 5.0                  # max gap to merge consecutive hits
BLUR_THRESHOLD = 100.0             # Laplacian variance; below = blurry
MIN_FACE_SIZE_PX = 40              # min face bounding box dimension
MAX_HIGHLIGHT_PHOTOS = 20          # max photos in slideshow
PHOTO_SLIDE_DURATION_S = 3         # seconds per photo in slideshow
```

---

## Development Setup

```bash
# First-time
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
# First run downloads insightface buffalo_l model (~300 MB to ~/.insightface/)

# Dev server (auto-reload)
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Tests
pytest tests/ -v          # 17 tests, no model download required

# Format
black src/ tests/
```

### External Dependencies
- **ffmpeg** system binary required (`brew install ffmpeg`)
- **insightface** requires cmake (`brew install cmake` before pip install)
- **AMAP_KEY** in `config/.env` — leave empty to disable map (UI degrades gracefully)

---

## Known Limitations (MVP v1)

1. **Video recall depends on reference quality**: A poor-angle or backlit selfie significantly reduces video hits. Provide 2–3 diverse selfies for best results.
2. **No authentication**: Sessions are accessible by anyone with the session ID. For personal/local use only.
3. **Highlight length**: With few photos, the slideshow may be short (< 30s). The `MAX_HIGHLIGHT_DURATION_S` config exists but is not yet used to pad/trim output.
4. **HEIC support**: HEIC files pass the file extension filter but conversion depends on Pillow version. If HEIC photos fail quality check, install `pillow-heif`.
5. **GPS absent**: Many photos lack GPS EXIF. Feature C shows only photos with coordinates. Manual map pin is listed as Layer-2 UI work.
6. **No persistent session**: Data lives on disk; no database. Sessions are not cleaned up automatically.
