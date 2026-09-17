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
        try:
            import insightface
        except ImportError:
            # insightface.__init__ 把底层真实错误（如 pyd 找不到某个 DLL 的
            # WinError）统一吞成 "Unable to import dependency onnxruntime."。
            # 这里取出完整异常链并向上抛出，使界面红色提示能直接显示根因。
            import traceback
            detail = traceback.format_exc().strip()
            log.error("insightface/onnxruntime import failed:\n%s", detail)
            diagHint = ""
            if sys.platform == "win32":
                diagHint = "\n诊断日志：%LOCALAPPDATA%\\FindMeApp\\ort_diag.log"
            raise ImportError(
                "人脸引擎加载失败（insightface/onnxruntime 无法导入）。\n"
                f"底层错误：\n{detail}{diagHint}"
            )
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


def detectFaces(imagePath: str, *, applyExif: bool = True) -> dict:
    """
    Detect all faces in imagePath.
    output: list of {"bbox": [x1,y1,x2,y2], "embedding": list[float], "det_score": float}

    applyExif=True  : read image with EXIF Orientation applied (display-correct pixels)
    applyExif=False : read RAW pixels exactly as stored (no EXIF rotation)
    """
    startTime = time.time()
    try:
        img = _readImage(imagePath) if applyExif else _readImageRaw(imagePath)
        if img is None:
            # Determine failure reason for better diagnostics
            pathObj = Path(imagePath)
            if not pathObj.exists():
                errMsg = f"File not found: {imagePath}"
            else:
                errMsg = f"Cannot read image (unsupported format or corrupt): {imagePath} ({pathObj.stat().st_size if pathObj.exists() else 'N/A'} bytes)"
            log.error("detectFaces: %s", errMsg)
            return makeResult(False, error=errMsg, startTime=startTime)

        log.info("detectFaces: img loaded shape=%s dtype=%s path=%s", img.shape, img.dtype, imagePath)
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
            log.warning(
                "detectFaces: no face detected in %s (shape=%s dtype=%s sys.platform=%s frozen=%s)",
                imagePath, img.shape, img.dtype, sys.platform, getattr(sys, "frozen", False),
            )
        else:
            log.info("detectFaces: found %d face(s), top det_score=%.3f", len(faceList),
                     max(f["det_score"] for f in faceList))
        return makeResult(True, output={"faces": faceList, "count": len(faceList)}, startTime=startTime)
    except Exception as e:
        log.exception("detectFaces failed: %s", imagePath)
        return makeResult(False, error=str(e), startTime=startTime)


def _readImageRaw(imagePath: str):
    """
    Read image file WITHOUT applying EXIF Orientation — raw pixels as stored.
    Used by the dual-path matcher: try raw pixels first, then EXIF-rotated.

    Uses cv2.imdecode(np.fromfile(...)) instead of cv2.imread() because:
      - cv2.imread silently fails on Windows when the path contains
        non-ASCII characters (Chinese, Japanese, etc.)
      - np.fromfile + cv2.imdecode always works — it reads raw bytes
        then lets OpenCV decode them, regardless of path encoding
    """
    ext = Path(imagePath).suffix.lower()

    # Try OpenCV first (covers JPG/PNG/BMP/TIFF/WEBP/...)
    try:
        data = np.fromfile(str(imagePath), dtype=np.uint8)
        if data.size == 0:
            return None
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        if img is not None:
            return img
    except Exception as e:
        log.warning("_readImageRaw: cv2.imdecode failed for %s: %s", imagePath, e)

    # OpenCV couldn't handle it — try Pillow for formats like HEIC
    if ext in (".heic", ".heif"):
        try:
            from PIL import Image as PILImage
            with PILImage.open(imagePath) as pilImg:
                arr = np.array(pilImg.convert("RGB"))
                img = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
            log.info("_readImageRaw: loaded HEIC via Pillow+heif → shape=%s", img.shape)
            return img
        except ImportError:
            log.error("_readImageRaw: HEIC file but pillow-heif not installed: %s", imagePath)
        except Exception as e:
            log.error("_readImageRaw: HEIC decode failed for %s: %s", imagePath, e)
    return None


def _readImage(imagePath: str):
    """
    Read an image file robustly across platforms, with EXIF Orientation applied
    so pixels are display-correct (upright).
    """
    img = _readImageRaw(imagePath)
    if img is None:
        return None
    # cv2.imdecode ignores EXIF orientation, but most photo viewers apply it on
    # display, so the user sees an upright image while the raw pixels may still
    # be rotated (phone cameras commonly store portrait shots as landscape with
    # Orientation=6). Without this, buffalo_l sees a sideways face and returns
    # 0 detections.
    return _applyExifOrientation(imagePath, img)


def _applyExifOrientation(imagePath: str, img) -> "np.ndarray":
    """
    Apply JPEG/PNG EXIF Orientation tag to the BGR image.
    cv2.imdecode ignores EXIF orientation, but most photo viewers apply it on
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
            log.info("_applyExifOrientation: no EXIF data for %s", Path(imagePath).name)
            return img
        _orient = _exif.get(0x0112)  # 274 = Orientation tag id
        if not _orient or _orient == 1:
            log.info("_applyExifOrientation: orientation=%s (no-op) for %s", _orient, Path(imagePath).name)
            return img
        log.info("_applyExifOrientation: applying orientation=%s fix for %s", _orient, Path(imagePath).name)
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
        log.warning("_applyExifOrientation: %s (%s) for %s — returning unrotated image",
                    type(e).__name__, e, Path(imagePath).name)
    return img
