# -*- coding: utf-8 -*-
"""
PyInstaller 运行时钩子（仅 Windows 打包后生效）。

在任何业务代码导入 onnxruntime 之前执行，做两件事：

1. 修复（fix）
   显式调用 os.add_dll_directory() 把 onnxruntime/capi 与 _internal 根目录
   加入本进程的 DLL 搜索路径。onnxruntime_pybind11_state.pyd 在初始化时会
   从同目录加载 onnxruntime.dll / onnxruntime_providers_shared.dll，某些
   Windows 机器上仅依赖 bootloader 的默认搜索行为不稳定。

2. 取证（diagnose）
   预热 import onnxruntime；无论成功/失败，都把详细信息写入：
     - 控制台（console 窗口 stderr）
     - %LOCALAPPDATA%\\FindMeApp\\ort_diag.log
   失败时用与 CPython 相同的 LoadLibraryEx 标志逐个探测关键 DLL，
   直接打印真正缺失的那个 DLL 名字和 WinError（insightface 只会笼统地
   抛 "Unable to import dependency onnxruntime."，把真实原因吞掉）。

本文件只允许使用标准库（运行时钩子早于业务模块加载）。
"""
import os
import sys
import traceback


def _logPath():
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        base = os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(base, "FindMeApp", "ort_diag.log")


def _emit(lines):
    text = "\n".join(lines)
    try:
        print(text, file=sys.stderr, flush=True)
    except Exception:
        pass
    try:
        p = _logPath()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(text + "\n")
    except Exception:
        pass


def _probeDll(label, fullPath):
    """用 LoadLibraryExW 以 CPython 加载扩展同款标志探测单个 DLL。"""
    import ctypes
    LOAD_LIBRARY_SEARCH_DEFAULT_DIRS = 0x1000
    LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR = 0x0100
    flags = LOAD_LIBRARY_SEARCH_DEFAULT_DIRS | LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR
    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        k32.LoadLibraryExW.restype = ctypes.c_void_p
        k32.LoadLibraryExW.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint32]
        handle = k32.LoadLibraryExW(fullPath, None, flags)
        if handle:
            return f"  [OK]      {label}: {fullPath}"
        err = ctypes.get_last_error()
        return f"  [FAIL]    {label}: {fullPath}  WinError={err}"
    except Exception as e:
        return f"  [FAIL]    {label}: {fullPath}  {type(e).__name__}: {e}"


def _run():
    if not getattr(sys, "frozen", False):
        return
    if sys.platform != "win32":
        return

    meipass = getattr(sys, "_MEIPASS", "")
    capiDir = os.path.join(meipass, "onnxruntime", "capi")

    lines = [
        "=" * 70,
        "[ort-diag] onnxruntime 启动诊断",
        f"[ort-diag] python={sys.version}",
        f"[ort-diag] sys._MEIPASS={meipass}",
        f"[ort-diag] capiDir={capiDir} (exists={os.path.isdir(capiDir)})",
    ]

    # ---- 1) 加固 DLL 搜索路径 ----
    for d in (capiDir, meipass):
        if d and os.path.isdir(d):
            try:
                os.add_dll_directory(d)
                lines.append(f"[ort-diag] AddDllDirectory OK: {d}")
            except Exception as e:
                lines.append(f"[ort-diag] AddDllDirectory FAIL {d}: {e!r}")

    # ---- 2) 预热导入 onnxruntime ----
    try:
        import onnxruntime as ort
        pydPath = getattr(ort, "onnxruntime_pybind11_state", None)
        lines += [
            "[ort-diag] >>> import onnxruntime 成功 <<<",
            f"[ort-diag] version={ort.__version__}",
            f"[ort-diag] file={ort.__file__}",
            f"[ort-diag] providers={ort.get_available_providers()}",
        ]
        _emit(lines)
        return
    except BaseException:
        lines += [
            "[ort-diag] >>> import onnxruntime 失败，完整异常链如下 <<<",
            traceback.format_exc().rstrip(),
        ]

    # ---- 3) 失败时逐个探测关键原生库 ----
    try:
        lines.append("[ort-diag] ---- 关键 DLL 逐个加载探测 ----")
        if os.path.isdir(capiDir):
            for name in sorted(os.listdir(capiDir)):
                lines.append(f"  capi/{name}")
        targets = [
            ("pyd  扩展本体", os.path.join(capiDir, "onnxruntime_pybind11_state.pyd")),
            ("ort  核心库  ", os.path.join(capiDir, "onnxruntime.dll")),
            ("共享 provider", os.path.join(capiDir, "onnxruntime_providers_shared.dll")),
            ("VC 运行库    ", os.path.join(meipass, "MSVCP140.dll")),
            ("VC 运行库1   ", os.path.join(meipass, "MSVCP140_1.dll")),
            ("VC 运行时1   ", os.path.join(meipass, "VCRUNTIME140_1.dll")),
        ]
        for label, p in targets:
            lines.append(_probeDll(label, p))
        lines.append(f"[ort-diag] PATH={os.environ.get('PATH', '')}")
    except Exception:
        lines.append("[ort-diag] 探测过程自身异常:\n" + traceback.format_exc())

    _emit(lines)


_run()
