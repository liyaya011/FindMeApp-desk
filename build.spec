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
    for onnx_file in sorted(model_root.glob("*.onnx")):
        datas.append((str(onnx_file), "assets/models/buffalo_l"))
    print(f"[build.spec] added {len(list(model_root.glob('*.onnx')))} .onnx files from {model_root}")
else:
    print(f"[build.spec] WARNING: model_root not found: {model_root}")

# tkinterdnd2 ships platform-specific shared libs that PyInstaller doesn't auto-collect
try:
    import tkinterdnd2
    tkdnd_dir = str(Path(tkinterdnd2.__file__).parent)
    datas.append((tkdnd_dir, "tkinterdnd2"))
except ImportError:
    pass

hiddenimports = [
    "tkinterdnd2",
    "PIL._tkinter_finder",  # PIL Tk image support
    "cv2",
    "numpy",
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
            "scipy",
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
            "CFBundleShortVersionString": "1.0.0",
            "CFBundleVersion": "1.0.0",
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
            "scipy",
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
