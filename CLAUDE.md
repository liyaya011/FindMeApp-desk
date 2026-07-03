# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What FindMeApp Does

FindMeApp is a personal photo/video curation tool. Users upload 1–3 reference selfies and a batch of photos/videos; the app automatically identifies media containing the user, builds highlight reels, and generates a GPS travel-memory map.

Three feature modules:
- **A – Find Me**: identify which photos/videos contain the user (insightface face matching)
- **B – Highlight**: select the best photos and auto-generate a short video
- **C – Travel Memory**: extract GPS/EXIF, plot a chronological map (Gaode JS API)

## Architecture: Agent / Playbook / Script

```
src/
├── agent/        # high-level goal coordination (future)
├── playbooks/    # orchestration logic per feature workflow
│   ├── findPhotos.py    # A1: photo → face-match pipeline
│   ├── findVideos.py    # A2: video → frame-sample → face-match → clip
│   ├── buildHighlight.py # B: dedup + quality-filter + ffmpeg assemble
│   └── travelMap.py     # C: EXIF extract + map point list
├── scripts/      # atomic, idempotent execution units
│   ├── faceDetect.py    # detect faces, return embeddings
│   ├── faceMatch.py     # cosine-distance match against references
│   ├── videoSample.py   # ffmpeg/OpenCV frame extraction
│   ├── videoClip.py     # ffmpeg cut sub-clips
│   ├── photoQuality.py  # blur (Laplacian) + face-size check
│   ├── photoDedupe.py   # pHash / dHash dedup
│   ├── exifExtract.py   # GPS + datetime from EXIF
│   └── videoMerge.py    # ffmpeg concat + slideshow render
└── utils/
    ├── logger.py        # structured logging helper
    └── result.py        # standardized result envelope
```

All scripts return a `ScriptResult` dict:
```python
{"success": bool, "output": any, "error": str | None, "elapsed_s": float}
```

Scripts must be idempotent and support timeouts. Playbooks declare `inputs`, `outputs`, and `success_criteria`.

## Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Run dev server (reload on change)
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Run a single test
pytest tests/test_faceDetect.py -v

# Run all tests
pytest tests/ -v

# Format
black src/ tests/

# Check types
mypy src/
```

First run downloads the insightface `buffalo_l` model (~300 MB) into `~/.insightface/`.

## Tech Stack

| Layer | Technology |
|---|---|
| Web API | FastAPI + Uvicorn |
| Face recognition | insightface (buffalo_l) + onnxruntime |
| Video I/O | OpenCV + ffmpeg (system binary) |
| Image quality | Pillow, imagehash |
| EXIF | exifread |
| Frontend map | Gaode Maps JS API |
| Tests | Pytest |
| Formatting | Black |
| Container | Docker |

## Key Dependencies & Gotchas

- **ffmpeg** must be installed as a system binary (`brew install ffmpeg` / `apt install ffmpeg`).
- **insightface** requires cmake (`pip install cmake` or system package) before pip install.
- **onnxruntime-gpu** can replace `onnxruntime` if CUDA is available; change in `requirements.txt`.
- Gaode Maps API key goes in `config/.env` as `AMAP_KEY=<your_key>` — register at [lbs.amap.com](https://lbs.amap.com).
- Many photos lack GPS EXIF; Feature C must tolerate missing coordinates (manual pin fallback in UI).

## Session Data Layout

```
data/sessions/{session_id}/
├── references/   # uploaded reference selfies
├── media/        # uploaded photos + videos
├── results/
│   ├── my_photos/      # matched photos (A1)
│   ├── my_clips/       # matched video sub-clips (A2)
│   ├── highlight/      # generated highlight video (B)
│   └── map_points.json # GPS points with photo refs (C)
└── session.json  # state: status, file lists, result paths
```

## Code Style

- **Languages**: Python (primary) and C++
- **Indentation**: 4 spaces
- **Naming**: camelCase for all functions, variables, class attributes
- **Comments**: English only

## Communication Convention

When providing code changes, only show the changed sections with diff format or line-number references (e.g. `[Line 42-45]`).
