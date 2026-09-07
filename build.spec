# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for FindMeApp desktop.

Build:
    pyinstaller build.spec --clean --noconfirm

Output:
    dist/FindMeApp.app              (macOS)
    dist/FindMeApp/FindMeApp.exe    (Windows)

Bundles:
    - insightface buffalo_l model (~325MB) under assets/models/buffalo_l/
    - tkinterdnd2 shared libraries (platform-specific tcl/tk dnD lib)
    - All Python deps from src/ and PIL/cv2/onnxruntime
"""
import sys
from pathlib import Path

block_cipher = None

# Project root = directory containing this spec file
ROOT = Path(SPECPATH)
ASSETS_MODELS = str(ROOT / "assets" / "models")

datas = [
    # Project source modules
    (str(ROOT / "src"), "src"),
    # Frontend templates/static (used by web routes; harmless if unused in desktop bundle)
    (str(ROOT / "frontend"), "frontend"),
]

# Explicitly add each model file — PyInstaller's recursive directory scan doesn't pick up .onnx binaries.
model_root = ROOT / "assets" / "models" / "buffalo_l"
if model_root.exists():
    onnx_files = sorted(model_root.glob("*.onnx"))
    if onnx_files:
        for onnx_file in onnx_files:
            datas.append((str(onnx_file), "assets/models/buffalo_l"))
        total_mb = sum(f.stat().st_size for f in onnx_files) / 1024 / 1024
        print(f"[build.spec] ✅ Added {len(onnx_files)} .onnx files ({total_mb:.0f} MB) from {model_root}")
    else:
        raise RuntimeError(
            f"[build.spec] ❌ CRITICAL: model_root exists but no .onnx files found in {model_root}!\n"
            f"  You must download the buffalo_l model before building.\n"
            f"  Run: mkdir -p assets/models && python -c \"from insightface.utils import ensure_available; ensure_available('models', 'buffalo_l', root='assets')\""
        )
else:
    raise RuntimeError(
        f"[build.spec] ❌ CRITICAL: model_root not found: {model_root}\n"
        f"  You must download the buffalo_l model before building.\n"
        f"  Run: mkdir -p assets/models && python -c \"from insightface.utils import ensure_available; ensure_available('models', 'buffalo_l', root='assets')\""
    )

# tkinterdnd2 ships platform-specific shared libs that PyInstaller doesn't auto-collect
try:
    import tkinterdnd2
    tkdnd_dir = str(Path(tkinterdnd2.__file__).parent)
    datas.append((tkdnd_dir, "tkinterdnd2"))
except ImportError:
    pass

# Auto-discover ALL scipy submodules — insightface pulls scipy.special,
# scipy.spatial.distance, scipy.ndimage, scipy.stats, etc. via deep imports
# that PyInstaller's static analysis can't see. Must list every submodule explicitly.
_all_scipy = ["scipy"]
_all_numpy = ["numpy"]
try:
    import scipy, numpy, pkgutil
    _all_scipy += sorted(f"scipy.{m.name}" for m in pkgutil.iter_modules(scipy.__path__))
    _all_numpy += sorted(f"numpy.{m.name}" for m in pkgutil.iter_modules(numpy.__path__))
except Exception:
    pass

hiddenimports = [
    "tkinterdnd2",
    "PIL._tkinter_finder",  # PIL Tk image support
    "cv2",
    "onnxruntime",
    "insightface",
    "insightface.app",
    "insightface.model_zoo",
    "insightface.utils",
    "exifread",
    "imageio_ffmpeg",
    "src",
    "src.playbooks",
    "src.scripts",
    "src.utils",
] + _all_numpy + _all_scipy
print(f"[build.spec] hiddenimports: {len(hiddenimports)} entries "
      f"(numpy={len(_all_numpy)}, scipy={len(_all_scipy)})")

# --- macOS-specific ---------------------------------------------------------
if sys.platform == "darwin":
    binaries = []
    a = Analysis(
        ["desktop.py"],
        pathex=[str(ROOT)],
        binaries=binaries,
        datas=datas,
        hiddenimports=hiddenimports,
        hookspath=[],
        runtime_hooks=[],
        excludes=[
            "matplotlib",
            "pandas",
            "pytest",
            "IPython",
            "jupyter",
            "notebook",
        ],
        win_no_prefer_redirects=False,
        win_private_assemblies=False,
        cipher=block_cipher,
        noarchive=False,
    )
    pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="FindMeApp",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,  # .app bundle: no terminal window
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(ROOT / "assets" / "icon.icns") if (ROOT / "assets" / "icon.icns").exists() else None,
    )

    app = BUNDLE(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name="FindMeApp.app",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        runtime_hooks=[],
        console=False,
        icon=str(ROOT / "assets" / "icon.icns") if (ROOT / "assets" / "icon.icns").exists() else None,
        bundle_identifier="com.findmeapp.desktop",
        info_plist={
            "CFBundleDisplayName": "FindMeApp",
            "CFBundleName": "FindMeApp",
            "CFBundleShortVersionString": "1.0.1",
            "CFBundleVersion": "1.0.1",
            "NSCameraUsageDescription": "FindMeApp 不使用摄像头。",
            "NSPhotoLibraryUsageDescription": "FindMeApp 需要读取照片库以匹配人脸。",
            "LSMinimumSystemVersion": "11.0",
        },
    )

# --- Windows-specific ------------------------------------------------------
else:
    a = Analysis(
        ["desktop.py"],
        pathex=[str(ROOT)],
        binaries=[],
        datas=datas,
        hiddenimports=hiddenimports,
        hookspath=[],
        runtime_hooks=[],
        excludes=[
            "matplotlib",
            "pandas",
            "pytest",
            "IPython",
            "jupyter",
            "notebook",
        ],
        win_no_prefer_redirects=False,
        win_private_assemblies=False,
        cipher=block_cipher,
        noarchive=False,
    )
    pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name="FindMeApp",
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=False,
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=str(ROOT / "assets" / "icon.ico") if (ROOT / "assets" / "icon.ico").exists() else None,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=False,
        upx_exclude=[],
        name="FindMeApp",
    )
