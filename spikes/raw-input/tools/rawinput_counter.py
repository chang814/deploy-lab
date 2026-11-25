"""Windows Raw Input 鼠标计数器：P0-4 的独立基准。

直接向 Windows 注册 Raw Input（RIDEV_INPUTSINK，后台也能收到），累计鼠标的原始计数，
不经过系统指针速度与「提高指针精确度」。与 Godot spike 同时运行，用同一次鼠标点击划分「轮」：

    鼠标中键按下 = 开始新一轮（清零）
    鼠标右键按下 = 结束本轮，写一行 CSV

只读取鼠标输入，不读取、不注入任何其他进程。只依赖 Python 标准库。

用法：
    python -I rawinput_counter.py [--csv 路径] [--duration 秒]
"""

import argparse
import csv
import ctypes
import datetime
import os
import sys
import time
from ctypes import wintypes

if sys.platform != "win32":
    sys.exit("只支持 Windows")

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

WM_INPUT = 0x00FF
WM_TIMER = 0x0113
RID_INPUT = 0x10000003
RIM_TYPEMOUSE = 0
RIDEV_INPUTSINK = 0x00000100
MOUSE_MOVE_ABSOLUTE = 0x0001
RI_MOUSE_RIGHT_BUTTON_DOWN = 0x0004
RI_MOUSE_MIDDLE_BUTTON_DOWN = 0x0010
HID_USAGE_PAGE_GENERIC = 0x01
HID_USAGE_GENERIC_MOUSE = 0x02

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class RAWINPUTDEVICE(ctypes.Structure):
    _fields_ = [
        ("usUsagePage", wintypes.USHORT),
        ("usUsage", wintypes.USHORT),
        ("dwFlags", wintypes.DWORD),
        ("hwndTarget", wintypes.HWND),
    ]


class RAWINPUTHEADER(ctypes.Structure):
    _fields_ = [
        ("dwType", wintypes.DWORD),
        ("dwSize", wintypes.DWORD),
        ("hDevice", wintypes.HANDLE),
        ("wParam", wintypes.WPARAM),
    ]


class _ButtonsStruct(ctypes.Structure):
    _fields_ = [("usButtonFlags", wintypes.USHORT), ("usButtonData", wintypes.USHORT)]


class _ButtonsUnion(ctypes.Union):
    _anonymous_ = ("s",)
    _fields_ = [("ulButtons", wintypes.ULONG), ("s", _ButtonsStruct)]


class RAWMOUSE(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("usFlags", wintypes.USHORT),
        ("u", _ButtonsUnion),
        ("ulRawButtons", wintypes.ULONG),
        ("lLastX", wintypes.LONG),
        ("lLastY", wintypes.LONG),
        ("ulExtraInformation", wintypes.ULONG),
    ]


class RAWINPUT_MOUSE(ctypes.Structure):
    _fields_ = [("header", RAWINPUTHEADER), ("mouse", RAWMOUSE)]


user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
user32.DefWindowProcW.restype = LRESULT
user32.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
user32.RegisterClassW.restype = wintypes.ATOM
user32.CreateWindowExW.argtypes = [
    wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
    wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
]
user32.CreateWindowExW.restype = wintypes.HWND
user32.RegisterRawInputDevices.argtypes = [ctypes.POINTER(RAWINPUTDEVICE), wintypes.UINT, wintypes.UINT]
user32.RegisterRawInputDevices.restype = wintypes.BOOL
user32.GetRawInputData.argtypes = [
    wintypes.HANDLE, wintypes.UINT, wintypes.LPVOID, ctypes.POINTER(wintypes.UINT), wintypes.UINT,
]
user32.GetRawInputData.restype = wintypes.UINT
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
user32.GetMessageW.restype = wintypes.BOOL
user32.SetTimer.argtypes = [wintypes.HWND, ctypes.c_size_t, wintypes.UINT, wintypes.LPVOID]
user32.SetTimer.restype = ctypes.c_size_t
kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
kernel32.GetModuleHandleW.restype = wintypes.HMODULE


class Counter:
    def __init__(self, csv_path: str) -> None:
        self.csv_path = csv_path
        self.round_index = 0
        self.devices: set[int] = set()
        self._reset()

    def _reset(self) -> None:
        self.x = 0
        self.y = 0
        self.events = 0
        self.absolute_events = 0

    def on_mouse(self, raw: RAWINPUT_MOUSE) -> None:
        m = raw.mouse
        self.devices.add(int(raw.header.hDevice or 0))
        if m.usFlags & MOUSE_MOVE_ABSOLUTE:
            self.absolute_events += 1
        elif m.lLastX or m.lLastY:
            self.x += m.lLastX
            self.y += m.lLastY
            self.events += 1
        if m.usButtonFlags & RI_MOUSE_MIDDLE_BUTTON_DOWN:
            self.round_index += 1
            self._reset()
            print(f"\n—— 第 {self.round_index} 轮开始 ——")
        if m.usButtonFlags & RI_MOUSE_RIGHT_BUTTON_DOWN:
            self.log()

    def log(self) -> None:
        is_new = not os.path.exists(self.csv_path)
        with open(self.csv_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if is_new:
                w.writerow(["time", "round", "raw_x", "raw_y", "events", "absolute_events", "devices"])
            w.writerow([
                datetime.datetime.now().isoformat(timespec="seconds"),
                self.round_index, self.x, self.y, self.events, self.absolute_events, len(self.devices),
            ])
        print(f"\n已记录第 {self.round_index} 轮：X={self.x} Y={self.y} 事件={self.events}")

    def status(self) -> str:
        warn = f"  ⚠ 绝对坐标事件 {self.absolute_events}（数据不可用）" if self.absolute_events else ""
        return (f"\r第 {self.round_index} 轮  X={self.x:>8}  Y={self.y:>8}  "
                f"事件={self.events:>6}  设备数={len(self.devices)}{warn}    ")


def main() -> None:
    parser = argparse.ArgumentParser(description="Windows Raw Input 鼠标计数器（P0-4 基准）")
    parser.add_argument("--csv", default="rawinput_runs.csv", help="记录文件路径")
    parser.add_argument("--duration", type=float, default=0.0, help="运行秒数，0 表示一直运行（Ctrl+C 退出）")
    args = parser.parse_args()

    counter = Counter(os.path.abspath(args.csv))
    started = time.monotonic()

    @WNDPROC
    def wndproc(hwnd, msg, wparam, lparam):
        if msg == WM_INPUT:
            size = wintypes.UINT(0)
            header_size = ctypes.sizeof(RAWINPUTHEADER)
            user32.GetRawInputData(lparam, RID_INPUT, None, ctypes.byref(size), header_size)
            buf = ctypes.create_string_buffer(max(size.value, ctypes.sizeof(RAWINPUT_MOUSE)))
            got = user32.GetRawInputData(lparam, RID_INPUT, buf, ctypes.byref(size), header_size)
            if got != 0xFFFFFFFF:
                raw = RAWINPUT_MOUSE.from_buffer(buf)
                if raw.header.dwType == RIM_TYPEMOUSE:
                    counter.on_mouse(raw)
        elif msg == WM_TIMER:
            sys.stdout.write(counter.status())
            sys.stdout.flush()
            if args.duration and time.monotonic() - started >= args.duration:
                user32.PostQuitMessage(0)
        return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

    hinst = kernel32.GetModuleHandleW(None)
    wc = WNDCLASSW()
    wc.lpfnWndProc = wndproc
    wc.hInstance = hinst
    wc.lpszClassName = "mcs_rawinput_counter"
    if not user32.RegisterClassW(ctypes.byref(wc)):
        sys.exit(f"RegisterClassW 失败：{ctypes.get_last_error()}")
    # 不显示的普通窗口（INPUTSINK 需要一个目标窗口）
    hwnd = user32.CreateWindowExW(0, wc.lpszClassName, "mcs raw input", 0, 0, 0, 0, 0, None, None, hinst, None)
    if not hwnd:
        sys.exit(f"CreateWindowExW 失败：{ctypes.get_last_error()}")

    rid = RAWINPUTDEVICE(HID_USAGE_PAGE_GENERIC, HID_USAGE_GENERIC_MOUSE, RIDEV_INPUTSINK, hwnd)
    if not user32.RegisterRawInputDevices(ctypes.byref(rid), 1, ctypes.sizeof(RAWINPUTDEVICE)):
        sys.exit(f"RegisterRawInputDevices 失败：{ctypes.get_last_error()}")
    user32.SetTimer(hwnd, 1, 200, None)

    print("Raw Input 计数器已启动。鼠标中键 = 新一轮，右键 = 记录。Ctrl+C 退出。")
    print(f"记录文件：{counter.csv_path}")
    msg = wintypes.MSG()
    try:
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
    except KeyboardInterrupt:
        pass
    print("\n已退出。")


if __name__ == "__main__":
    main()
