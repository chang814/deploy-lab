"""输入显示层的纯逻辑（与平台无关，可单元测试）。

把 Raw Input 的原始字段解码成「哪个键按下/松开」，并维护每个键当前是否点亮。
"""

from dataclasses import dataclass, field

# 显示顺序与标签
KEYS: list[str] = ["1", "2", "3", "Q", "F", "滚轮", "左键", "右键"]

# 键盘虚拟键码 → 名称（只关心测量用到的键）
VKEY_NAMES: dict[int, str] = {0x31: "1", 0x32: "2", 0x33: "3", 0x51: "Q", 0x46: "F"}

RI_KEY_BREAK = 0x01  # RAWKEYBOARD.Flags：键松开

RI_MOUSE_LEFT_BUTTON_DOWN = 0x0001
RI_MOUSE_LEFT_BUTTON_UP = 0x0002
RI_MOUSE_RIGHT_BUTTON_DOWN = 0x0004
RI_MOUSE_RIGHT_BUTTON_UP = 0x0008
RI_MOUSE_WHEEL = 0x0400

WHEEL_FLASH_S = 0.10  # 滚轮没有「松开」，点亮这么久，保证 60 fps 录像里至少有几帧能看到


def decode_keyboard(vkey: int, flags: int) -> tuple[str, bool] | None:
    """返回 (键名, 是否按下)；不关心的键返回 None。"""
    name = VKEY_NAMES.get(vkey)
    if name is None:
        return None
    return name, not (flags & RI_KEY_BREAK)


def decode_mouse(button_flags: int) -> list[tuple[str, bool]]:
    """返回这个数据包里的按键变化列表；滚轮记为 ("滚轮", True)。"""
    out: list[tuple[str, bool]] = []
    if button_flags & RI_MOUSE_LEFT_BUTTON_DOWN:
        out.append(("左键", True))
    if button_flags & RI_MOUSE_LEFT_BUTTON_UP:
        out.append(("左键", False))
    if button_flags & RI_MOUSE_RIGHT_BUTTON_DOWN:
        out.append(("右键", True))
    if button_flags & RI_MOUSE_RIGHT_BUTTON_UP:
        out.append(("右键", False))
    if button_flags & RI_MOUSE_WHEEL:
        out.append(("滚轮", True))
    return out


@dataclass
class OverlayState:
    pressed: dict[str, bool] = field(default_factory=lambda: {k: False for k in KEYS})
    wheel_until: float = 0.0
    log: list[tuple[float, str, str]] = field(default_factory=list)  # (时间戳, 键名, "down"/"up"/"wheel")

    def apply(self, name: str, down: bool, t: float) -> bool:
        """应用一次按键变化，返回是否需要记录（按住时的自动重复不记录）。"""
        if name == "滚轮":
            self.wheel_until = t + WHEEL_FLASH_S
            self.log.append((t, name, "wheel"))
            return True
        if self.pressed.get(name) == down:
            return False  # 键盘按住不放时 Windows 会重复发送按下，只记第一次
        self.pressed[name] = down
        self.log.append((t, name, "down" if down else "up"))
        return True

    def is_lit(self, name: str, now: float) -> bool:
        if name == "滚轮":
            return now < self.wheel_until
        return self.pressed.get(name, False)
