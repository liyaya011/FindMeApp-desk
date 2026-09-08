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
    - All Python deps from src/ and PIL/cv2/onnxruntime/scipy/matplotlib/...
"""
import sys
from pathlib import Path

block_cipher = None

# Project root = directory containing this spec file
ROOT = Path(SPECPATH)

# ---------- datas: non-Python files to bundle ----------
datas = [
    # Project source modules
    (str(ROOT / "src"), "src"),
    # Frontend templates/static (harmless if unused in desktop bundle)
    (str(ROOT / "frontend"), "frontend"),
]

# Explicitly add each model file — PyInstaller's recursive dir scan
# doesn't pick up .onnx binaries (they're treated as unknown extensions).
model_root = ROOT / "assets" / "models" / "buffalo_l"
if model_root.exists():
    onnx_files = sorted(model_root.glob("*.onnx"))
    if onnx_files:
        for onnx_file in onnx_files:
            datas.append((str(onnx_file), "assets/models/buffalo_l"))
        total_mb = sum(f.stat().st_size for f in onnx_files) / 1024 / 1024
        print(f"[build.spec] [OK] Added {len(onnx_files)} .onnx files ({total_mb:.0f} MB) from {model_root}")
    else:
        raise RuntimeError(
            f"[build.spec] [ERROR] model_root exists but no .onnx files found in {model_root}!\n"
            f"  Download with: mkdir -p assets/models && python -c "
            f"\"from insightface.utils import ensure_available; ensure_available('models', 'buffalo_l', root='assets')\""
        )
else:
    raise RuntimeError(
        f"[build.spec] [ERROR] model_root not found: {model_root}\n"
        f"  Download with: mkdir -p assets/models && python -c "
        f"\"from insightface.utils import ensure_available; ensure_available('models', 'buffalo_l', root='assets')\""
    )

# tkinterdnd2 ships platform-specific shared libs that PyInstaller doesn't auto-collect
try:
    import tkinterdnd2
    tkdnd_dir = str(Path(tkinterdnd2.__file__).parent)
    datas.append((tkdnd_dir, "tkinterdnd2"))
except ImportError:
    pass

# insightface data files (.pkl templates, mask images) — PyInstaller doesn't
# auto-collect .pkl/.jpg/.png that are loaded at runtime via pkg_resources / pickle
try:
    import insightface
    if_dir = Path(insightface.__file__).parent
    if_data = if_dir / "data"
    if if_data.exists():
        datas.append((str(if_data), "insightface/data"))
        print(f"[build.spec] [OK] Added insightface/data directory")
except ImportError:
    pass

# ---------- hiddenimports: every submodule of key packages ----------
# insightface does deep, dynamic imports that PyInstaller's static analysis
# cannot trace (scipy.special, matplotlib.cm, skimage.measure, etc.).
# Use pkgutil at build time to enumerate EVERY submodule of each package,
# so nothing is missed regardless of how deep the import chain goes.
import pkgutil

def _all_submodules(pkg_name: str) -> list[str]:
    """Return [pkg_name, pkg_name.sub1, pkg_name.sub2, ...] for every submodule.

    Uses filesystem walk instead of pkgutil.walk_packages because some
    packages (e.g. matplotlib) have internal directories that walk_packages
    tries to import and crashes on.
    """
    import os as _os
    result = [pkg_name]
    try:
        pkg = __import__(pkg_name, fromlist=["*"])
        pkg_dir = _os.path.dirname(pkg.__file__)
        pkg_prefix = pkg_name + "."
        for root, dirs, files in _os.walk(pkg_dir):
            # Skip test / benchmark directories — they're not runtime deps
            dirs[:] = [d for d in dirs if d not in ("tests", "test", "benchmarks", "__pycache__")]
            rel_root = _os.path.relpath(root, pkg_dir)
            rel_root = "" if rel_root == "." else rel_root.replace(_os.sep, ".")
            for f in files:
                if f.endswith(".py") and not f.startswith("_"):
                    mod_name = f[:-3]
                    full = pkg_prefix + (rel_root + "." + mod_name if rel_root else mod_name)
                    result.append(full)
                elif f.endswith(".py") and f == "__init__.py":
                    # package init — already covered by the directory walk
                    pass
    except Exception as e:
        print(f"[build.spec] [WARN] Failed to enumerate submodules of {pkg_name}: {e}")
    # De-duplicate and sort
    return sorted(set(result))

# Packages insightface / opencv transitively depend on.
# DO NOT add these to excludes — they WILL be needed at runtime.
_essential_pkgs = [
    "numpy",          # every Python scientific package needs it
    "scipy",          # insightface: spatial.distance, special, ndimage, stats...
    "matplotlib",     # insightface model_zoo: cm, pyplot (skips if headless)
    "skimage",        # insightface: measure, morphology (via albumentations)
    "onnx",           # onnxruntime sometimes needs the onnx protobuf
    "requests",       # insightface utils.download uses it
    "tqdm",           # download progress bars
    "albumentations", # image augmentations (runtime deps of trained models)
]

hiddenimports = [
    "tkinterdnd2",
    "PIL._tkinter_finder",
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
]

for pkg in _essential_pkgs:
    hiddenimports.extend(_all_submodules(pkg))

print(f"[build.spec] hiddenimports: {len(hiddenimports)} entries")

# ---------- excludes: packages we truly don't need ----------
# ONLY exclude things that are definitely NOT imported by insightface/cv2/PIL.
# Matplotlib/scipy/numpy/skimage/requests/tqdm/albumentations are FORBIDDEN here.
_excludes_common = [
    "pandas",
    "pytest",
    "IPython",
    "jupyter",
    "notebook",
    "Cython",          # build-time only
    "pip",             # build-time only
    "mxnet",           # insightface default uses onnx, not mxnet
]

# ---------- macOS build ----------
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
        excludes=_excludes_common,
        win_no_prefer_redirects=False,
        win_private_assemblies=False,
        cipher=block_cipher,
        noarchive=False,
    )
    pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

    exe = EXE(
        pyz, a.scripts, [],
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
        icon=str(ROOT / "assets" / "icon.icns") if (ROOT / "assets" / "icon.icns").exists() else None,
    )

    app = BUNDLE(
        exe, a.binaries, a.zipfiles, a.datas, [],
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
            "CFBundleShortVersionString": "1.0.2",
            "CFBundleVersion": "1.0.2",
            "NSCameraUsageDescription": "FindMeApp 不使用摄像头。",
            "NSPhotoLibraryUsageDescription": "FindMeApp 需要读取照片库以匹配人脸。",
            "LSMinimumSystemVersion": "11.0",
        },
    )

# ---------- Windows build ----------
else:
    a = Analysis(
        ["desktop.py"],
        pathex=[str(ROOT)],
        binaries=[],
        datas=datas,
        hiddenimports=hiddenimports,
        hookspath=[],
        runtime_hooks=[],
        excludes=_excludes_common,
        win_no_prefer_redirects=False,
        win_private_assemblies=False,
        cipher=block_cipher,
        noarchive=False,
    )
    pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

    exe = EXE(
        pyz, a.scripts, [],
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
        exe, a.binaries, a.zipfiles, a.datas,
        strip=False, upx=False, upx_exclude=[],
        name="FindMeApp",
    )
