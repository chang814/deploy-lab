"""P0-5 输入显示层：一个置顶的小窗口，按下 1/2/3/Q/F、滚轮、左右键时对应的格子会亮起。

用「显示器采集」录屏时，它和游戏画面出现在同一帧里，所以能从录像中直接读出按键时刻。
同时把每次按键的毫秒时间戳写入 CSV，用于交叉核对。

实现：另开一个线程，用 Windows Raw Input（RIDEV_INPUTSINK）被动接收键盘和鼠标输入。
它不注入、不 hook、不读取任何其他进程（包括 CS2），只依赖 Python 标准库。

用法：
    python -I input_overlay.py [--csv 路径]
窗口可以用鼠标拖动；点右上角的 × 关闭。
"""

import argparse
import ctypes
import datetime
import os
import sys
import threading
import time
import tkinter as tk
from ctypes import wintypes

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from overlay_state import KEYS, LockedCsvLog, OverlayState, decode_keyboard, decode_mouse  # noqa: E402

if sys.platform != "win32":
    sys.exit("只支持 Windows")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_INPUT = 0x00FF
WM_QUIT = 0x0012
RID_INPUT = 0x10000003
RIM_TYPEMOUSE, RIM_TYPEKEYBOARD = 0, 1
RIDEV_INPUTSINK = 0x00000100

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", wintypes.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", wintypes.HINSTANCE), ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE), ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR), ("lpszClassName", wintypes.LPCWSTR)]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [("usUsagePage", wintypes.USHORT), ("usUsage", wintypes.USHORT),
                ("dwFlags", wintypes.DWORD), ("hwndTarget", wintypes.HWND)]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [("dwType", wintypes.DWORD), ("dwSize", wintypes.DWORD),
                ("hDevice", wintypes.HANDLE), ("wParam", wintypes.WPARAM)]


class _Btn(ctypes.Structure):
    _fields_ = [("usButtonFlags", wintypes.USHORT), ("usButtonData", wintypes.USHORT)]


class _BtnU(ctypes.Union):
    _anonymous_ = ("s",)
    _fields_ = [("ulButtons", wintypes.ULONG), ("s", _Btn)]


class RAWMOUSE(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("usFlags", wintypes.USHORT), ("u", _BtnU), ("ulRawButtons", wintypes.ULONG),
                ("lLastX", wintypes.LONG), ("lLastY", wintypes.LONG), ("ulExtraInformation", wintypes.ULONG)]


class RAWKEYBOARD(ctypes.Structure):
    _fields_ = [("MakeCode", wintypes.USHORT), ("Flags", wintypes.USHORT), ("Reserved", wintypes.USHORT),
                ("VKey", wintypes.USHORT), ("Message", wintypes.UINT), ("ExtraInformation", wintypes.ULONG)]


class _RawData(ctypes.Union):
    _fields_ = [("mouse", RAWMOUSE), ("keyboard", RAWKEYBOARD)]


class RAWINPUT(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("data", _RawData)]


user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                   ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                   wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
user32.CreateWindowExW.restype = wintypes.HWND
user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]
user32.RegisterRawInputDevices.restype = wintypes.BOOL
user32.GetRawInputData.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPVOID,
                                   ctypes.POINTER(wintypes.UINT), wintypes.UINT]
user32.GetRawInputData.restype = wintypes.UINT
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE

CSV_HEADER = ["time", "t_unix", "key", "event"]


class RawInputThread(threading.Thread):
    """在独立线程里创建隐藏窗口、注册 Raw Input 并运行消息循环。"""

    def __init__(self, state: OverlayState, lock: threading.Lock, log: LockedCsvLog) -> None:
        super().__init__(daemon=True)
        self.state, self.lock, self.log = state, lock, log
        self.thread_id = 0
        self.ready = threading.Event()
        self.error = ""
        self.read_errors = 0

    def _on_input(self, lparam) -> None:
        size = wintypes.UINT(0)
        hsize = ctypes.sizeof(RAWINPUTHEADER)
        if user32.GetRawInputData(lparam, RID_INPUT, None, ctypes.byref(size), hsize) != 0 or size.value == 0:
            self.read_errors += 1
            return
        buf = ctypes.create_string_buffer(max(size.value, ctypes.sizeof(RAWINPUT)))
        if user32.GetRawInputData(lparam, RID_INPUT, buf, ctypes.byref(size), hsize) != size.value:
            self.read_errors += 1
            return
        raw = RAWINPUT.from_buffer(buf)
        t = time.time()
        if raw.header.dwType == RIM_TYPEKEYBOARD:
            changes = [c for c in [decode_keyboard(raw.data.keyboard.VKey, raw.data.keyboard.Flags)] if c]
        elif raw.header.dwType == RIM_TYPEMOUSE:
            changes = decode_mouse(raw.data.mouse.usButtonFlags)
        else:
            return
        rows = []
        with self.lock:
            for name, down in changes:
                if self.state.apply(name, down, t):
                    ev = self.state.log[-1][2]
                    rows.append([datetime.datetime.fromtimestamp(t).isoformat(timespec="milliseconds"),
                                 f"{t:.3f}", name, ev])
        for row in rows:
            self.log.write_row(row)  # 记录器关闭后会安全地拒绝写入

    def run(self) -> None:
        self.thread_id = kernel32.GetCurrentThreadId()

        @WNDPROC
        def wndproc(hwnd, msg, wparam, lparam):
            if msg == WM_INPUT:
                self._on_input(lparam)
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc = wndproc  # 保持引用，防止被回收
        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = wndproc
        wc.hInstance = hinst
        wc.lpszClassName = "mcs_input_overlay_raw"
        if not user32.RegisterClassW(ctypes.byref(wc)):
            self.error = f"RegisterClassW 失败：{ctypes.get_last_error()}"
            self.ready.set()
            return
        hwnd = user32.CreateWindowExW(0, wc.lpszClassName, "mcs overlay raw", 0, 0, 0, 0, 0, None, None, hinst, None)
        devices = (RAWINPUTDEVICE * 2)(RAWINPUTDEVICE(0x01, 0x02, RIDEV_INPUTSINK, hwnd),   # 鼠标
                                       RAWINPUTDEVICE(0x01, 0x06, RIDEV_INPUTSINK, hwnd))   # 键盘
        if not hwnd or not user32.RegisterRawInputDevices(devices, 2, ctypes.sizeof(RAWINPUTDEVICE)):
            self.error = f"注册 Raw Input 失败：{ctypes.get_last_error()}"
            self.ready.set()
            return
        self.ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        # 窗口必须由创建它的线程销毁
        user32.DestroyWindow(hwnd)

    def stop(self, timeout_s: float = 2.0) -> bool:
        """通知消息循环退出并等待线程结束，返回线程是否已退出。

        即使返回 False（线程没能及时退出），调用方关闭记录器也是安全的：之后的写入会被拒绝。
        """
        if self.thread_id and self.is_alive():
            if not user32.PostThreadMessageW(self.thread_id, WM_QUIT, 0, 0):
                self.error = f"通知输入线程退出失败：{ctypes.get_last_error()}"
            self.join(timeout_s)
        return not self.is_alive()


def main() -> None:
    p = argparse.ArgumentParser(description="P0-5 输入显示层")
    p.add_argument("--csv", default="input_log.csv", help="按键记录文件")
    a = p.parse_args()

    path = os.path.abspath(a.csv)
    is_new = not os.path.exists(path)
    log = LockedCsvLog(open(path, "a", newline="", encoding="utf-8"), CSV_HEADER if is_new else None)

    state, lock = OverlayState(), threading.Lock()
    raw = RawInputThread(state, lock, log)
    raw.start()

    def shutdown() -> None:
        """统一的退出路径：先停输入线程并等它结束，再关闭记录器（关闭后的写入会被安全拒绝）。"""
        if not raw.stop():
            print("警告：输入线程没有在 2 秒内退出；记录器已关闭，之后的输入不会再写入。", file=sys.stderr)
        log.close()

    if not raw.ready.wait(3):
        shutdown()
        sys.exit("Raw Input 线程启动超时")
    if raw.error:
        shutdown()
        sys.exit(raw.error)

    box, gap = 58, 6
    root = tk.Tk()
    root.title("mcs 输入显示")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    width = len(KEYS) * (box + gap) + gap + 22
    root.geometry(f"{width}x{box + 2 * gap}+12+12")
    canvas = tk.Canvas(root, width=width, height=box + 2 * gap, bg="#111318", highlightthickness=0)
    canvas.pack()
    cells = {}
    for i, k in enumerate(KEYS):
        x = gap + i * (box + gap)
        rect = canvas.create_rectangle(x, gap, x + box, gap + box, fill="#2a2d35", outline="#555")
        text = canvas.create_text(x + box / 2, gap + box / 2 - 6, text=k, fill="#ddd", font=("Microsoft YaHei", 14, "bold"))
        # 累计按下次数：录像里如果某次按键没看到点亮，编号会跳号，可以据此发现漏显示
        count = canvas.create_text(x + box / 2, gap + box - 10, text="0", fill="#999", font=("Consolas", 10))
        cells[k] = (rect, text, count)
    close = canvas.create_text(width - 11, 10, text="×", fill="#aaa", font=("Arial", 12, "bold"))
    warn = canvas.create_text(width - 11, box, text="", fill="#ff5050", font=("Arial", 12, "bold"))

    drag = {"x": 0, "y": 0}

    def on_press(e):
        if canvas.find_withtag("current") == (close,):
            shutdown()
            root.destroy()
            return
        drag["x"], drag["y"] = e.x, e.y

    def on_drag(e):
        root.geometry(f"+{root.winfo_x() + e.x - drag['x']}+{root.winfo_y() + e.y - drag['y']}")

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)

    tick = {"n": 0}

    def refresh():
        now = time.time()
        with lock:
            lit = {k: state.is_lit(k, now) for k in KEYS}
            counts = dict(state.presses)
        log.flush()
        for k, (rect, text, count) in cells.items():
            canvas.itemconfig(rect, fill="#2bd94a" if lit[k] else "#2a2d35")
            canvas.itemconfig(text, fill="#000" if lit[k] else "#ddd")
            canvas.itemconfig(count, text=str(counts[k]), fill="#000" if lit[k] else "#999")
        # 读取失败时右下角显示红色「!」，这次录像要告诉 Claude
        canvas.itemconfig(warn, text="!" if raw.read_errors else "")
        tick["n"] += 1
        if tick["n"] % 50 == 0:
            root.attributes("-topmost", True)  # 游戏切到前台后重新置顶
            root.lift()
        root.after(4, refresh)

    print(f"输入显示层已启动。按键记录：{path}")
    root.protocol("WM_DELETE_WINDOW", lambda: (shutdown(), root.destroy()))
    refresh()
    try:
        root.mainloop()
    finally:
        shutdown()


if __name__ == "__main__":
    main()
