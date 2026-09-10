"""
faceDetect.py — detect all faces in an image and return embeddings.
Singleton model load; buffalo_l downloads on first run (~300 MB).
"""
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

from src.utils.logger import getLogger
from src.utils.result import makeResult

log = getLogger(__name__)

_app = None  # insightface FaceAnalysis singleton


def _resolveModelRoot():
    """
    Locate the buffalo_l model root for insightface.
    insightface looks for `<root>/models/buffalo_l/*.onnx`.
    Priority:
      1. INSIGHTFACE_HOME env var
      2. PyInstaller _MEIPASS bundled assets (returns <_MEIPASS>/assets)
      3. Default ~/.insightface (will auto-download on first use)

    In frozen (packaged) mode, missing bundled models is treated as fatal
    because PyInstaller should have included them at build time.
    """
    envHome = os.environ.get("INSIGHTFACE_HOME")
    if envHome:
        candidate = Path(envHome) / "models" / "buffalo_l"
        if candidate.exists() and any(candidate.glob("*.onnx")):
            return envHome
    if getattr(sys, "frozen", False):
        # Running inside PyInstaller bundle: <_MEIPASS>/assets/models/buffalo_l/*.onnx
        # insightface expects <root>/models/buffalo_l/, so return <_MEIPASS>/assets
        bundled = Path(sys._MEIPASS) / "assets" / "models" / "buffalo_l"
        if bundled.exists() and any(bundled.glob("*.onnx")):
            return str(Path(sys._MEIPASS) / "assets")
        # Frozen but no bundled model — this is a build-time mistake, not a recoverable one
        onnx_count = len(list(bundled.glob("*.onnx"))) if bundled.exists() else 0
        raise RuntimeError(
            f"Packaged build is missing insightface models!\n"
            f"  Expected: {bundled} (exists={bundled.exists()}, onnx_count={onnx_count})\n"
            f"  This means the PyInstaller build didn't include the .onnx files.\n"
            f"  Please rebuild with a complete buffalo_l model directory."
        )
    return "~/.insightface"


def _getApp():
    global _app
    if _app is None:
        import insightface
        modelRoot = _resolveModelRoot()
        log.info("loading insightface buffalo_l from root=%s", modelRoot)
        _app = insightface.app.FaceAnalysis(
            name="buffalo_l",
            root=modelRoot,
            providers=["CPUExecutionProvider"],
        )
        _app.prepare(ctx_id=0, det_size=(640, 640), det_thresh=0.3)
        log.info("insightface buffalo_l model loaded")
    return _app


def detectFaces(imagePath: str) -> dict:
    """
    Detect all faces in imagePath.
    output: list of {"bbox": [x1,y1,x2,y2], "embedding": list[float], "det_score": float}
    """
    startTime = time.time()
    try:
        img = _readImage(imagePath)
        if img is None:
            # Determine failure reason for better diagnostics
            pathObj = Path(imagePath)
            if not pathObj.exists():
                errMsg = f"File not found: {imagePath}"
            else:
                errMsg = f"Cannot read image (unsupported format or corrupt): {imagePath} ({pathObj.stat().st_size if pathObj.exists() else 'N/A'} bytes)"
            log.error("detectFaces: %s", errMsg)
            return makeResult(False, error=errMsg, startTime=startTime)

        faces = _getApp().get(img)
        faceList = [
            {
                "bbox": face.bbox.tolist(),
                "embedding": face.embedding.tolist(),
                "det_score": float(face.det_score),
            }
            for face in faces
        ]
        if not faceList:
            log.warning("detectFaces: no face detected in %s (image shape=%s)", imagePath, img.shape)
        return makeResult(True, output={"faces": faceList, "count": len(faceList)}, startTime=startTime)
    except Exception as e:
        log.exception("detectFaces failed: %s", imagePath)
        return makeResult(False, error=str(e), startTime=startTime)


def _readImage(imagePath: str):
    """Read an image file, with HEIC fallback via Pillow + pillow-heif."""
    img = cv2.imread(str(imagePath))
    if img is not None:
        # cv2.imread does NOT honor EXIF Orientation. Most photo viewers do
        # (Windows Photos, macOS Preview), so the user sees an upright image
        # while the raw pixels may still be rotated (phone cameras commonly
        # store portrait shots as landscape with Orientation=6).
        # Without this, buffalo_l sees a sideways face and returns 0 detections.
        return _applyExifOrientation(imagePath, img)
    # cv2.imread failed — try Pillow for formats like HEIC that OpenCV can't read
    ext = Path(imagePath).suffix.lower()
    if ext in (".heic", ".heif"):
        try:
            from PIL import Image as PILImage
            # pillow-heif must be installed; if missing, PIL will also fail on HEIC
            with PILImage.open(imagePath) as pilImg:
                # Convert Pillow RGB → BGR for OpenCV compatibility
                import numpy as np
                arr = np.array(pilImg.convert("RGB"))
                img = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            log.info("_readImage: loaded HEIC via Pillow+heif → shape=%s", img.shape)
            return img
        except ImportError:
            log.error("_readImage: HEIC file but pillow-heif not installed: %s", imagePath)
        except Exception as e:
            log.error("_readImage: HEIC decode failed for %s: %s", imagePath, e)
    return None


def _applyExifOrientation(imagePath: str, img) -> "np.ndarray":
    """
    Apply JPEG EXIF Orientation tag to the BGR image.
    cv2.imread ignores EXIF orientation, but most photo viewers apply it on
    display, so the user sees an upright face while the raw pixels may be
    rotated 90/180/270°. Feeding those raw pixels to buffalo_l → 0 detections.

    EXIF orientation values (TIFF spec) — value tells the viewer how to ROTATE
    the raw pixels to display them upright; we apply the inverse transform:
        1 = Horizontal (normal)                no transform
        2 = Mirror horizontal                  flip LR
        3 = Rotate 180°                        rotate 180
        4 = Mirror vertical                    flip TB
        5 = Mirror horizontal + rot 270 CW     flip LR + rot 90 CCW
        6 = Rotate 90° CCW (raw → upright)     rotate 90 CW   (most common from phones)
        7 = Mirror horizontal + rot 90 CCW     flip LR + rot 90 CW
        8 = Rotate 90° CW                      rotate 90 CCW
    """
    try:
        from PIL import Image as _PILImage
        with _PILImage.open(imagePath) as _pil:
            _exif = _pil.getexif()
        if not _exif:
            return img
        _orient = _exif.get(0x0112)  # 274 = Orientation tag id
        if not _orient or _orient == 1:
            return img
        if _orient == 2:
            return cv2.flip(img, 1)
        if _orient == 3:
            return cv2.rotate(img, cv2.ROTATE_180)
        if _orient == 4:
            return cv2.flip(img, 0)
        if _orient == 5:
            img = cv2.flip(img, 1)
            return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
        if _orient == 6:
            return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        if _orient == 7:
            img = cv2.flip(img, 1)
            return cv2.rotate(img, cv2.ROTATE_90_CLOCKWISE)
        if _orient == 8:
            return cv2.rotate(img, cv2.ROTATE_90_COUNTERCLOCKWISE)
    except Exception as e:
        log.debug("_applyExifOrientation: %s (%s) for %s", type(e).__name__, e, imagePath)
    return img
