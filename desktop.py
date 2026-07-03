#!/usr/bin/env python3
"""desktop.py — FindMeApp 桌面版入口.

运行方式:
    python desktop.py

基本功能:
- 选择 1-3 张参考自拍
- 选择待识别图片文件夹（递归子文件夹）
- 识别匹配参考人脸的图片并保存到结果文件夹
- 高亮视频可另存到本地
"""

import os
import shutil
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

from PIL import Image, ImageTk

from src.config import MAX_HIGHLIGHT_PHOTOS
from src.playbooks.buildHighlight import runBuildHighlight
from src.playbooks.findPhotos import runFindPhotos

PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".webp", ".bmp", ".tif", ".tiff"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".m4v"}

root = tk.Tk()
root.title("FindMeApp Desk")
root.geometry("1000x680")
root.configure(bg="#0f3c6d")
root.resizable(True, True)

# State
reference_paths: list[Path] = []
target_folder: Path | None = None
matched_paths: list[Path] = []
highlight_path: Path | None = None
results_root: Path | None = None
image_preview_refs: list[ImageTk.PhotoImage] = []

status_var = tk.StringVar(value="请选择参考图像和目标文件夹，即可开始识别。")
refs_var = tk.StringVar(value="未选择参考图像")
target_var = tk.StringVar(value="未选择目标文件夹")
matched_var = tk.StringVar(value="匹配结果: 0 张")
results_dir_var = tk.StringVar(value="结果文件夹: -")
highlight_count_var = tk.StringVar(value=str(MAX_HIGHLIGHT_PHOTOS))


def set_status(message: str, is_error: bool = False):
    status_var.set(message)
    if is_error:
        status_label.config(fg="#ffdddd")
    else:
        status_label.config(fg="#ffffff")


def select_references():
    global reference_paths, results_root, highlight_path
    paths = filedialog.askopenfilenames(
        title="选择 1-3 张参考图像",
        filetypes=[("Image files", "*.jpg *.jpeg *.png *.heic *.webp *.bmp *.tif *.tiff")],
    )
    if not paths:
        return
    if len(paths) > 3:
        messagebox.showwarning("参考图像限制", "只能选择最多 3 张参考图像。")
        return
    reference_paths = [Path(p) for p in paths]
    ref_dirs = {p.parent for p in reference_paths}
    if len(ref_dirs) > 1:
        results_root = sorted(ref_dirs)[0].parent / "results"
        set_status("参考图像来自多个文件夹，结果将保存到第一个参考图像所在目录的同级 results 文件夹。")
    else:
        ref_dir = next(iter(ref_dirs))
        results_root = ref_dir.parent / "results"
    refs_var.set(f"参考图像: {len(reference_paths)} 张")
    results_dir_var.set(f"结果文件夹: {results_root}")
    matched_paths.clear()
    highlight_path = None
    matched_var.set("匹配结果: 0 张")
    clear_match_list()
    refresh_action_buttons()


def select_target_folder():
    global target_folder
    initial_dir = None
    if reference_paths:
        ref_dirs = {p.parent for p in reference_paths}
        initial_dir = str(sorted(ref_dirs)[0])
    folder = filedialog.askdirectory(title="选择待识别图片文件夹", initialdir=initial_dir)
    if not folder:
        return
    target_folder = Path(folder)
    target_var.set(f"目标文件夹: {target_folder}")
    set_status("已选择目标文件夹。现在可开始识别。")


def scan_image_files(folder: Path) -> list[Path]:
    paths = []
    for path in folder.rglob("*"):
        if path.is_file() and path.suffix.lower() in PHOTO_EXTS:
            paths.append(path)
    return sorted(paths)


def get_results_root() -> Path:
    if results_root is None:
        raise RuntimeError("结果文件夹未初始化")
    results_root.mkdir(parents=True, exist_ok=True)
    return results_root


def refresh_action_buttons():
    global matched_paths, highlight_path
    if highlight_button is None or save_video_button is None:
        return
    highlight_button.config(state=tk.NORMAL if matched_paths else tk.DISABLED)
    save_video_button.config(state=tk.NORMAL if highlight_path and Path(highlight_path).exists() else tk.DISABLED)


def update_highlight_selector():
    max_count = min(MAX_HIGHLIGHT_PHOTOS, len(matched_paths)) if matched_paths else MAX_HIGHLIGHT_PHOTOS
    if max_count <= 0:
        max_count = 1
    if highlight_count_spinbox is not None:
        highlight_count_spinbox.config(from_=1, to=max_count)
    if highlight_count_var.get() == "" or int(highlight_count_var.get()) > max_count:
        highlight_count_var.set(str(max_count))


def clear_match_list():
    match_listbox.delete(0, tk.END)
    for child in preview_content.winfo_children():
        child.destroy()
    preview_label.config(text="选中图片将显示大图", image="")
    image_preview_refs.clear()


def display_matches(paths: list[Path]):
    clear_match_list()
    for p in paths:
        match_listbox.insert(tk.END, p.name)
    matched_var.set(f"匹配结果: {len(paths)} 张")
    render_match_thumbnails(paths)
    if paths:
        show_preview(paths[0])
    refresh_action_buttons()


def render_match_thumbnails(paths: list[Path]):
    for idx, path in enumerate(paths):
        thumb_frame = tk.Frame(preview_content, bg="#ffffff", padx=8, pady=8)
        thumb_frame.grid(row=idx // 2, column=idx % 2, sticky="n", padx=6, pady=6)
        try:
            img = Image.open(path)
            img.thumbnail((180, 180))
            photo = ImageTk.PhotoImage(img)
            thumb_label = tk.Label(thumb_frame, image=photo, bg="#ffffff")
            thumb_label.image = photo
            thumb_label.pack()
            image_preview_refs.append(photo)
        except Exception as exc:
            tk.Label(thumb_frame, text=f"无法预览\n{exc}", bg="#ffffff", wraplength=140).pack()
        tk.Label(thumb_frame, text=path.name, bg="#ffffff", wraplength=150, justify="center").pack(pady=(4, 0))


def show_preview(path: Path):
    try:
        img = Image.open(path)
        img.thumbnail((320, 320))
        photo = ImageTk.PhotoImage(img)
        image_preview_refs.clear()
        image_preview_refs.append(photo)
        preview_label.config(image=photo, text="")
    except Exception as exc:
        preview_label.config(text=f"无法预览: {exc}", image="")


def on_match_select(event):
    selection = match_listbox.curselection()
    if not selection or not matched_paths:
        return
    idx = selection[0]
    if idx >= len(matched_paths):
        return
    path = matched_paths[idx]
    show_preview(path)


def run_find_me():
    global matched_paths, highlight_path
    if not reference_paths:
        messagebox.showwarning("缺少参考图像", "请先选择至少一张参考图像。")
        return
    if not target_folder or not target_folder.exists():
        messagebox.showwarning("缺少目标文件夹", "请先选择待识别图片文件夹。")
        return
    if not results_root:
        messagebox.showwarning("缺少结果目录", "无法确定结果文件夹，请重新选择参考图像。")
        return

    images = scan_image_files(target_folder)
    if not images:
        messagebox.showwarning("未找到图片", "目标文件夹中未找到任何可识别的图片文件。")
        return

    out_dir = get_results_root() / "my_photos"
    set_status("正在识别，请稍候...", is_error=False)
    find_button.config(state=tk.DISABLED)
    highlight_button.config(state=tk.DISABLED)
    save_video_button.config(state=tk.DISABLED)
    open_results_button.config(state=tk.DISABLED)

    def worker():
        nonlocal images
        global highlight_path, matched_paths
        try:
            result = runFindPhotos([str(p) for p in reference_paths], [str(p) for p in images], str(out_dir))
            if not result["success"]:
                raise RuntimeError(result.get("error", "识别失败"))
            matched = [Path(p) for p in result["output"]["matched_paths"]]
            matched_paths = matched
            highlight_path = None
            root.after(0, lambda: display_matches(matched_paths))
            root.after(0, lambda: set_status(f"识别完成: 共扫描 {len(images)} 张图片，匹配 {len(matched_paths)} 张。结果已保存到 {out_dir}"))
            root.after(0, lambda: update_highlight_selector())
            root.after(0, lambda: refresh_action_buttons())
            root.after(0, lambda: open_results_button.config(state=tk.NORMAL))
        except Exception as exc:
            root.after(0, lambda exc=exc: set_status(f"识别失败: {exc}", is_error=True))
        finally:
            root.after(0, lambda: find_button.config(state=tk.NORMAL))

    threading.Thread(target=worker, daemon=True).start()


def generate_highlight():
    global highlight_path
    if not matched_paths:
        messagebox.showwarning("无匹配结果", "请先完成识别并确认有匹配图片。")
        return
    if not results_root:
        messagebox.showwarning("缺少结果目录", "请先重新选择参考图像以确认结果目录。")
        return

    highlight_dir = get_results_root() / "highlight"
    selected_count = min(MAX_HIGHLIGHT_PHOTOS, len(matched_paths))
    try:
        selected_count = int(highlight_count_var.get())
    except ValueError:
        selected_count = min(MAX_HIGHLIGHT_PHOTOS, len(matched_paths))
    selected_count = max(1, min(selected_count, len(matched_paths), MAX_HIGHLIGHT_PHOTOS))

    set_status(f"正在生成高光视频（共 {selected_count} 张），请稍候...", is_error=False)
    highlight_button.config(state=tk.DISABLED)
    save_video_button.config(state=tk.DISABLED)
    open_results_button.config(state=tk.DISABLED)
    root.update_idletasks()

    def worker():
        global highlight_path
        try:
            result = runBuildHighlight(
                [str(p) for p in matched_paths[:selected_count]],
                [],
                str(highlight_dir),
                audioPath=None,
            )
            if not result["success"]:
                raise RuntimeError(result.get("error", "高光生成失败"))
            highlight_path = Path(result["output"]["highlight_video_path"])
            root.after(0, lambda: set_status(f"高光生成完成: {highlight_path}"))
            root.after(0, lambda: refresh_action_buttons())
            root.after(0, lambda: open_results_button.config(state=tk.NORMAL))
        except Exception as exc:
            root.after(0, lambda: set_status(f"高光生成失败: {exc}", is_error=True))
        finally:
            root.after(0, lambda: highlight_button.config(state=tk.NORMAL))

    threading.Thread(target=worker, daemon=True).start()


def save_highlight_video():
    if not highlight_path or not highlight_path.exists():
        messagebox.showwarning("无高光视频", "请先生成高光视频。")
        return
    dest = filedialog.asksaveasfilename(
        title="另存为高光视频",
        defaultextension=".mp4",
        filetypes=[("MP4 视频", "*.mp4")],
        initialfile=highlight_path.name,
    )
    if not dest:
        return
    try:
        shutil.copy2(str(highlight_path), dest)
        set_status(f"高光视频已另存为: {dest}")
    except Exception as exc:
        messagebox.showerror("保存失败", f"无法保存高光视频: {exc}")


def open_results_folder():
    if not results_root:
        messagebox.showwarning("无结果目录", "请先完成识别以创建结果目录。")
        return
    path = results_root.resolve()
    if not path.exists():
        messagebox.showwarning("结果不存在", "结果目录尚未创建。")
        return
    if os.name == "nt":
        os.startfile(path)
    elif sys.platform == "darwin":
        os.system(f"open '{path}'")
    else:
        os.system(f"xdg-open '{path}'")


# UI layout
frame_left = tk.Frame(root, bg="#112f5d", bd=0, padx=14, pady=14, width=220)
frame_left.pack_propagate(False)
frame_left.pack(side=tk.LEFT, fill=tk.Y, padx=12, pady=12)
frame_right = tk.Frame(root, bg="#163f78", bd=0, padx=14, pady=14)
frame_right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=12, pady=12)

logo = tk.Label(frame_left, text="FindMeApp 桌面版", font=("Helvetica", 18, "bold"), bg="#112f5d", fg="#f2f8ff")
logo.pack(anchor=tk.W, pady=(0, 10))

btn_ref = tk.Button(frame_left, text="选择参考图像 (1-3 张)", command=select_references, width=24, bg="#7a1521", fg="#ffffff", activebackground="#8e1d28", activeforeground="#ffffff", disabledforeground="#ffffff", relief="flat", bd=0, padx=10, pady=8, font=("Helvetica", 12, "bold"), highlightthickness=0)
btn_ref.pack(fill=tk.X, pady=4)

btn_target = tk.Button(frame_left, text="选择待识别文件夹", command=select_target_folder, width=24, bg="#7a1521", fg="#ffffff", activebackground="#8e1d28", activeforeground="#ffffff", disabledforeground="#ffffff", relief="flat", bd=0, padx=10, pady=8, font=("Helvetica", 12, "bold"), highlightthickness=0)
btn_target.pack(fill=tk.X, pady=4)

find_button = tk.Button(frame_left, text="开始识别", command=run_find_me, width=24, bg="#7a1521", fg="#ffffff", activebackground="#8e1d28", activeforeground="#ffffff", disabledforeground="#ffffff", relief="flat", bd=0, padx=10, pady=8, font=("Helvetica", 12, "bold"), highlightthickness=0)
find_button.pack(fill=tk.X, pady=16)

highlight_button = tk.Button(frame_left, text="生成高光视频", command=generate_highlight, width=24, bg="#7a1521", fg="#ffffff", activebackground="#8e1d28", activeforeground="#ffffff", disabledforeground="#ffffff", relief="flat", bd=0, padx=10, pady=8, font=("Helvetica", 12, "bold"), highlightthickness=0, state=tk.DISABLED)
highlight_button.pack(fill=tk.X, pady=4)

highlight_count_frame = tk.Frame(frame_left, bg="#112f5d")
highlight_count_frame.pack(fill=tk.X, pady=(2, 6))
tk.Label(highlight_count_frame, text="照片数量（最多 20）", bg="#112f5d", fg="#ffffff", font=("Helvetica", 10)).pack(anchor=tk.W)
highlight_count_spinbox = tk.Spinbox(highlight_count_frame, from_=1, to=MAX_HIGHLIGHT_PHOTOS, textvariable=highlight_count_var, width=8, justify=tk.CENTER)
highlight_count_spinbox.pack(anchor=tk.W, pady=(2, 0))

save_video_button = tk.Button(frame_left, text="另存高光视频", command=save_highlight_video, width=24, bg="#7a1521", fg="#ffffff", activebackground="#8e1d28", activeforeground="#ffffff", disabledforeground="#ffffff", relief="flat", bd=0, padx=10, pady=8, font=("Helvetica", 12, "bold"), highlightthickness=0, state=tk.DISABLED)
save_video_button.pack(fill=tk.X, pady=4)

open_results_button = tk.Button(frame_left, text="打开结果文件夹", command=open_results_folder, width=24, bg="#7a1521", fg="#ffffff", activebackground="#8e1d28", activeforeground="#ffffff", disabledforeground="#ffffff", relief="flat", bd=0, padx=10, pady=8, font=("Helvetica", 12, "bold"), highlightthickness=0, state=tk.DISABLED)
open_results_button.pack(fill=tk.X, pady=4)

status_label = tk.Label(frame_left, textvariable=status_var, bg="#112f5d", fg="#ffffff", wraplength=240, justify=tk.LEFT)
status_label.pack(fill=tk.X, pady=(24, 0))

info_frame = tk.Frame(frame_left, bg="#112f5d")
info_frame.pack(fill=tk.X, pady=(20, 0))

label_refs = tk.Label(info_frame, textvariable=refs_var, anchor=tk.W, bg="#112f5d", fg="#f2f8ff")
label_refs.pack(fill=tk.X, pady=2)
label_target = tk.Label(info_frame, textvariable=target_var, anchor=tk.W, bg="#112f5d", fg="#f2f8ff")
label_target.pack(fill=tk.X, pady=2)
label_results_dir = tk.Label(info_frame, textvariable=results_dir_var, anchor=tk.W, bg="#112f5d", fg="#f2f8ff")
label_results_dir.pack(fill=tk.X, pady=2)
label_matched = tk.Label(info_frame, textvariable=matched_var, anchor=tk.W, bg="#112f5d", fg="#f2f8ff")
label_matched.pack(fill=tk.X, pady=2)

# Right side: match list + preview
right_top = tk.Label(frame_right, text="匹配结果预览", font=("Helvetica", 14, "bold"), bg="#163f78", fg="#f2f8ff")
right_top.pack(anchor=tk.W)

list_frame = tk.Frame(frame_right, bg="#163f78")
list_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 6))

match_listbox = tk.Listbox(list_frame, bg="#eaf2fb", fg="#0f3c6d", selectbackground="#bfd8ff", activestyle="none")
match_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
match_listbox.bind("<<ListboxSelect>>", on_match_select)

scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL, command=match_listbox.yview)
scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
match_listbox.config(yscrollcommand=scrollbar.set)

preview_frame = tk.Frame(frame_right, bg="#bfdcff", bd=1, relief=tk.SOLID)
preview_frame.pack(fill=tk.BOTH, expand=True, pady=(6, 0))

preview_label = tk.Label(preview_frame, text="选择匹配结果以预览图片", bg="#bfdcff", fg="#0f3c6d", anchor="center")
preview_label.pack(fill=tk.X, padx=8, pady=(8, 6))

preview_canvas = tk.Canvas(preview_frame, bg="#eaf2fb", highlightthickness=0)
preview_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

preview_scrollbar = tk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=preview_canvas.yview)
preview_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
preview_canvas.configure(yscrollcommand=preview_scrollbar.set)

preview_content = tk.Frame(preview_canvas, bg="#ffffff")
preview_window_id = preview_canvas.create_window((0, 0), window=preview_content, anchor="nw")
preview_canvas.bind("<Configure>", lambda event: preview_canvas.itemconfig(preview_window_id, width=event.width))
preview_content.bind("<Configure>", lambda event: preview_canvas.configure(scrollregion=preview_canvas.bbox("all")))

root.mainloop()
