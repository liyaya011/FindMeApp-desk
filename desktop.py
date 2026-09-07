#!/usr/bin/env python3
"""FindMeApp desktop entrypoint."""

import json
import logging
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox, ttk
from uuid import uuid4

# --- File logging (critical for packaged builds where console=False) ----------
def _setupLogging():
    """Write ALL logs (including uncaught exceptions) to DATA_DIR/app.log."""
    from src.config import DATA_DIR as _DATA_DIR
    try:
        _DATA_DIR.mkdir(parents=True, exist_ok=True)
        _logPath = _DATA_DIR / "app.log"
        # 10 MB rotation, keep 3 backups
        _handler = logging.handlers.RotatingFileHandler(
            str(_logPath), maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        _handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s — %(message)s"
        ))
        logging.basicConfig(
            level=logging.INFO,
            handlers=[_handler, logging.StreamHandler(sys.stderr)],
        )
        # Also forward uncaught exceptions to the log file
        def _excepthook(excType, excValue, excTb):
            logging.critical("Uncaught exception", exc_info=(excType, excValue, excTb))
        sys.excepthook = _excepthook
        logging.info("FindMeApp starting (frozen=%s, python=%s)",
                     getattr(sys, "frozen", False), sys.version)
    except Exception as e:
        # If logging setup fails, don't crash the app
        print(f"[WARN] failed to setup file logging: {e}", file=sys.stderr)

import logging.handlers
_setupLogging()
# -----------------------------------------------------------------------------

try:
    import cv2
except ImportError:
    cv2 = None

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = None
    TkinterDnD = None

from PIL import Image, ImageTk

from src.config import DATA_DIR
from src.utils.ffmpeg import getFfmpegPath

# ffmpeg is a system binary required by video clipping (A2) and highlight rendering (B).
# Detect at startup so we can gracefully disable those features when missing.
ffmpegAvailable = getFfmpegPath() is not None
from src.playbooks.buildHighlight import runBuildHighlight
from src.playbooks.findPhotos import runFindPhotos
from src.playbooks.findVideos import runFindVideos
from src.playbooks.travelMap import runTravelMap

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}

SIDEBAR_BG = "#1E2035"
MAIN_BG = "#12131F"
TOPBAR_BG = "#171829"
NAV_HOVER_BG = "#272944"
NAV_ACTIVE_BG = "#3B3E7A"
PANEL_BG = "#22243B"
PANEL_ALT_BG = "#1A1C30"
SECTION_LINE = "#2C2E47"
TEXT_COLOR = "#FFFFFF"
MUTED_TEXT_COLOR = "#A9AFC7"
SUBTLE_TEXT_COLOR = "#9198B8"
PLACEHOLDER_TEXT_COLOR = "#848BB0"
NAV_TEXT_COLOR = "#C9CDDF"
PRIMARY_COLOR = "#6C5CE7"
PRIMARY_HOVER_COLOR = "#8070ED"
SECONDARY_DASH_COLOR = "#3A3C52"
PRIMARY_DISABLED_BG = "#474075"
LIGHT_PANEL_BG = "#DCE4FF"
LIGHT_PANEL_BORDER = "#C5D1FF"
LIGHT_PANEL_TEXT = "#10254C"
SUCCESS_COLOR = "#57C084"
ERROR_COLOR = "#F07A7A"
PROCESSING_COLOR = PRIMARY_COLOR
PHOTO_THUMB_SIZE = 136
REFERENCE_THUMB_SIZE = 84
VIDEO_PREVIEW_SIZE = (980, 540)
STATUS_COLORS = {
    "idle": MUTED_TEXT_COLOR,
    "processing": PROCESSING_COLOR,
    "done": SUCCESS_COLOR,
    "error": ERROR_COLOR,
}
PAGE_META = {
    "setup": {
        "title": "上传素材",
        "subtitle": "上传 1-3 张本人参考自拍，再上传要搜索的照片和视频。",
    },
    "find": {
        "title": "找我 - 识别结果",
        "subtitle": "以下是包含你本人的照片和视频片段，点击照片可放大查看。",
    },
    "highlight": {
        "title": "一键成片",
        "subtitle": "从匹配的照片和视频片段自动生成高光短视频。",
    },
    "travel": {
        "title": "轨迹回忆",
        "subtitle": "按时间顺序展示照片拍摄地点，点击照片可放大查看，点击地图按钮在浏览器中查看位置。",
    },
}


@dataclass
class AppState:
    referencePaths: list[Path] = field(default_factory=list)
    mediaPaths: list[Path] = field(default_factory=list)
    photoPaths: list[Path] = field(default_factory=list)
    videoPaths: list[Path] = field(default_factory=list)
    sessionId: str | None = None
    sessionRoot: Path | None = None
    resultsRoot: Path | None = None
    status: str = "idle"
    highlightStatus: str = "idle"
    travelStatus: str = "idle"
    results: dict = field(default_factory=lambda: {"photos": None, "videos": None, "highlight": None, "travel": None})
    error: str | None = None


appState = AppState()
previewWindow: tk.Toplevel | None = None
previewImageRef: ImageTk.PhotoImage | None = None
videoPreviewRef: ImageTk.PhotoImage | None = None
referencePreviewRefs: list[ImageTk.PhotoImage] = []
photoPreviewRefs: list[ImageTk.PhotoImage] = []
videoCapture = None
videoPlaying = False
videoTotalFrames = 0
videoFps = 0.0
statusTone = "idle"
currentPage = "setup"
navWidgets: dict[str, dict[str, tk.Widget]] = {}
pageFrames: dict[str, tk.Frame] = {}

root = TkinterDnD.Tk() if TkinterDnD is not None else tk.Tk()
root.title("FindMeApp")
root.geometry("1920x1080")
root.minsize(1400, 800)
root.configure(bg=MAIN_BG)
root.resizable(True, True)

availableFonts = set(tkfont.families(root))
for candidate in ("Microsoft YaHei", "PingFang SC", "Helvetica Neue", "Helvetica"):
    if candidate in availableFonts:
        FONT_FAMILY = candidate
        break
else:
    FONT_FAMILY = "TkDefaultFont"

statusVar = tk.StringVar(value="请选择参考自拍和待搜索素材。")
headerTitleVar = tk.StringVar(value=PAGE_META[currentPage]["title"])
headerSubtitleVar = tk.StringVar(value=PAGE_META[currentPage]["subtitle"])
refsSummaryVar = tk.StringVar(value="参考自拍: 0 张")
mediaSummaryVar = tk.StringVar(value="素材文件: 0 个")
mediaTypeSummaryVar = tk.StringVar(value="照片 0 / 视频 0")
sessionVar = tk.StringVar(value="桌面会话: -")
resultsDirVar = tk.StringVar(value="结果文件夹: -")
matchedVar = tk.StringVar(value="识别结果: 照片 0 张，视频片段 0 个")
findButtonHintVar = tk.StringVar(value="请先完成两步上传后再开始识别。")
photoStatVar = tk.StringVar(value='请先完成"开始识别"。')
clipStatVar = tk.StringVar(value='请先完成"开始识别"。')
highlightVar = tk.StringVar(value="高光视频将在识别完成后生成。")
videoProgressVar = tk.DoubleVar(value=0.0)
videoProgressTextVar = tk.StringVar(value="00:00 / 00:00")
travelStatVar = tk.StringVar(value='请先完成"开始识别"后加载轨迹数据。')
travelSummaryVar = tk.StringVar(value="共 0 个点位，0 个缺少 GPS")
travelHintVar = tk.StringVar(value="识别完成后可加载轨迹数据。")
travelPreviewRefs: list[ImageTk.PhotoImage] = []


def getMatchedPhotoPaths() -> list[Path]:
    photoResult = appState.results.get("photos") or {}
    if not photoResult.get("success"):
        return []
    return [Path(path) for path in photoResult.get("output", {}).get("matched_paths", [])]


def getMatchedClips() -> list[dict]:
    videoResult = appState.results.get("videos") or {}
    if not videoResult.get("success"):
        return []

    clipItems = []
    for videoEntry in videoResult.get("output", {}).get("videos", []):
        sourceVideo = Path(videoEntry.get("video", "")).name
        for clip in videoEntry.get("clips", []):
            clipPath = Path(clip["path"])
            duration = max(0.0, clip["end_s"] - clip["start_s"])
            clipItems.append(
                {
                    "path": clipPath,
                    "video": sourceVideo,
                    "start_s": clip["start_s"],
                    "end_s": clip["end_s"],
                    "duration_s": duration,
                    "badge": clipPath.suffix.replace(".", "").upper() or "CLIP",
                }
            )
    return clipItems


def getMatchedClipPaths() -> list[str]:
    return [str(item["path"]) for item in getMatchedClips()]


def getHighlightPath() -> Path | None:
    highlightResult = appState.results.get("highlight") or {}
    if not highlightResult.get("success"):
        return None
    videoPath = highlightResult.get("output", {}).get("highlight_video_path")
    return Path(videoPath) if videoPath else None


def getTravelPhotos() -> list[str]:
    """Prefer B1 curated photos; fall back to raw A1 matches (mirrors routes.py logic)."""
    highlightResult = appState.results.get("highlight") or {}
    if highlightResult.get("success"):
        selected = highlightResult.get("output", {}).get("selected_photos") or []
        if selected:
            return selected
    photoResult = appState.results.get("photos") or {}
    if photoResult.get("success"):
        return photoResult.get("output", {}).get("matched_paths", []) or []
    return []


def getTravelMapPoints() -> list[dict]:
    travelResult = appState.results.get("travel") or {}
    if not travelResult.get("success"):
        return []
    return travelResult.get("output", {}).get("map_points", []) or []


def hasHighlightInputs() -> bool:
    return bool(getMatchedPhotoPaths() or getMatchedClips())


def formatSeconds(value: float) -> str:
    return f"{value:.1f}s"


def formatClock(value: float) -> str:
    totalSeconds = max(0, int(value))
    minutes, seconds = divmod(totalSeconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def sortPaths(paths: list[Path]) -> list[Path]:
    unique: dict[str, Path] = {}
    for path in paths:
        unique[str(path)] = path
    return sorted(unique.values(), key=lambda item: str(item).lower())


def collectMediaFiles(paths: list[Path]) -> tuple[list[Path], list[Path], list[Path]]:
    photoPaths: list[Path] = []
    videoPaths: list[Path] = []

    for path in paths:
        if not path.exists():
            continue
        if path.is_dir():
            for child in path.rglob("*"):
                if not child.is_file():
                    continue
                suffix = child.suffix.lower()
                if suffix in PHOTO_EXTS:
                    photoPaths.append(child)
                elif suffix in VIDEO_EXTS:
                    videoPaths.append(child)
            continue

        suffix = path.suffix.lower()
        if suffix in PHOTO_EXTS:
            photoPaths.append(path)
        elif suffix in VIDEO_EXTS:
            videoPaths.append(path)

    photoPaths = sortPaths(photoPaths)
    videoPaths = sortPaths(videoPaths)
    return photoPaths, videoPaths, sortPaths(photoPaths + videoPaths)


def ensureDesktopSession() -> Path:
    if appState.sessionRoot and appState.resultsRoot:
        appState.sessionRoot.mkdir(parents=True, exist_ok=True)
        appState.resultsRoot.mkdir(parents=True, exist_ok=True)
        return appState.sessionRoot

    sessionId = f"desk-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}"
    sessionRoot = DATA_DIR / "sessions" / sessionId
    resultsRoot = sessionRoot / "results"
    for directory in [sessionRoot, sessionRoot / "references", sessionRoot / "media", resultsRoot]:
        directory.mkdir(parents=True, exist_ok=True)

    appState.sessionId = sessionId
    appState.sessionRoot = sessionRoot
    appState.resultsRoot = resultsRoot
    return sessionRoot


def getResultsRoot() -> Path:
    ensureDesktopSession()
    if appState.resultsRoot is None:
        raise RuntimeError("结果文件夹未初始化")
    appState.resultsRoot.mkdir(parents=True, exist_ok=True)
    return appState.resultsRoot


def sessionStatePayload() -> dict:
    return {
        "session_id": appState.sessionId,
        "status": appState.status,
        "highlight_status": appState.highlightStatus,
        "travel_status": appState.travelStatus,
        "reference_paths": [str(path) for path in appState.referencePaths],
        "media_paths": [str(path) for path in appState.mediaPaths],
        "results": appState.results,
        "error": appState.error,
    }


def writeSessionState():
    sessionRoot = ensureDesktopSession()
    sessionFile = sessionRoot / "session.json"
    sessionFile.write_text(json.dumps(sessionStatePayload(), ensure_ascii=False, indent=2), encoding="utf-8")


def loadLatestSessionState():
    sessionsRoot = DATA_DIR / "sessions"
    if not sessionsRoot.exists():
        return

    sessionFiles = sorted(sessionsRoot.glob("desk-*/session.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    if not sessionFiles:
        return

    sessionFile = sessionFiles[0]
    try:
        payload = json.loads(sessionFile.read_text(encoding="utf-8"))
    except Exception:
        return

    sessionRoot = sessionFile.parent
    appState.sessionId = payload.get("session_id") or sessionRoot.name
    appState.sessionRoot = sessionRoot
    appState.resultsRoot = sessionRoot / "results"
    appState.referencePaths = [Path(path) for path in payload.get("reference_paths", []) if Path(path).exists()]
    mediaPaths = [Path(path) for path in payload.get("media_paths", []) if Path(path).exists()]
    photoPaths, videoPaths, mediaPaths = collectMediaFiles(mediaPaths)
    appState.mediaPaths = mediaPaths
    appState.photoPaths = photoPaths
    appState.videoPaths = videoPaths
    appState.status = payload.get("status", "idle")
    appState.highlightStatus = payload.get("highlight_status", "idle")
    appState.travelStatus = payload.get("travel_status", "idle")
    appState.results = payload.get("results") or {"photos": None, "videos": None, "highlight": None, "travel": None}
    appState.error = payload.get("error")


#loadLatestSessionState()


def renderIcon(canvas, name, x0, y0, x1, y1, color, width=2):
    """Draw a simple linear (outline) icon inside the given bounding box."""
    boxW = x1 - x0
    boxH = y1 - y0

    def px(fx):
        return x0 + fx * boxW

    def py(fy):
        return y0 + fy * boxH

    line = {"fill": color, "width": width, "capstyle": "round", "joinstyle": "round"}

    if name == "home":
        canvas.create_line(px(0.12), py(0.52), px(0.5), py(0.14), px(0.88), py(0.52), **line)
        canvas.create_line(
            px(0.22), py(0.46), px(0.22), py(0.86), px(0.78), py(0.86), px(0.78), py(0.46), **line
        )
        canvas.create_line(px(0.42), py(0.86), px(0.42), py(0.62), px(0.58), py(0.62), px(0.58), py(0.86), **line)
    elif name == "search":
        canvas.create_oval(px(0.16), py(0.16), px(0.66), py(0.66), outline=color, width=width)
        canvas.create_line(px(0.62), py(0.62), px(0.88), py(0.88), **line)
    elif name == "clapper":
        canvas.create_rectangle(px(0.12), py(0.44), px(0.88), py(0.86), outline=color, width=width)
        canvas.create_rectangle(px(0.12), py(0.22), px(0.88), py(0.44), outline=color, width=width)
        for fx in (0.30, 0.52, 0.74):
            canvas.create_line(px(fx - 0.08), py(0.44), px(fx), py(0.22), **line)
    elif name == "mountain":
        canvas.create_oval(px(0.62), py(0.16), px(0.80), py(0.34), outline=color, width=width)
        canvas.create_line(
            px(0.10), py(0.84), px(0.34), py(0.44), px(0.50), py(0.64), px(0.66), py(0.40), px(0.90), py(0.84), **line
        )
    elif name == "camera":
        canvas.create_rectangle(px(0.10), py(0.34), px(0.90), py(0.82), outline=color, width=width)
        canvas.create_line(px(0.34), py(0.34), px(0.40), py(0.24), px(0.60), py(0.24), px(0.66), py(0.34), **line)
        canvas.create_oval(px(0.38), py(0.46), px(0.62), py(0.70), outline=color, width=width)
    elif name == "folder":
        canvas.create_line(
            px(0.12), py(0.80), px(0.12), py(0.34), px(0.40), py(0.34), px(0.48), py(0.44),
            px(0.88), py(0.44), px(0.88), py(0.80), px(0.12), py(0.80), **line
        )


class RoundedButton:
    """Canvas-based button with rounded corners, an optional linear icon, and three visual states."""

    def __init__(self, parent, text, command, *, primary=True, icon=None, width=None, height=42, radius=8):
        self.command = command
        self.primary = primary
        self.icon = icon
        self.text = text
        self.enabled = True
        self.radius = radius
        self.height = height
        self.font = tkfont.Font(family=FONT_FAMILY, size=11, weight="bold")

        self.normalBg = PRIMARY_COLOR if primary else PANEL_ALT_BG
        self.normalFg = TEXT_COLOR if primary else NAV_TEXT_COLOR
        self.hoverBg = PRIMARY_HOVER_COLOR if primary else "#262945"
        self.hoverFg = TEXT_COLOR
        self.disabledBg = PRIMARY_DISABLED_BG if primary else "#26273A"
        self.disabledFg = PLACEHOLDER_TEXT_COLOR

        iconW = 18 if icon else 0
        gap = 8 if icon else 0
        needed = iconW + gap + self.font.measure(text) + 44
        self.width = int(width) if width is not None else max(140, int(needed))

        try:
            parentBg = parent.cget("bg")
        except Exception:
            parentBg = MAIN_BG

        self.canvas = tk.Canvas(
            parent,
            width=self.width,
            height=self.height,
            highlightthickness=0,
            bd=0,
            bg=parentBg,
            cursor="hand2",
        )
        self.curBg = self.normalBg
        self.curFg = self.normalFg
        self._draw(self.normalBg, self.normalFg)

        self.canvas.bind("<Enter>", self._onEnter)
        self.canvas.bind("<Leave>", self._onLeave)
        self.canvas.bind("<Button-1>", self._onClick)

    def _roundRect(self, x1, y1, x2, y2, r, color):
        c = self.canvas
        c.create_rectangle(x1 + r, y1, x2 - r, y2, fill=color, outline=color)
        c.create_rectangle(x1, y1 + r, x2, y2 - r, fill=color, outline=color)
        c.create_oval(x1, y1, x1 + 2 * r, y1 + 2 * r, fill=color, outline=color)
        c.create_oval(x2 - 2 * r, y1, x2, y1 + 2 * r, fill=color, outline=color)
        c.create_oval(x1, y2 - 2 * r, x1 + 2 * r, y2, fill=color, outline=color)
        c.create_oval(x2 - 2 * r, y2 - 2 * r, x2, y2, fill=color, outline=color)

    def _draw(self, bg, fg):
        self.curBg = bg
        self.curFg = fg
        c = self.canvas
        c.delete("all")
        self._roundRect(1, 1, self.width - 1, self.height - 1, self.radius, bg)
        iconW = 18 if self.icon else 0
        gap = 8 if self.icon else 0
        contentW = iconW + gap + self.font.measure(self.text)
        startX = (self.width - contentW) / 2
        cy = self.height / 2
        if self.icon:
            renderIcon(c, self.icon, startX, cy - 9, startX + 18, cy + 9, fg, width=2)
            startX += iconW + gap
        c.create_text(startX, cy, text=self.text, anchor="w", fill=fg, font=self.font)

    def _onEnter(self, _event):
        if self.enabled:
            self._draw(self.hoverBg, self.hoverFg)

    def _onLeave(self, _event):
        if self.enabled:
            self._draw(self.normalBg, self.normalFg)

    def _onClick(self, _event):
        if self.enabled and self.command:
            self.command()

    def setEnabled(self, enabled):
        self.enabled = enabled
        if enabled:
            self.canvas.config(cursor="hand2")
            self._draw(self.normalBg, self.normalFg)
        else:
            self.canvas.config(cursor="arrow")
            self._draw(self.disabledBg, self.disabledFg)

    def setText(self, text):
        self.text = text
        self._draw(self.curBg, self.curFg)

    def config(self, **kwargs):
        if "text" in kwargs:
            self.setText(kwargs["text"])

    def pack(self, **kwargs):
        self.canvas.pack(**kwargs)
        return self

    def grid(self, **kwargs):
        self.canvas.grid(**kwargs)
        return self

    def place(self, **kwargs):
        self.canvas.place(**kwargs)
        return self


class UploadPanel:

    def __init__(self, parent: tk.Widget, accentColor: str, command, dropHandler=None, icon=None):
        self.command = command
        self.dropHandler = dropHandler
        self.accentColor = accentColor
        self.icon = icon
        self.currentBg = PANEL_ALT_BG
        self.frame = tk.Frame(parent, bg=MAIN_BG)
        # 画布修改：fill=BOTH expand=True，固定高度220
        self.canvas = tk.Canvas(self.frame, bg=MAIN_BG, highlightthickness=0, bd=0, height=220, cursor="hand2")
        self.canvas.pack(fill=tk.BOTH, expand=True)  # 关键修改：fill=BOTH
        self.fillId = self.canvas.create_rectangle(0, 0, 0, 0, fill=PANEL_ALT_BG, outline="")
        self.borderId = self.canvas.create_rectangle(0, 0, 0, 0, outline=accentColor, width=2, dash=(8, 6))
        self.inner = tk.Frame(self.canvas, bg=PANEL_ALT_BG)
        # 修复1：anchor改为nw，同时设置窗口宽度跟随画布
        self.innerWindow = self.canvas.create_window(4, 4, window=self.inner, anchor="nw", width=100)
        
        self.iconCanvas = None
        if icon:
            self.iconCanvas = tk.Canvas(
                self.inner, width=42, height=42, bg=PANEL_ALT_BG, highlightthickness=0, bd=0, cursor="hand2"
            )
            self.iconCanvas.pack(pady=(0, 12))
            self._paintIcon(PANEL_ALT_BG)
        self.tagLabel = tk.Label(
            self.inner,
            bg=PANEL_ALT_BG,
            fg=SUBTLE_TEXT_COLOR,
            font=(FONT_FAMILY, 11, "bold"),
        )
        self.tagLabel.pack(pady=(0, 10))
        self.mainLabel = tk.Label(
            self.inner,
            bg=PANEL_ALT_BG,
            fg=TEXT_COLOR,
            font=(FONT_FAMILY, 14),
            wraplength=760,
            justify=tk.CENTER,
        )
        self.mainLabel.pack()
        self.detailLabel = tk.Label(
            self.inner,
            bg=PANEL_ALT_BG,
            fg=SUBTLE_TEXT_COLOR,
            font=(FONT_FAMILY, 12),
            wraplength=760,
            justify=tk.CENTER,
        )
        self.detailLabel.pack(pady=(10, 0))
        self.footerLabel = tk.Label(
            self.inner,
            bg=PANEL_ALT_BG,
            fg=PLACEHOLDER_TEXT_COLOR,
            font=(FONT_FAMILY, 12),
            wraplength=760,
            justify=tk.CENTER,
        )
        self.footerLabel.pack(pady=(12, 0))

        self.canvas.bind("<Configure>", self.onConfigure)
        bindTargets = [self.canvas, self.inner, self.tagLabel, self.mainLabel, self.detailLabel, self.footerLabel]
        if self.iconCanvas is not None:
            bindTargets.append(self.iconCanvas)
        for widget in bindTargets:
            widget.bind("<Button-1>", self.onClick)
            widget.bind("<Enter>", self.onEnter)
            widget.bind("<Leave>", self.onLeave)
        if DND_FILES and self.dropHandler is not None:
            drag_widgets = [self.canvas, self.frame, self.inner, self.tagLabel, self.mainLabel, self.detailLabel, self.footerLabel]
            if self.iconCanvas is not None:
                drag_widgets.append(self.iconCanvas)
            for widget in drag_widgets:
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind("<<Drop>>", self.onDrop)

        self.canvas.update_idletasks()
        self.canvas.update_idletasks()
        self.canvas.update_idletasks()
        self.canvas.after(50, self._force_resize)

    def _force_resize(self):
        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w > 20 and h > 20:   # 确保尺寸有效
            fake_event = type('FakeEvent', (object,), {'width': w, 'height': h})
            self.onConfigure(fake_event)
        else:
            self.canvas.after(50, self._force_resize)   # 尺寸无效时重试
    def _paintIcon(self, bg):
        if self.iconCanvas is None:
            return
        self.iconCanvas.config(bg=bg)
        self.iconCanvas.delete("all")
        renderIcon(self.iconCanvas, self.icon, 2, 2, 40, 40, self.accentColor, width=2)

    def onConfigure(self, event):
        pad = 8
        cw = max(10, event.width - pad * 2)   # 防止负值
        ch = max(10, event.height - pad * 2)  # 防止负值
        # 更新背景填充、虚线边框矩形（使用保护后的 cw/ch 或直接使用事件宽高，但确保不小于 pad）
        self.canvas.coords(self.fillId, pad, pad, event.width - pad, event.height - pad)
        self.canvas.coords(self.borderId, pad, pad, event.width - pad, event.height - pad)
        self.canvas.itemconfig(self.innerWindow, width=cw)
        self.inner.update_idletasks()
        inner_h = self.inner.winfo_reqheight()
        offset_y = max(4, (ch - inner_h) / 2 + pad)
        self.canvas.coords(self.innerWindow, pad, offset_y)
    def onClick(self, _event):
        self.command()

    def onEnter(self, _event):
        self.currentBg = "#20233B"
        self.canvas.itemconfigure(self.borderId, width=3)
        self.canvas.itemconfigure(self.fillId, fill="#20233B")
        for widget in [self.inner, self.tagLabel, self.mainLabel, self.detailLabel, self.footerLabel]:
            widget.configure(bg="#20233B")
        self._paintIcon("#20233B")

    def onLeave(self, _event):
        self.currentBg = PANEL_ALT_BG
        self.canvas.itemconfigure(self.borderId, width=2)
        self.canvas.itemconfigure(self.fillId, fill=PANEL_ALT_BG)
        for widget in [self.inner, self.tagLabel, self.mainLabel, self.detailLabel, self.footerLabel]:
            widget.configure(bg=PANEL_ALT_BG)
        self._paintIcon(PANEL_ALT_BG)


    def onDrop(self, event):
        if self.dropHandler is not None:
            self.dropHandler(parseDroppedPaths(event.data))

    def setContent(self, tag: str, mainText: str, detailText: str, footerText: str):
        self.tagLabel.config(text=tag)
        self.mainLabel.config(text=mainText)
        self.detailLabel.config(text=detailText)
        self.footerLabel.config(text=footerText)



def parseDroppedPaths(rawValue: str) -> list[Path]:
    if not rawValue:
        return []
    try:
        items = root.tk.splitlist(rawValue)
    except Exception:
        items = [rawValue]
    paths = [Path(item) for item in items if item]
    return [path for path in paths if path.exists()]



def createActionButton(parent: tk.Widget, text: str, command, *, primary: bool = True) -> tk.Button:
    button = tk.Button(
        parent,
        text=text,
        command=command,
        relief="flat",
        bd=0,
        padx=18,
        pady=10,
        font=(FONT_FAMILY, 11, "bold"),
        cursor="hand2",
        activeforeground=TEXT_COLOR,
        disabledforeground=TEXT_COLOR,
    )
    button.normalBg = PRIMARY_COLOR if primary else PANEL_ALT_BG
    button.normalFg = TEXT_COLOR if primary else NAV_TEXT_COLOR
    button.hoverBg = PRIMARY_HOVER_COLOR if primary else "#262945"
    button.hoverFg = TEXT_COLOR
    button.disabledBg = PRIMARY_DISABLED_BG if primary else "#26273A"
    button.disabledFg = PLACEHOLDER_TEXT_COLOR

    def onEnter(_event):
        if str(button["state"]) == tk.NORMAL:
            button.config(bg=button.hoverBg, fg=button.hoverFg, activebackground=button.hoverBg)

    def onLeave(_event):
        if str(button["state"]) == tk.NORMAL:
            button.config(bg=button.normalBg, fg=button.normalFg, activebackground=button.hoverBg)

    button.bind("<Enter>", onEnter)
    button.bind("<Leave>", onLeave)
    setActionButtonState(button, True)
    return button



def setActionButtonState(button, enabled: bool):
    if isinstance(button, RoundedButton):
        button.setEnabled(enabled)
        return
    if enabled:

        button.config(
            state=tk.NORMAL,
            bg=button.normalBg,
            fg=button.normalFg,
            activebackground=button.hoverBg,
            activeforeground=button.hoverFg,
            cursor="hand2",
        )
    else:
        button.config(
            state=tk.DISABLED,
            bg=button.disabledBg,
            fg=button.disabledFg,
            activebackground=button.disabledBg,
            activeforeground=button.disabledFg,
            cursor="arrow",
        )



def refreshSummaryLabels():
    refsSummaryVar.set(f"参考自拍: {len(appState.referencePaths)} 张")
    mediaSummaryVar.set(f"素材文件: {len(appState.mediaPaths)} 个")
    mediaTypeSummaryVar.set(f"照片 {len(appState.photoPaths)} / 视频 {len(appState.videoPaths)}")
    sessionVar.set(f"桌面会话: {appState.sessionId}" if appState.sessionId else "桌面会话: -")
    resultsDirVar.set(f"结果文件夹: {appState.resultsRoot}" if appState.resultsRoot else "结果文件夹: -")
    matchedVar.set(
        f"识别结果: 照片 {len(getMatchedPhotoPaths())} 张，视频片段 {len(getMatchedClips())} 个"
    )



def refreshHeader():
    meta = PAGE_META[currentPage]
    headerTitleVar.set(meta["title"])
    headerSubtitleVar.set(meta["subtitle"])



def updateStatusAppearance():
    color = STATUS_COLORS.get(statusTone, MUTED_TEXT_COLOR)
    headerStatusLabel.config(fg=color)



def setStatus(message: str, tone: str = "idle"):
    global statusTone
    statusTone = tone
    statusVar.set(message)
    if "headerStatusLabel" in globals():
        updateStatusAppearance()



def refreshHighlightSummary():
    if appState.highlightStatus == "processing":
        highlightVar.set("正在生成高光视频，请稍候。")
        return

    highlightResult = appState.results.get("highlight") or {}
    if highlightResult.get("success"):
        output = highlightResult.get("output", {})
        selectedCount = output.get("photo_count", 0)
        clipCount = output.get("clip_count", len(getMatchedClips()))
        if selectedCount and clipCount:
            highlightVar.set(f"高光已生成：精选照片 {selectedCount} 张，并拼接 {clipCount} 个视频片段。")
        elif selectedCount:
            highlightVar.set(f"高光已生成：使用精选照片 {selectedCount} 张。")
        elif clipCount:
            highlightVar.set(f"高光已生成：使用视频片段 {clipCount} 个。")
        else:
            highlightVar.set("高光已生成。")
        return

    if highlightResult and not highlightResult.get("success"):
        highlightVar.set(f"高光生成失败：{highlightResult.get('error', '未知错误')}")
        return

    if hasHighlightInputs():
        highlightVar.set("从匹配到的照片和视频片段自动生成高光视频。")
    else:
        highlightVar.set("高光视频将在识别完成后生成。")



def refreshActionButtons():
    findBusy = appState.status in {"processing", "processing_photos", "processing_videos"}
    highlightBusy = appState.highlightStatus == "processing"
    travelBusy = appState.travelStatus == "processing"
    highlightPath = getHighlightPath()
    canFind = bool(appState.referencePaths and appState.mediaPaths and not findBusy and not highlightBusy and not travelBusy)

    if findBusy:
        findButtonHintVar.set("正在执行识别，请稍候。")
    elif canFind:
        findButtonHintVar.set("已完成素材准备，可以开始识别。")
    else:
        missingParts = []
        if not appState.referencePaths:
            missingParts.append("参考自拍")
        if not appState.mediaPaths:
            missingParts.append("待搜索素材")
        findButtonHintVar.set(f"请先上传{'和'.join(missingParts)}。")

    setActionButtonState(findButton, canFind)
    setActionButtonState(highlightButton, bool(appState.status == "done" and hasHighlightInputs() and not highlightBusy and not travelBusy))
    setActionButtonState(openResultsButton, bool(appState.resultsRoot and appState.resultsRoot.exists() and not findBusy and not highlightBusy))
    setActionButtonState(saveVideoButton, bool(highlightPath and highlightPath.exists() and not highlightBusy))
    setActionButtonState(playVideoButton, bool(highlightPath and highlightPath.exists() and not highlightBusy and cv2 is not None))
    playVideoButton.config(text="暂停高光视频" if videoPlaying else "播放高光视频")
    # Travel: available once find is done (uses A1 or B1 photos). Block during any find/highlight processing.
    canLoadTravel = bool(
        appState.status == "done"
        and not findBusy
        and not highlightBusy
        and not travelBusy
        and bool(getTravelPhotos())
    )
    setActionButtonState(loadTravelButton, canLoadTravel)
    setActionButtonState(reloadTravelButton, canLoadTravel)
    setActionButtonState(openTravelResultsBtn, bool(appState.resultsRoot and appState.resultsRoot.exists() and not findBusy and not travelBusy))



def resetHighlightResult():
    appState.results["highlight"] = None
    appState.highlightStatus = "idle"
    clearHighlightPreview()
    refreshHighlightSummary()
    writeSessionState()



def clearPhotoResults():
    for child in photoResultsBody.winfo_children():
        child.destroy()
    photoPreviewRefs.clear()



def clearClipResults():
    for child in clipResultsBody.winfo_children():
        child.destroy()



def clearHighlightPreview():
    global videoPreviewRef, videoTotalFrames, videoFps
    stopVideoPlayback()
    videoPreviewRef = None
    videoTotalFrames = 0
    videoFps = 0.0
    videoLabel.config(text="高光视频将在这里播放", image="")
    videoLabel.image = None
    videoProgressVar.set(0.0)
    videoProgressTextVar.set("00:00 / 00:00")



def resetFindResults(*, clearMediaSelection: bool):
    appState.results["photos"] = None
    appState.results["videos"] = None
    appState.results["highlight"] = None
    appState.results["travel"] = None
    appState.status = "idle"
    appState.highlightStatus = "idle"
    appState.travelStatus = "idle"
    appState.error = None
    if clearMediaSelection:
        appState.mediaPaths = []
        appState.photoPaths = []
        appState.videoPaths = []
    clearPhotoResults()
    clearClipResults()
    clearHighlightPreview()
    clearTravelResults()
    photoStatVar.set('请先完成"开始识别"。')
    clipStatVar.set('请先完成"开始识别"。')
    refreshSummaryLabels()
    refreshUploadPanels()
    refreshHighlightSummary()
    refreshTravelSummary()
    refreshActionButtons()
    renderResults()
    if appState.referencePaths or appState.mediaPaths:
        writeSessionState()



def startNewSession():
    appState.sessionId = None
    appState.sessionRoot = None
    appState.resultsRoot = None
    ensureDesktopSession()



def showPhotoPreview(path: Path):
    global previewWindow, previewImageRef
    try:
        image = Image.open(path)
        image.thumbnail((980, 980))
        previewImageRef = ImageTk.PhotoImage(image)
        if previewWindow is None or not previewWindow.winfo_exists():
            previewWindow = tk.Toplevel(root)
            previewWindow.configure(bg=MAIN_BG)
            previewWindow.geometry("960x960")
            previewWindow.transient(root)
        else:
            for child in previewWindow.winfo_children():
                child.destroy()
        previewWindow.title(path.name)
        label = tk.Label(previewWindow, image=previewImageRef, bg=MAIN_BG)
        label.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)
    except Exception as exc:
        messagebox.showerror("预览失败", f"无法预览图片: {exc}")



def displayReferenceThumbnails():
    referencePreviewRefs.clear()
    for child in referenceThumbStrip.winfo_children():
        child.destroy()

    if not appState.referencePaths:
        return

    for idx, path in enumerate(appState.referencePaths):
        thumbFrame = tk.Frame(referenceThumbStrip, bg=PANEL_ALT_BG, padx=6, pady=6, highlightthickness=1)
        thumbFrame.config(highlightbackground=SECTION_LINE, highlightcolor=SECTION_LINE)
        thumbFrame.grid(row=0, column=idx, sticky="nw", padx=(0, 10), pady=2)
        try:
            image = Image.open(path)
            image.thumbnail((REFERENCE_THUMB_SIZE, REFERENCE_THUMB_SIZE))
            photo = ImageTk.PhotoImage(image)
            thumbLabel = tk.Label(thumbFrame, image=photo, bg=PANEL_ALT_BG)
            thumbLabel.image = photo
            thumbLabel.pack()
            referencePreviewRefs.append(photo)
        except Exception:
            tk.Label(
                thumbFrame,
                text="无法预览",
                bg=PANEL_ALT_BG,
                fg=TEXT_COLOR,
                font=(FONT_FAMILY, 10),
                width=10,
                height=5,
            ).pack()
        tk.Label(
            thumbFrame,
            text=path.name,
            bg=PANEL_ALT_BG,
            fg=MUTED_TEXT_COLOR,
            font=(FONT_FAMILY, 10),
            wraplength=110,
            justify=tk.CENTER,
        ).pack(pady=(6, 0))



def renderPhotoResults(paths: list[Path]):
    clearPhotoResults()
    photoResult = appState.results.get("photos") or {}

    if photoResult.get("success"):
        total = photoResult.get("output", {}).get("total", len(appState.photoPaths))
        matchedCount = photoResult.get("output", {}).get("matched_count", len(paths))
        if paths:
            photoStatVar.set(f"在 {total} 张照片中找到 {matchedCount} 张含有你的照片。")
        else:
            photoStatVar.set("未找到含有你的照片。")
    elif photoResult:
        photoStatVar.set(f"照片识别失败：{photoResult.get('error', '未知错误')}")
    elif appState.status == "done" and not appState.photoPaths:
        photoStatVar.set("本次素材中没有照片。")
    else:
        photoStatVar.set('请先完成"开始识别"。')

    if not paths:
        placeholder = tk.Label(
            photoResultsBody,
            text='请先完成"开始识别"',
            bg=PANEL_BG,
            fg=PLACEHOLDER_TEXT_COLOR,
            font=(FONT_FAMILY, 13),
        )
        placeholder.pack(fill=tk.BOTH, expand=True, pady=20)
        return

    photoResultsBody.update_idletasks()
    panelWidth = max(photoResultsBody.winfo_width(), 680)
    columns = max(2, min(5, panelWidth // 170))
    for idx, path in enumerate(paths):
        thumbFrame = tk.Frame(photoResultsBody, bg=PANEL_ALT_BG, padx=8, pady=8, highlightthickness=1)
        thumbFrame.config(highlightbackground=SECTION_LINE, highlightcolor=SECTION_LINE)
        thumbFrame.grid(row=idx // columns, column=idx % columns, sticky="n", padx=6, pady=6)
        try:
            image = Image.open(path)
            image.thumbnail((PHOTO_THUMB_SIZE, PHOTO_THUMB_SIZE))
            photo = ImageTk.PhotoImage(image)
            thumbLabel = tk.Label(thumbFrame, image=photo, bg=PANEL_ALT_BG, cursor="hand2")
            thumbLabel.image = photo
            thumbLabel.pack()
            thumbLabel.bind("<Button-1>", lambda _event, selectedPath=path: showPhotoPreview(selectedPath))
            photoPreviewRefs.append(photo)
        except Exception:
            tk.Label(
                thumbFrame,
                text="无法预览",
                bg=PANEL_ALT_BG,
                fg=TEXT_COLOR,
                width=14,
                height=7,
            ).pack()
        nameLabel = tk.Label(
            thumbFrame,
            text=path.name,
            bg=PANEL_ALT_BG,
            fg=TEXT_COLOR,
            wraplength=150,
            justify=tk.CENTER,
            cursor="hand2",
            font=(FONT_FAMILY, 10),
        )
        nameLabel.pack(pady=(6, 0))
        nameLabel.bind("<Button-1>", lambda _event, selectedPath=path: showPhotoPreview(selectedPath))

        photoBtns = tk.Frame(thumbFrame, bg=PANEL_ALT_BG)
        photoBtns.pack(pady=(8, 0), fill=tk.X)

        def _createMiniBtn(parent, btnText, btnCmd):
            btn = tk.Button(
                parent,
                text=btnText,
                command=btnCmd,
                relief="flat",
                bd=0,
                padx=8,
                pady=4,
                font=(FONT_FAMILY, 9, "bold"),
                cursor="hand2",
                bg=PANEL_BG,
                fg=NAV_TEXT_COLOR,
                activebackground="#262945",
                activeforeground=TEXT_COLOR,
            )
            def _onEnter(_e):
                btn.config(bg="#262945", fg=TEXT_COLOR)
            def _onLeave(_e):
                btn.config(bg=PANEL_BG, fg=NAV_TEXT_COLOR)
            btn.bind("<Enter>", _onEnter)
            btn.bind("<Leave>", _onLeave)
            return btn

        saveBtn = _createMiniBtn(photoBtns, "另存为", lambda p=path: saveSinglePhoto(p))
        saveBtn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 3))

        openDirBtn = _createMiniBtn(photoBtns, "打开位置", lambda p=path: openPath(p.parent))
        openDirBtn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(3, 0))



def renderClipResults(clips: list[dict]):
    clearClipResults()
    videoResult = appState.results.get("videos") or {}

    if videoResult.get("success"):
        if clips:
            clipStatVar.set(f"找到 {len(clips)} 个视频片段。")
        else:
            clipStatVar.set("未找到含有你的视频片段。")
    elif videoResult:
        clipStatVar.set(f"视频识别失败：{videoResult.get('error', '未知错误')}")
    elif appState.status == "done" and not appState.videoPaths:
        clipStatVar.set("本次素材中没有视频。")
    else:
        clipStatVar.set('请先完成"开始识别"。')

    if not clips:
        placeholder = tk.Label(
            clipResultsBody,
            text='请先完成"开始识别"',
            bg=PANEL_BG,
            fg=PLACEHOLDER_TEXT_COLOR,
            font=(FONT_FAMILY, 13),
        )
        placeholder.pack(fill=tk.BOTH, expand=True, pady=20)
        return

    for item in clips:
        card = tk.Frame(clipResultsBody, bg=PANEL_ALT_BG, padx=16, pady=14, highlightthickness=1)
        card.config(highlightbackground=SECTION_LINE, highlightcolor=SECTION_LINE)
        card.pack(fill=tk.X, pady=6)

        topRow = tk.Frame(card, bg=PANEL_ALT_BG)
        topRow.pack(fill=tk.X)
        titleBlock = tk.Frame(topRow, bg=PANEL_ALT_BG)
        titleBlock.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Label(
            titleBlock,
            text=item["path"].name,
            bg=PANEL_ALT_BG,
            fg=TEXT_COLOR,
            font=(FONT_FAMILY, 11, "bold"),
        ).pack(anchor=tk.W)
        tk.Label(
            titleBlock,
            text=f"来源视频：{item['video']}",
            bg=PANEL_ALT_BG,
            fg=MUTED_TEXT_COLOR,
            font=(FONT_FAMILY, 10),
        ).pack(anchor=tk.W, pady=(3, 0))
        tk.Label(
            topRow,
            text=item["badge"],
            bg="#2A2D4B",
            fg=NAV_TEXT_COLOR,
            padx=10,
            pady=4,
            font=(FONT_FAMILY, 9, "bold"),
        ).pack(side=tk.RIGHT)

        metaRow = tk.Frame(card, bg=PANEL_ALT_BG)
        metaRow.pack(anchor=tk.W, pady=(12, 10))
        for metaTitle, metaValue in [
            ("开始", formatSeconds(item["start_s"])),
            ("结束", formatSeconds(item["end_s"])),
            ("时长", formatSeconds(item["duration_s"])),
        ]:
            metaCard = tk.Frame(metaRow, bg=MAIN_BG, padx=12, pady=8, highlightthickness=1)
            metaCard.config(highlightbackground=SECTION_LINE, highlightcolor=SECTION_LINE)
            metaCard.pack(side=tk.LEFT, padx=(0, 10))
            tk.Label(metaCard, text=metaTitle, bg=MAIN_BG, fg=SUBTLE_TEXT_COLOR, font=(FONT_FAMILY, 9)).pack(anchor=tk.W)
            tk.Label(metaCard, text=metaValue, bg=MAIN_BG, fg=TEXT_COLOR, font=(FONT_FAMILY, 10, "bold")).pack(anchor=tk.W, pady=(3, 0))

        actionRow = tk.Frame(card, bg=PANEL_ALT_BG)
        actionRow.pack(anchor=tk.W)
        previewButton = createActionButton(actionRow, "打开片段", lambda clipPath=item["path"]: openPath(clipPath), primary=False)
        previewButton.pack(side=tk.LEFT, padx=(0, 10))
        openDirButton = createActionButton(actionRow, "打开所在文件夹", lambda clipPath=item["path"]: openPath(clipPath.parent), primary=False)
        openDirButton.pack(side=tk.LEFT)



def renderResults():
    renderPhotoResults(getMatchedPhotoPaths())
    renderClipResults(getMatchedClips())
    renderTravelPoints()
    refreshSummaryLabels()
    refreshHighlightSummary()
    refreshTravelSummary()
    refreshActionButtons()



def refreshUploadPanels():
    if appState.referencePaths:
        names = "、".join(path.name for path in appState.referencePaths[:3])
        referenceUploadPanel.setContent(
            "第一步 - 参考自拍 (1-3 张)",
            f"已选择 {len(appState.referencePaths)} 张参考自拍",
            names,
            "点击重新选择文件",
        )
    else:
        referenceUploadPanel.setContent(
            "第一步 - 参考自拍 (1-3 张)",
            "拖放自拍到此处或点击选择",
            "建议使用清晰正脸自拍",
            "未选择任何文件",
        )

    if appState.mediaPaths:
        sampleNames = "、".join(path.name for path in appState.mediaPaths[:4])
        more = "" if len(appState.mediaPaths) <= 4 else f" 等 {len(appState.mediaPaths)} 个文件"
        mediaUploadPanel.setContent(
            "第二步 - 要搜索的素材",
            f"已选择 {len(appState.mediaPaths)} 个素材文件",
            f"{sampleNames}{more}",
            "支持 JPG、PNG、MP4、MOV，支持拖入文件夹",
        )
    else:
        mediaUploadPanel.setContent(
            "第二步 - 要搜索的素材",
            "拖放照片和视频到此处或点击选择",
            "支持 JPG、PNG、MP4、MOV",
            "未选择任何文件",
        )



def showVideoPreview():
    global videoPreviewRef, videoTotalFrames, videoFps
    if cv2 is None:
        return

    highlightPath = getHighlightPath()
    if not highlightPath or not highlightPath.exists():
        return

    capture = cv2.VideoCapture(str(highlightPath))
    if not capture.isOpened():
        return

    videoTotalFrames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    videoFps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
    durationSeconds = (videoTotalFrames / videoFps) if videoTotalFrames > 0 and videoFps > 0 else 0.0
    videoProgressVar.set(0.0)
    videoProgressTextVar.set(f"00:00 / {formatClock(durationSeconds)}")

    ret, frame = capture.read()
    if ret:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(frame)
        image.thumbnail(VIDEO_PREVIEW_SIZE)
        photo = ImageTk.PhotoImage(image)
        videoPreviewRef = photo
        videoLabel.config(image=photo, text="")
        videoLabel.image = photo
    capture.release()



def stopVideoPlayback():
    global videoCapture, videoPlaying
    videoPlaying = False
    if videoCapture is not None:
        try:
            videoCapture.release()
        except Exception:
            pass
    videoCapture = None
    if videoPreviewRef is not None:
        videoLabel.config(text="", image=videoPreviewRef)
        videoLabel.image = videoPreviewRef
    else:
        videoLabel.config(text="高光视频将在这里播放", image="")
        videoLabel.image = None
    if videoTotalFrames > 0 and videoFps > 0:
        videoProgressVar.set(0.0)
        videoProgressTextVar.set(f"00:00 / {formatClock(videoTotalFrames / videoFps)}")
    else:
        videoProgressVar.set(0.0)
        videoProgressTextVar.set("00:00 / 00:00")
    if "playVideoButton" in globals():
        playVideoButton.config(text="播放高光视频")



def updateVideoFrame():
    global videoCapture, videoPlaying
    if not videoPlaying or videoCapture is None:
        return

    ret, frame = videoCapture.read()
    if not ret:
        stopVideoPlayback()
        refreshActionButtons()
        return

    try:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(frame)
        image.thumbnail(VIDEO_PREVIEW_SIZE)
        photo = ImageTk.PhotoImage(image)
        videoLabel.config(image=photo, text="")
        videoLabel.image = photo
        currentFrame = int(videoCapture.get(cv2.CAP_PROP_POS_FRAMES) or 0)
        if videoTotalFrames > 0:
            videoProgressVar.set(min(100.0, currentFrame * 100.0 / videoTotalFrames))
        if videoFps > 0:
            currentSeconds = currentFrame / videoFps
            totalSeconds = (videoTotalFrames / videoFps) if videoTotalFrames > 0 else 0.0
            videoProgressTextVar.set(f"{formatClock(currentSeconds)} / {formatClock(totalSeconds)}")
    except Exception as exc:
        stopVideoPlayback()
        messagebox.showerror("播放失败", f"无法播放高光视频: {exc}")
        refreshActionButtons()
        return

    frameDelay = int(1000 / videoFps) if videoFps > 0 else 40
    root.after(max(20, frameDelay), updateVideoFrame)



def toggleVideoPlayback():
    global videoCapture, videoPlaying, videoTotalFrames, videoFps
    if cv2 is None:
        messagebox.showerror("缺少依赖", "当前环境不支持视频播放，请安装 opencv-python。")
        return

    highlightPath = getHighlightPath()
    if not highlightPath or not highlightPath.exists():
        messagebox.showwarning("无高光视频", "请先生成高光视频。")
        return

    if videoPlaying:
        stopVideoPlayback()
        refreshActionButtons()
        return

    stopVideoPlayback()
    videoCapture = cv2.VideoCapture(str(highlightPath))
    if not videoCapture.isOpened():
        videoCapture = None
        messagebox.showerror("视频打开失败", "无法打开高光视频。")
        return

    videoTotalFrames = int(videoCapture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    videoFps = float(videoCapture.get(cv2.CAP_PROP_FPS) or 0.0)
    videoPlaying = True
    refreshActionButtons()
    updateVideoFrame()



def openPath(path: Path):
    try:
        if sys.platform == "win32":
            import os

            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as exc:
        messagebox.showerror("打开失败", f"无法打开文件: {exc}")



def applyReferenceSelection(paths: list[Path]):
    validPaths = [path for path in paths if path.is_file() and path.suffix.lower() in PHOTO_EXTS]
    if not validPaths:
        messagebox.showwarning("参考自拍无效", "请选择图片文件。")
        return
    if len(validPaths) > 3:
        messagebox.showwarning("参考自拍限制", "只能选择最多 3 张参考自拍。")
        return

    appState.referencePaths = sortPaths(validPaths)
    startNewSession()
    writeSessionState()
    resetFindResults(clearMediaSelection=False)
    refreshSummaryLabels()
    refreshUploadPanels()
    displayReferenceThumbnails()

    if appState.mediaPaths:
        setStatus("已选择参考自拍。现在可以开始识别。")
    else:
        setStatus("已选择参考自拍。请继续选择素材文件。")



def selectReferences(droppedPaths: list[Path] | None = None):
    if droppedPaths is None:
        paths = filedialog.askopenfilenames(
            title="选择 1-3 张参考自拍",
            filetypes=[("Image files", "*.jpg *.jpeg *.png *.heic *.webp *.bmp *.tif *.tiff")],
        )
        droppedPaths = [Path(path) for path in paths]
    if not droppedPaths:
        return
    applyReferenceSelection(droppedPaths)



def applyMediaSelection(paths: list[Path]):
    photoPaths, videoPaths, mediaPaths = collectMediaFiles(paths)
    if not mediaPaths:
        messagebox.showwarning("未找到素材", "请选择支持的照片或视频文件。")
        return

    appState.mediaPaths = mediaPaths
    appState.photoPaths = photoPaths
    appState.videoPaths = videoPaths
    startNewSession()
    writeSessionState()
    resetFindResults(clearMediaSelection=False)
    refreshSummaryLabels()
    refreshUploadPanels()

    if appState.referencePaths:
        setStatus("已选择素材文件。现在可以开始识别。")
    else:
        setStatus("已选择素材文件。请先选择参考自拍。")



def selectMediaItems(droppedPaths: list[Path] | None = None):
    if droppedPaths is None:
        choice = messagebox.askyesnocancel(
            "选择素材类型",
            "是 = 选择文件\n否 = 选择文件夹\n取消 = 返回",
        )
        if choice is None:
            return
        if choice:
            paths = filedialog.askopenfilenames(
                title="选择要搜索的素材文件",
                filetypes=[("Media files", "*.jpg *.jpeg *.png *.heic *.webp *.bmp *.tif *.tiff *.mp4 *.mov *.avi *.mkv *.m4v")],
            )
            droppedPaths = [Path(path) for path in paths]
        else:
            folder = filedialog.askdirectory(title="选择包含素材的文件夹")
            if folder:
                droppedPaths = [Path(folder)]
            else:
                return
    if not droppedPaths:
        return
    applyMediaSelection(droppedPaths)



def onFindComplete():
    writeSessionState()
    renderResults()
    photoCount = len(getMatchedPhotoPaths())
    clipCount = len(getMatchedClips())
    setStatus(
        f"识别完成：扫描照片 {len(appState.photoPaths)} 张、视频 {len(appState.videoPaths)} 个，匹配照片 {photoCount} 张、视频片段 {clipCount} 个。",
        "done",
    )
    showPage("find")



def onFindError(errorMessage: str):
    writeSessionState()
    renderResults()
    setStatus(f"识别失败：{errorMessage}", "error")



def runFindMe():
    if not appState.referencePaths:
        messagebox.showwarning("缺少参考自拍", "请先选择至少一张参考自拍。")
        return
    if not appState.mediaPaths:
        messagebox.showwarning("缺少素材文件", "请先选择待搜索素材。")
        return
    if not appState.resultsRoot:
        messagebox.showwarning("缺少结果目录", "无法确定结果文件夹，请重新选择参考自拍。")
        return

    if not appState.photoPaths and not appState.videoPaths:
        messagebox.showwarning("未找到素材", "当前选择中没有支持的照片或视频文件。")
        return

    # Graceful degradation: if ffmpeg missing and user has videos, warn but still run photos.
    if not ffmpegAvailable and appState.videoPaths:
        if not messagebox.askyesno(
            "ffmpeg 未安装",
            "未检测到 ffmpeg，将跳过视频片段识别（A2）。\n仅识别照片中是否包含你，视频片段不会被剪辑。\n\n是否继续？\n\n（建议安装 ffmpeg：macOS `brew install ffmpeg` / Windows `choco install ffmpeg`）",
        ):
            return

    resetFindResults(clearMediaSelection=False)
    appState.status = "processing"
    appState.error = None
    writeSessionState()
    refreshSummaryLabels()
    refreshHighlightSummary()
    refreshActionButtons()
    setStatus(
        f"正在扫描素材：照片 {len(appState.photoPaths)} 张，视频 {len(appState.videoPaths)} 个。",
        "processing",
    )

    photoOutputDir = getResultsRoot() / "my_photos"
    clipOutputDir = getResultsRoot() / "my_clips"

    def worker():
        photoResult = None
        videoResult = None
        try:
            if appState.photoPaths:
                appState.status = "processing_photos"
                writeSessionState()
                root.after(0, lambda: setStatus(f"正在识别照片（共 {len(appState.photoPaths)} 张）...", "processing"))
                root.after(0, refreshActionButtons)
                photoResult = runFindPhotos(
                    [str(path) for path in appState.referencePaths],
                    [str(path) for path in appState.photoPaths],
                    str(photoOutputDir),
                )
                if not photoResult["success"]:
                    raise RuntimeError(photoResult.get("error", "照片识别失败"))

            if appState.videoPaths and ffmpegAvailable:
                appState.status = "processing_videos"
                writeSessionState()
                root.after(0, lambda: setStatus(f"正在识别视频（共 {len(appState.videoPaths)} 个）...", "processing"))
                root.after(0, refreshActionButtons)
                videoResult = runFindVideos(
                    [str(path) for path in appState.referencePaths],
                    [str(path) for path in appState.videoPaths],
                    str(clipOutputDir),
                )
                if not videoResult["success"]:
                    raise RuntimeError(videoResult.get("error", "视频识别失败"))
            elif appState.videoPaths and not ffmpegAvailable:
                # Skip A2 silently; the user already acknowledged the warning before runFindMe.
                print("WARN: skipping A2 (video find) because ffmpeg is not installed", flush=True)

            appState.results["photos"] = photoResult
            appState.results["videos"] = videoResult
            appState.results["highlight"] = None
            appState.status = "done"
            appState.highlightStatus = "idle"
            appState.error = None
            root.after(0, onFindComplete)
        except Exception as exc:
            appState.results["photos"] = photoResult
            appState.results["videos"] = videoResult
            appState.results["highlight"] = None
            appState.status = "error"
            appState.highlightStatus = "idle"
            appState.error = str(exc)
            root.after(0, lambda exc=exc: onFindError(str(exc)))

    threading.Thread(target=worker, daemon=True).start()



def onHighlightComplete():
    writeSessionState()
    showVideoPreview()
    # Highlight B1 may have re-curated photos; invalidate stale travel data so user reloads from fresh selection
    if appState.results.get("travel"):
        resetTravelResult()
    refreshSummaryLabels()
    refreshHighlightSummary()
    refreshActionButtons()
    highlightPath = getHighlightPath()
    setStatus(f"高光生成完成：{highlightPath}", "done")
    showPage("highlight")



def onHighlightError(errorMessage: str):
    writeSessionState()
    refreshSummaryLabels()
    refreshHighlightSummary()
    refreshActionButtons()
    setStatus(f"高光生成失败：{errorMessage}", "error")



def generateHighlight():
    myPhotos = [str(path) for path in getMatchedPhotoPaths()]
    myClips = getMatchedClipPaths()
    if not myPhotos and not myClips:
        messagebox.showwarning("无匹配结果", "请先完成识别，并确保有匹配照片或视频片段。")
        return
    if not appState.resultsRoot:
        messagebox.showwarning("缺少结果目录", "请先重新选择参考自拍以确认结果目录。")
        return
    if not ffmpegAvailable:
        messagebox.showerror(
            "无法生成高光视频",
            "未检测到 ffmpeg，无法生成高光视频。\n\n请先安装：\nmacOS: `brew install ffmpeg`\nWindows: `choco install ffmpeg`",
        )
        return

    appState.highlightStatus = "processing"
    appState.results["highlight"] = None
    writeSessionState()
    clearHighlightPreview()
    refreshHighlightSummary()
    refreshActionButtons()
    setStatus(
        f"正在生成高光视频：照片 {len(myPhotos)} 张，视频片段 {len(myClips)} 个。",
        "processing",
    )
    highlightDir = getResultsRoot() / "highlight"

    def worker():
        try:
            result = runBuildHighlight(myPhotos, myClips, str(highlightDir), audioPath=None)
            if not result["success"]:
                raise RuntimeError(result.get("error", "高光生成失败"))
            appState.results["highlight"] = result
            appState.highlightStatus = "done"
            root.after(0, onHighlightComplete)
        except Exception as exc:
            appState.results["highlight"] = {"success": False, "output": None, "error": str(exc)}
            appState.highlightStatus = "error"
            root.after(0, lambda exc=exc: onHighlightError(str(exc)))

    threading.Thread(target=worker, daemon=True).start()



def saveHighlightVideo():
    highlightPath = getHighlightPath()
    if not highlightPath or not highlightPath.exists():
        messagebox.showwarning("无高光视频", "请先生成高光视频。")
        return

    destination = filedialog.asksaveasfilename(
        title="另存为高光视频",
        defaultextension=".mp4",
        filetypes=[("MP4 视频", "*.mp4")],
        initialfile=highlightPath.name,
    )
    if not destination:
        return

    try:
        shutil.copy2(str(highlightPath), destination)
        setStatus(f"高光视频已另存为：{destination}", "done")
    except Exception as exc:
        messagebox.showerror("保存失败", f"无法保存高光视频: {exc}")


savedPhotosDir: Path | None = None

def saveSinglePhoto(srcPath: Path):
    destination = filedialog.asksaveasfilename(
        title="另存照片",
        defaultextension=srcPath.suffix or ".jpg",
        filetypes=[("Image files", "*.jpg *.jpeg *.png *.heic *.webp *.bmp *.tif *.tiff")],
        initialfile=srcPath.name,
    )
    if not destination:
        return
    try:
        destPath = Path(destination)
        destPath.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(srcPath), str(destPath))
        setStatus(f"照片已另存为：{destPath}", "done")
    except Exception as exc:
        messagebox.showerror("保存失败", f"无法保存照片: {exc}")


def saveAllMatchedPhotos():
    global savedPhotosDir
    matchedPaths = getMatchedPhotoPaths()
    if not matchedPaths:
        messagebox.showwarning("无匹配照片", "请先完成识别，并确保有匹配的照片。")
        return

    destDir = filedialog.askdirectory(title="选择保存全部照片的文件夹")
    if not destDir:
        return
    destDirPath = Path(destDir)
    savedPhotosDir = destDirPath

    successCount = 0
    errorMessages = []
    for srcPath in matchedPaths:
        try:
            destPath = destDirPath / srcPath.name
            counter = 1
            while destPath.exists():
                stem = srcPath.stem
                suffix = srcPath.suffix
                destPath = destDirPath / f"{stem}_{counter}{suffix}"
                counter += 1
            shutil.copy2(str(srcPath), str(destPath))
            successCount += 1
        except Exception as exc:
            errorMessages.append(f"{srcPath.name}: {exc}")

    if successCount > 0:
        setStatus(f"已保存 {successCount} 张照片到：{destDirPath}", "done")
    if errorMessages:
        messagebox.showerror("部分保存失败", "\n".join(errorMessages[:10]))


def openSavedPhotosDir():
    global savedPhotosDir
    if savedPhotosDir is None or not savedPhotosDir.exists():
        matchedPaths = getMatchedPhotoPaths()
        if matchedPaths:
            firstDir = matchedPaths[0].parent
            openPath(firstDir.resolve())
            return
        messagebox.showwarning("未找到目录", "请先另存照片，或完成识别后再试。")
        return
    openPath(savedPhotosDir.resolve())



def openResultsFolder():
    if not appState.resultsRoot:
        messagebox.showwarning("无结果目录", "请先完成识别以创建结果目录。")
        return
    if not appState.resultsRoot.exists():
        messagebox.showwarning("结果不存在", "结果目录尚未创建。")
        return
    openPath(appState.resultsRoot.resolve())


def openUrl(url: str):
    """Open URL in the system default browser (cross-platform)."""
    try:
        if sys.platform == "win32":
            import os

            os.startfile(url)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url])
    except Exception as exc:
        messagebox.showerror("打开失败", f"无法打开链接: {exc}")


def openInBrowserMap(lat: float, lng: float):
    """Open a cross-platform map view (OpenStreetMap) for the given coordinates."""
    url = f"https://www.openstreetmap.org/?mlat={lat}&mlon={lng}#map=15/{lat}/{lng}"
    openUrl(url)


def clearTravelResults():
    for child in travelResultsBody.winfo_children():
        child.destroy()
    travelPreviewRefs.clear()


def refreshTravelSummary():
    points = getTravelMapPoints()
    total = len(points)
    missing = sum(1 for point in points if not point.get("has_gps"))
    travelSummaryVar.set(f"共 {total} 个点位，{missing} 个缺少 GPS")

    if appState.travelStatus == "processing":
        travelStatVar.set("正在加载轨迹数据…")
        travelHintVar.set("正在提取照片 EXIF GPS 信息，请稍候。")
        return

    travelResult = appState.results.get("travel") or {}
    if travelResult.get("success"):
        if total == 0:
            travelStatVar.set("未找到可用的照片。")
            travelHintVar.set("请先完成识别或生成高光视频。")
        elif missing == total:
            travelStatVar.set(f"共 {total} 张照片，但都缺少 GPS 信息。")
            travelHintVar.set("照片没有 GPS EXIF 数据，无法在地图上展示。")
        else:
            travelStatVar.set(f"已加载 {total} 个点位（{missing} 个缺少 GPS）。")
            travelHintVar.set("点击缩略图可放大查看，点击「地图」按钮在浏览器中查看位置。")
    elif travelResult:
        travelStatVar.set(f"轨迹加载失败：{travelResult.get('error', '未知错误')}")
        travelHintVar.set("请重试或检查日志。")
    elif appState.status == "done":
        travelStatVar.set("识别已完成，点击「加载轨迹数据」开始。")
        travelHintVar.set("将优先使用高光精选照片，未生成高光时回退到全部匹配照片。")
    else:
        travelStatVar.set('请先完成"开始识别"后加载轨迹数据。')
        travelHintVar.set("识别完成后可加载轨迹数据。")


def renderTravelPoints():
    clearTravelResults()
    points = getTravelMapPoints()

    if not points:
        placeholder = tk.Label(
            travelResultsBody,
            text='请先完成"开始识别"并加载轨迹数据',
            bg=PANEL_BG,
            fg=PLACEHOLDER_TEXT_COLOR,
            font=(FONT_FAMILY, 13),
        )
        placeholder.pack(fill=tk.BOTH, expand=True, pady=20)
        return

    travelResultsBody.update_idletasks()
    panelWidth = max(travelResultsBody.winfo_width(), 680)
    columns = max(2, min(4, panelWidth // 220))

    for idx, point in enumerate(points):
        photoPath = Path(point.get("photo_path", "")) if point.get("photo_path") else None
        takenAt = point.get("taken_at") or "时间未知"
        hasGps = point.get("has_gps")
        lat = point.get("lat")
        lng = point.get("lng")

        card = tk.Frame(travelResultsBody, bg=PANEL_ALT_BG, padx=12, pady=12, highlightthickness=1)
        card.config(highlightbackground=SECTION_LINE, highlightcolor=SECTION_LINE)
        card.grid(row=idx // columns, column=idx % columns, sticky="n", padx=6, pady=6)

        # Order badge + thumbnail
        header = tk.Frame(card, bg=PANEL_ALT_BG)
        header.pack(fill=tk.X)
        tk.Label(
            header,
            text=f"#{idx + 1}",
            bg=PRIMARY_COLOR,
            fg=TEXT_COLOR,
            padx=8,
            pady=2,
            font=(FONT_FAMILY, 9, "bold"),
        ).pack(side=tk.LEFT)

        badgeText = "GPS" if hasGps else "无 GPS"
        badgeBg = SUCCESS_COLOR if hasGps else MUTED_TEXT_COLOR
        tk.Label(
            header,
            text=badgeText,
            bg=badgeBg,
            fg=TEXT_COLOR,
            padx=8,
            pady=2,
            font=(FONT_FAMILY, 9, "bold"),
        ).pack(side=tk.RIGHT)

        thumbWrap = tk.Frame(card, bg=PANEL_ALT_BG)
        thumbWrap.pack(pady=(8, 6))
        if photoPath and photoPath.exists():
            try:
                image = Image.open(photoPath)
                image.thumbnail((PHOTO_THUMB_SIZE, PHOTO_THUMB_SIZE))
                photo = ImageTk.PhotoImage(image)
                thumbLabel = tk.Label(thumbWrap, image=photo, bg=PANEL_ALT_BG, cursor="hand2")
                thumbLabel.image = photo
                thumbLabel.pack()
                thumbLabel.bind("<Button-1>", lambda _event, p=photoPath: showPhotoPreview(p))
                travelPreviewRefs.append(photo)
            except Exception:
                tk.Label(
                    thumbWrap,
                    text="无法预览",
                    bg=PANEL_ALT_BG,
                    fg=TEXT_COLOR,
                    width=14,
                    height=7,
                ).pack()
        else:
            tk.Label(
                thumbWrap,
                text="文件缺失",
                bg=PANEL_ALT_BG,
                fg=MUTED_TEXT_COLOR,
                width=14,
                height=7,
            ).pack()

        tk.Label(
            card,
            text=photoPath.name if photoPath else "(未知文件)",
            bg=PANEL_ALT_BG,
            fg=TEXT_COLOR,
            font=(FONT_FAMILY, 10),
            wraplength=180,
            justify=tk.CENTER,
            cursor="hand2",
        ).pack()
        tk.Label(
            card,
            text=takenAt,
            bg=PANEL_ALT_BG,
            fg=MUTED_TEXT_COLOR,
            font=(FONT_FAMILY, 9),
            wraplength=180,
            justify=tk.CENTER,
        ).pack(pady=(4, 0))

        coordText = f"{lat:.5f}, {lng:.5f}" if hasGps else "缺少 GPS 数据"
        tk.Label(
            card,
            text=coordText,
            bg=PANEL_ALT_BG,
            fg=SUCCESS_COLOR if hasGps else MUTED_TEXT_COLOR,
            font=(FONT_FAMILY, 9),
            wraplength=180,
            justify=tk.CENTER,
        ).pack(pady=(4, 8))

        actionRow = tk.Frame(card, bg=PANEL_ALT_BG)
        actionRow.pack(fill=tk.X, pady=(2, 0))

        def _createMiniBtn(parent, btnText, btnCmd, btnEnabled=True):
            btn = tk.Button(
                parent,
                text=btnText,
                command=btnCmd,
                relief="flat",
                bd=0,
                padx=8,
                pady=4,
                font=(FONT_FAMILY, 9, "bold"),
                cursor="hand2" if btnEnabled else "arrow",
                bg=PANEL_BG,
                fg=NAV_TEXT_COLOR if btnEnabled else PLACEHOLDER_TEXT_COLOR,
                activebackground="#262945",
                activeforeground=TEXT_COLOR,
                state=tk.NORMAL if btnEnabled else tk.DISABLED,
            )
            def _onEnter(_e):
                if btnEnabled:
                    btn.config(bg="#262945", fg=TEXT_COLOR)
            def _onLeave(_e):
                if btnEnabled:
                    btn.config(bg=PANEL_BG, fg=NAV_TEXT_COLOR)
            btn.bind("<Enter>", _onEnter)
            btn.bind("<Leave>", _onLeave)
            return btn

        mapBtn = _createMiniBtn(
            actionRow,
            "地图",
            lambda lat=lat, lng=lng: openInBrowserMap(lat, lng),
            btnEnabled=bool(hasGps),
        )
        mapBtn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 3))

        openPhotoBtn = _createMiniBtn(
            actionRow,
            "打开",
            lambda p=photoPath: openPath(p) if p else None,
            btnEnabled=bool(photoPath and photoPath.exists()),
        )
        openPhotoBtn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(3, 0))


def onTravelComplete():
    writeSessionState()
    renderTravelPoints()
    refreshTravelSummary()
    refreshActionButtons()
    total = len(getTravelMapPoints())
    missing = sum(1 for point in getTravelMapPoints() if not point.get("has_gps"))
    setStatus(f"轨迹加载完成：共 {total} 个点位，{missing} 个缺少 GPS。", "done")
    showPage("travel")


def onTravelError(errorMessage: str):
    writeSessionState()
    renderTravelPoints()
    refreshTravelSummary()
    refreshActionButtons()
    setStatus(f"轨迹加载失败：{errorMessage}", "error")


def loadTravelMap():
    if appState.travelStatus == "processing":
        return

    travelPhotos = getTravelPhotos()
    if not travelPhotos:
        messagebox.showwarning("无可用的照片", "请先完成识别，并确保有匹配的照片。")
        return
    if not appState.resultsRoot:
        messagebox.showwarning("缺少结果目录", "请先完成识别以确认结果目录。")
        return

    appState.travelStatus = "processing"
    appState.results["travel"] = None
    writeSessionState()
    clearTravelResults()
    refreshTravelSummary()
    refreshActionButtons()
    setStatus(f"正在提取 {len(travelPhotos)} 张照片的 GPS 信息…", "processing")

    def worker():
        try:
            result = runTravelMap(travelPhotos)
            appState.results["travel"] = result
            appState.travelStatus = "done" if result.get("success") else "error"
            root.after(0, onTravelComplete if result.get("success") else lambda: onTravelError(result.get("error", "未知错误")))
        except Exception as exc:
            appState.results["travel"] = {"success": False, "output": None, "error": str(exc)}
            appState.travelStatus = "error"
            root.after(0, lambda exc=exc: onTravelError(str(exc)))

    threading.Thread(target=worker, daemon=True).start()


def resetTravelResult():
    appState.results["travel"] = None
    appState.travelStatus = "idle"
    clearTravelResults()
    refreshTravelSummary()



def createSection(parent: tk.Widget, title: str, subtitleVar: tk.StringVar | None = None) -> tuple[tk.Frame, tk.Frame]:
    wrapper = tk.Frame(parent, bg=MAIN_BG)
    tk.Label(wrapper, text=title, bg=MAIN_BG, fg="#D1D6EB", font=(FONT_FAMILY, 15, "bold")).pack(anchor=tk.W)
    separator = tk.Frame(wrapper, bg=SECTION_LINE, height=1)
    separator.pack(fill=tk.X, pady=(8, 14))
    if subtitleVar is not None:
        tk.Label(
            wrapper,
            textvariable=subtitleVar,
            bg=MAIN_BG,
            fg=MUTED_TEXT_COLOR,
            font=(FONT_FAMILY, 12),
            justify=tk.LEFT,
            wraplength=1200,
        ).pack(anchor=tk.W, pady=(0, 12))
    body = tk.Frame(wrapper, bg=MAIN_BG)
    body.pack(fill=tk.BOTH, expand=True)
    return wrapper, body



NAV_ICONS = {
    "setup": "home",
    "find": "search",
    "highlight": "clapper",
    "travel": "mountain",
}


def createNavItem(parent: tk.Widget, key: str, label: str):
    frame = tk.Frame(parent, bg=SIDEBAR_BG, cursor="hand2")
    indicator = tk.Frame(frame, bg=SIDEBAR_BG, width=4)
    indicator.pack(side=tk.LEFT, fill=tk.Y)

    iconCanvas = tk.Canvas(frame, width=18, height=18, bg=SIDEBAR_BG, highlightthickness=0, bd=0, cursor="hand2")
    iconCanvas.pack(side=tk.LEFT, padx=(22, 0))

    def paintIcon(bg, fg):
        iconCanvas.config(bg=bg)
        iconCanvas.delete("all")
        renderIcon(iconCanvas, NAV_ICONS.get(key, "home"), 0, 0, 18, 18, fg, width=2)

    paintIcon(SIDEBAR_BG, NAV_TEXT_COLOR)

    textLabel = tk.Label(
        frame,
        text=label,
        bg=SIDEBAR_BG,
        fg=NAV_TEXT_COLOR,
        font=(FONT_FAMILY, 14),
        padx=12,
        pady=16,
        anchor="w",
        cursor="hand2",
    )
    textLabel.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def onEnter(_event):
        if key != currentPage:
            frame.config(bg=NAV_HOVER_BG)
            indicator.config(bg=NAV_HOVER_BG)
            textLabel.config(bg=NAV_HOVER_BG)
            paintIcon(NAV_HOVER_BG, TEXT_COLOR)

    def onLeave(_event):
        updateNavStyles()

    def onClick(_event):
        showPage(key)

    for widget in [frame, indicator, iconCanvas, textLabel]:
        widget.bind("<Enter>", onEnter)
        widget.bind("<Leave>", onLeave)
        widget.bind("<Button-1>", onClick)

    navWidgets[key] = {"frame": frame, "indicator": indicator, "label": textLabel, "paintIcon": paintIcon}
    return frame



def updateNavStyles():
    for key, widgets in navWidgets.items():
        active = key == currentPage
        bg = NAV_ACTIVE_BG if active else SIDEBAR_BG
        fg = TEXT_COLOR if active else NAV_TEXT_COLOR
        indicatorBg = PRIMARY_COLOR if active else bg
        widgets["frame"].config(bg=bg)
        widgets["indicator"].config(bg=indicatorBg)
        widgets["label"].config(bg=bg, fg=fg)
        iconFg = PRIMARY_COLOR if active else NAV_TEXT_COLOR
        widgets["paintIcon"](bg, iconFg)




def showPage(pageKey: str):
    global currentPage
    currentPage = pageKey
    pageFrames[pageKey].tkraise()
    refreshHeader()
    updateNavStyles()


headerFrame = tk.Frame(root, bg=MAIN_BG)
headerFrame.pack(fill=tk.BOTH, expand=True)
headerFrame.grid_columnconfigure(1, weight=1)
headerFrame.grid_rowconfigure(0, weight=1)

sidebar = tk.Frame(headerFrame, bg=SIDEBAR_BG, width=220)
sidebar.grid(row=0, column=0, sticky="ns")
sidebar.grid_propagate(False)
sidebar.grid_rowconfigure(2, weight=1)

brandWrap = tk.Frame(sidebar, bg=SIDEBAR_BG)
brandWrap.grid(row=0, column=0, sticky="ew", padx=22, pady=(28, 22))
tk.Label(brandWrap, text="FindMeApp", bg=SIDEBAR_BG, fg=TEXT_COLOR, font=(FONT_FAMILY, 22, "bold")).pack(anchor=tk.W)
tk.Label(brandWrap, text="Desktop", bg=SIDEBAR_BG, fg=MUTED_TEXT_COLOR, font=(FONT_FAMILY, 12)).pack(anchor=tk.W, pady=(4, 0))

navWrap = tk.Frame(sidebar, bg=SIDEBAR_BG)
navWrap.grid(row=1, column=0, sticky="new", padx=0)
createNavItem(navWrap, "setup", "Setup").pack(fill=tk.X)
createNavItem(navWrap, "find", "找我").pack(fill=tk.X)
createNavItem(navWrap, "highlight", "一键成片").pack(fill=tk.X)
createNavItem(navWrap, "travel", "轨迹回忆").pack(fill=tk.X)

contentWrap = tk.Frame(headerFrame, bg=MAIN_BG)
contentWrap.grid(row=0, column=1, sticky="nsew")
contentWrap.grid_rowconfigure(1, weight=1)
contentWrap.grid_columnconfigure(0, weight=1)

headerBar = tk.Frame(contentWrap, bg=TOPBAR_BG, padx=28, pady=22)
headerBar.grid(row=0, column=0, sticky="ew")
headerBar.grid_columnconfigure(0, weight=1)

titleBlock = tk.Frame(headerBar, bg=TOPBAR_BG)
titleBlock.grid(row=0, column=0, sticky="w")
tk.Label(titleBlock, textvariable=headerTitleVar, bg=TOPBAR_BG, fg=TEXT_COLOR, font=(FONT_FAMILY, 20, "bold")).pack(anchor=tk.W)
tk.Label(titleBlock, textvariable=headerSubtitleVar, bg=TOPBAR_BG, fg=MUTED_TEXT_COLOR, font=(FONT_FAMILY, 13), wraplength=900, justify=tk.LEFT).pack(anchor=tk.W, pady=(6, 0))

headerStatusLabel = tk.Label(
    headerBar,
    textvariable=statusVar,
    bg=TOPBAR_BG,
    fg=MUTED_TEXT_COLOR,
    font=(FONT_FAMILY, 12),
    justify=tk.RIGHT,
    wraplength=520,
)
headerStatusLabel.grid(row=0, column=1, sticky="e")

pagesWrap = tk.Frame(contentWrap, bg=MAIN_BG)
pagesWrap.grid(row=1, column=0, sticky="nsew")
pagesWrap.grid_rowconfigure(0, weight=1)
pagesWrap.grid_columnconfigure(0, weight=1)

setupPage = tk.Frame(pagesWrap, bg=MAIN_BG, padx=28, pady=24)
setupPage.grid(row=0, column=0, sticky="nsew")
setupPage.grid_columnconfigure(0, weight=1)
setupPage.grid_rowconfigure(0, weight=1)
setupPage.grid_rowconfigure(1, weight=0)
pageFrames["setup"] = setupPage

setupContentOuter = tk.Frame(setupPage, bg=MAIN_BG)
setupContentOuter.grid(row=0, column=0, sticky="nsew")
setupContentOuter.grid_columnconfigure(0, weight=1)
setupContentOuter.grid_rowconfigure(0, weight=1)

setupContentCanvas = tk.Canvas(setupContentOuter, bg=MAIN_BG, highlightthickness=0, bd=0)
setupContentCanvas.grid(row=0, column=0, sticky="nsew")
setupContentScrollbar = ttk.Scrollbar(setupContentOuter, orient="vertical", command=setupContentCanvas.yview)
setupContentScrollbar.grid(row=0, column=1, sticky="ns")
setupContentCanvas.configure(yscrollcommand=setupContentScrollbar.set)

setupContent = tk.Frame(setupContentCanvas, bg=MAIN_BG)
setupContentWindow = setupContentCanvas.create_window((0, 0), window=setupContent, anchor="nw")
setupContent.grid_columnconfigure(0, weight=1)

def _onSetupContentConfigure(_event):
    setupContentCanvas.configure(scrollregion=setupContentCanvas.bbox("all"))

def _onSetupContentCanvasConfigure(event):
    setupContentCanvas.itemconfig(setupContentWindow, width=event.width)

setupContent.bind("<Configure>", _onSetupContentConfigure)
setupContentCanvas.bind("<Configure>", _onSetupContentCanvasConfigure)

def _onMouseWheel(event):
    if setupContentCanvas.bbox("all") is None:
        return
    setupContentCanvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

def _bindMouseWheel(widget):
    widget.bind("<MouseWheel>", _onMouseWheel)
    for child in widget.winfo_children():
        _bindMouseWheel(child)

_bindMouseWheel(setupContentCanvas)
setupContentCanvas.bind("<Enter>", lambda _e: setupContentCanvas.bind_all("<MouseWheel>", _onMouseWheel))
setupContentCanvas.bind("<Leave>", lambda _e: setupContentCanvas.unbind_all("<MouseWheel>"))

setupStep1, setupStep1Body = createSection(setupContent, "第一步 - 参考自拍 (1-3 张)")
setupStep1.pack(fill=tk.X, padx=(0, 8))
referenceUploadPanel = UploadPanel(setupStep1Body, PRIMARY_COLOR, lambda: selectReferences(), lambda paths: selectReferences(paths), icon="camera")

referenceUploadPanel.frame.pack(fill=tk.X)
referenceThumbStrip = tk.Frame(setupStep1Body, bg=MAIN_BG)
referenceThumbStrip.pack(fill=tk.X, pady=(14, 0))

setupStep2, setupStep2Body = createSection(setupContent, "第二步 - 要搜索的素材")
setupStep2.pack(fill=tk.X, pady=(26, 0), padx=(0, 8))
mediaUploadPanel = UploadPanel(setupStep2Body, SECONDARY_DASH_COLOR, lambda: selectMediaItems(), lambda paths: selectMediaItems(paths), icon="folder")

mediaUploadPanel.frame.pack(fill=tk.X)

setupBottom = tk.Frame(setupPage, bg=MAIN_BG)
setupBottom.grid(row=1, column=0, sticky="ew", pady=(24, 0))
setupBottom.grid_columnconfigure(0, weight=1)

setupActions = tk.Frame(setupBottom, bg=MAIN_BG)
setupActions.grid(row=0, column=0, sticky="ew")
actionBar = tk.Frame(setupActions, bg=PANEL_ALT_BG, padx=18, pady=16, highlightthickness=1)
actionBar.config(highlightbackground=SECTION_LINE, highlightcolor=SECTION_LINE)
actionBar.pack(anchor=tk.W, fill=tk.X)
findButton = RoundedButton(actionBar, "开始识别", runFindMe, primary=True, icon="search", width=150)
findButton.pack(side=tk.LEFT)

tk.Label(
    actionBar,
    textvariable=findButtonHintVar,
    bg=PANEL_ALT_BG,
    fg=MUTED_TEXT_COLOR,
    font=(FONT_FAMILY, 12),
    justify=tk.LEFT,
).pack(side=tk.LEFT, padx=(16, 0))



setupSummary = tk.Frame(setupBottom, bg=MAIN_BG)
setupSummary.grid(row=1, column=0, sticky="ew", pady=(18, 0))
for variable in [refsSummaryVar, mediaSummaryVar, mediaTypeSummaryVar, matchedVar, sessionVar, resultsDirVar]:
    tk.Label(setupSummary, textvariable=variable, bg=MAIN_BG, fg=MUTED_TEXT_COLOR, font=(FONT_FAMILY, 12), anchor="w", justify=tk.LEFT).pack(fill=tk.X, pady=2)

findPage = tk.Frame(pagesWrap, bg=MAIN_BG, padx=28, pady=24)
findPage.grid(row=0, column=0, sticky="nsew")
pageFrames["find"] = findPage

photoSection, photoSectionBody = createSection(findPage, "我的照片", photoStatVar)
photoSection.pack(fill=tk.X)

photoActionBar = tk.Frame(photoSectionBody, bg=MAIN_BG)
photoActionBar.pack(fill=tk.X, pady=(0, 12))
saveAllPhotosBtn = RoundedButton(photoActionBar, "全部另存为", saveAllMatchedPhotos, primary=True, icon="folder", width=130)
saveAllPhotosBtn.pack(side=tk.LEFT)
openSavedDirBtn = RoundedButton(photoActionBar, "打开保存目录", openSavedPhotosDir, primary=False, icon="folder", width=140)
openSavedDirBtn.pack(side=tk.LEFT, padx=(10, 0))

photoCard = tk.Frame(photoSectionBody, bg=PANEL_BG, padx=16, pady=16)
photoCard.pack(fill=tk.X)
photoResultsBody = tk.Frame(photoCard, bg=PANEL_BG)
photoResultsBody.pack(fill=tk.X)

clipSection, clipSectionBody = createSection(findPage, "我的视频片段", clipStatVar)
clipSection.pack(fill=tk.X, pady=(20, 0))
clipCard = tk.Frame(clipSectionBody, bg=PANEL_BG, padx=16, pady=16)
clipCard.pack(fill=tk.X)
clipResultsBody = tk.Frame(clipCard, bg=PANEL_BG)
clipResultsBody.pack(fill=tk.X)

highlightPage = tk.Frame(pagesWrap, bg=MAIN_BG, padx=28, pady=24)
highlightPage.grid(row=0, column=0, sticky="nsew")
pageFrames["highlight"] = highlightPage

highlightActions = tk.Frame(highlightPage, bg=MAIN_BG)
highlightActions.pack(anchor=tk.W)
highlightButton = RoundedButton(highlightActions, "生成高光视频", generateHighlight, primary=True, icon="clapper", width=180)
highlightButton.pack(side=tk.LEFT)

openResultsButton = RoundedButton(highlightActions, "打开结果文件夹", openResultsFolder, primary=False, icon="folder", width=150)
openResultsButton.pack(side=tk.LEFT, padx=(12, 0))

tk.Label(
    highlightPage,
    textvariable=highlightVar,
    bg=MAIN_BG,
    fg=MUTED_TEXT_COLOR,
    font=(FONT_FAMILY, 12),
    justify=tk.LEFT,
    wraplength=1200,
).pack(anchor=tk.W, pady=(18, 18))

previewCard = tk.Frame(highlightPage, bg=PANEL_BG, padx=18, pady=18)
previewCard.pack(fill=tk.BOTH, expand=True)
previewCard.grid_rowconfigure(0, weight=1)
previewCard.grid_columnconfigure(0, weight=1)

videoLabel = tk.Label(
    previewCard,
    text="高光视频将在这里播放",
    bg=LIGHT_PANEL_BG,
    fg=LIGHT_PANEL_TEXT,
    anchor="center",
    justify=tk.CENTER,
    height=20,
    highlightthickness=1,
)
videoLabel.config(highlightbackground=LIGHT_PANEL_BORDER, highlightcolor=LIGHT_PANEL_BORDER)
videoLabel.grid(row=0, column=0, sticky="nsew")

videoProgressWrap = tk.Frame(previewCard, bg=PANEL_BG)
videoProgressWrap.grid(row=1, column=0, sticky="ew", pady=(14, 0))
videoProgressWrap.grid_columnconfigure(0, weight=1)

progressStyle = ttk.Style(root)
try:
    progressStyle.theme_use("clam")
except Exception:
    pass
progressStyle.configure(
    "Desk.Horizontal.TProgressbar",
    troughcolor=MAIN_BG,
    bordercolor=MAIN_BG,
    background=PRIMARY_COLOR,
    lightcolor=PRIMARY_COLOR,
    darkcolor=PRIMARY_COLOR,
)
videoProgress = ttk.Progressbar(videoProgressWrap, style="Desk.Horizontal.TProgressbar", variable=videoProgressVar, maximum=100)
videoProgress.grid(row=0, column=0, sticky="ew")
tk.Label(videoProgressWrap, textvariable=videoProgressTextVar, bg=PANEL_BG, fg=MUTED_TEXT_COLOR, font=(FONT_FAMILY, 11)).grid(row=1, column=0, sticky="e", pady=(6, 0))

videoControls = tk.Frame(previewCard, bg=PANEL_BG)
videoControls.grid(row=2, column=0, sticky="w", pady=(16, 0))
saveVideoButton = RoundedButton(videoControls, "另存高光视频", saveHighlightVideo, primary=False, icon="folder", width=150)
saveVideoButton.pack(side=tk.LEFT, padx=(0, 10))
playVideoButton = RoundedButton(videoControls, "播放高光视频", toggleVideoPlayback, primary=True, icon="camera", width=150)
playVideoButton.pack(side=tk.LEFT)

travelPage = tk.Frame(pagesWrap, bg=MAIN_BG, padx=28, pady=24)
travelPage.grid(row=0, column=0, sticky="nsew")
pageFrames["travel"] = travelPage
travelPage.grid_columnconfigure(0, weight=1)
travelPage.grid_rowconfigure(2, weight=1)

travelActions = tk.Frame(travelPage, bg=MAIN_BG)
travelActions.grid(row=0, column=0, sticky="ew")
loadTravelButton = RoundedButton(travelActions, "加载轨迹数据", loadTravelMap, primary=True, icon="mountain", width=160)
loadTravelButton.pack(side=tk.LEFT)
reloadTravelButton = RoundedButton(travelActions, "重新加载", loadTravelMap, primary=False, icon="search", width=120)
reloadTravelButton.pack(side=tk.LEFT, padx=(10, 0))
openTravelResultsBtn = RoundedButton(travelActions, "打开结果文件夹", openResultsFolder, primary=False, icon="folder", width=150)
openTravelResultsBtn.pack(side=tk.LEFT, padx=(10, 0))

travelStatFrame = tk.Frame(travelPage, bg=MAIN_BG)
travelStatFrame.grid(row=1, column=0, sticky="ew", pady=(16, 0))
tk.Label(
    travelStatFrame,
    textvariable=travelStatVar,
    bg=MAIN_BG,
    fg=TEXT_COLOR,
    font=(FONT_FAMILY, 13, "bold"),
    anchor="w",
    justify=tk.LEFT,
).pack(fill=tk.X)
tk.Label(
    travelStatFrame,
    textvariable=travelSummaryVar,
    bg=MAIN_BG,
    fg=MUTED_TEXT_COLOR,
    font=(FONT_FAMILY, 12),
    anchor="w",
    justify=tk.LEFT,
).pack(fill=tk.X, pady=(4, 0))
tk.Label(
    travelStatFrame,
    textvariable=travelHintVar,
    bg=MAIN_BG,
    fg=SUBTLE_TEXT_COLOR,
    font=(FONT_FAMILY, 11),
    anchor="w",
    justify=tk.LEFT,
    wraplength=1200,
).pack(fill=tk.X, pady=(4, 0))

travelSection, travelSectionBody = createSection(travelPage, "轨迹点位（按时间顺序）")
travelSection.grid(row=2, column=0, sticky="nsew")
travelSection.grid_rowconfigure(0, weight=1)
travelSection.grid_columnconfigure(0, weight=1)

travelScrollOuter = tk.Frame(travelSectionBody, bg=MAIN_BG)
travelScrollOuter.pack(fill=tk.BOTH, expand=True)
travelScrollOuter.grid_rowconfigure(0, weight=1)
travelScrollOuter.grid_columnconfigure(0, weight=1)

travelCanvas = tk.Canvas(travelScrollOuter, bg=PANEL_BG, highlightthickness=0, bd=0)
travelCanvas.grid(row=0, column=0, sticky="nsew")
travelScrollbar = ttk.Scrollbar(travelScrollOuter, orient="vertical", command=travelCanvas.yview)
travelScrollbar.grid(row=0, column=1, sticky="ns")
travelCanvas.configure(yscrollcommand=travelScrollbar.set)

travelResultsBody = tk.Frame(travelCanvas, bg=PANEL_BG)
travelResultsWindow = travelCanvas.create_window((0, 0), window=travelResultsBody, anchor="nw")
travelResultsBody.bind(
    "<Configure>",
    lambda _e: travelCanvas.configure(scrollregion=travelCanvas.bbox("all")),
)
travelCanvas.bind(
    "<Configure>",
    lambda e: travelCanvas.itemconfig(travelResultsWindow, width=e.width),
)


def _onTravelMouseWheel(event):
    if travelCanvas.bbox("all") is None:
        return
    travelCanvas.yview_scroll(int(-1 * (event.delta / 120)), "units")


travelCanvas.bind("<Enter>", lambda _e: travelCanvas.bind_all("<MouseWheel>", _onTravelMouseWheel))
travelCanvas.bind("<Leave>", lambda _e: travelCanvas.unbind_all("<MouseWheel>"))

refreshSummaryLabels()
refreshUploadPanels()
displayReferenceThumbnails()
renderResults()
refreshHighlightSummary()
showVideoPreview()
refreshActionButtons()
setStatus(statusVar.get(), statusTone)
showPage(currentPage)

root.protocol("WM_DELETE_WINDOW", lambda: (stopVideoPlayback(), root.destroy()))
root.mainloop()
