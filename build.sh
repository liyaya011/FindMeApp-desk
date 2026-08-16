#!/usr/bin/env bash
# Build script for FindMeApp (macOS / Linux)
# Usage:
#   ./build.sh           # Build .app
#   ./build.sh --clean   # Clean build
#   ./build.sh --skip-model  # Skip model bundling (faster testing)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
CLEAN=0
SKIP_MODEL=0

for arg in "$@"; do
    case "$arg" in
        --clean) CLEAN=1 ;;
        --skip-model) SKIP_MODEL=1 ;;
        *) echo "Unknown arg: $arg" >&2; exit 1 ;;
    esac
done

echo "===== FindMeApp macOS Build ====="
echo "Project root: $ROOT"

# --- 1. Verify venv --------------------------------------------------------
if [[ ! -f "$ROOT/.venv/bin/python" ]]; then
    echo "Creating virtual environment..."
    python3 -m venv "$ROOT/.venv"
fi
# shellcheck disable=SC1091
source "$ROOT/.venv/bin/activate"
python -m pip install --upgrade pip >/dev/null

# --- 2. Install deps --------------------------------------------------------
if [[ -f "$ROOT/requirements.txt" ]]; then
    echo "Installing requirements..."
    python -m pip install -r "$ROOT/requirements.txt"
fi

# Ensure PyInstaller is available
if ! python -c "import PyInstaller" 2>/dev/null; then
    python -m pip install pyinstaller
fi

# --- 3. Prepare model files ------------------------------------------------
MODEL_DIR="$ROOT/assets/models/buffalo_l"
if [[ ! -d "$MODEL_DIR" ]]; then
    if [[ "$SKIP_MODEL" -eq 1 ]]; then
        echo "WARNING: Model not found and --skip-model set; .app will require download on first run."
    else
        echo "Downloading insightface buffalo_l model..."
        python -c "from insightface.utils import ensure_available; ensure_available('models', 'buffalo_l', root='$ROOT/assets')"
    fi
else
    echo "Model already present at $MODEL_DIR"
fi

# --- 4. Build ---------------------------------------------------------------
if [[ "$CLEAN" -eq 1 ]]; then
    echo "Cleaning previous build..."
    rm -rf "$ROOT/dist" "$ROOT/build"
fi

echo "Running PyInstaller..."
export PYINSTALLER_CONFIG_DIR="$ROOT/.pyinstaller_cache"
cd "$ROOT"
python -m PyInstaller build.spec --noconfirm

# --- 5. Verify --------------------------------------------------------------
if [[ -d "$ROOT/dist/FindMeApp.app" ]]; then
    SIZE=$(du -sh "$ROOT/dist/FindMeApp.app" | awk '{print $1}')
    echo "Build successful!"
    echo "  Output: $ROOT/dist/FindMeApp.app"
    echo "  Size:   $SIZE"
    ONNX_COUNT=$(find "$ROOT/dist/FindMeApp.app" -name "*.onnx" | wc -l | tr -d ' ')
    echo "  Bundled models: $ONNX_COUNT .onnx files"
    if [[ "$ONNX_COUNT" -lt 5 ]]; then
        echo "  WARNING: Expected at least 5 .onnx files!" >&2
        exit 1
    fi
else
    echo "ERROR: Build output not found: $ROOT/dist/FindMeApp.app" >&2
    exit 1
fi
