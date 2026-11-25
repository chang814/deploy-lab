"""rawinput_counter 的分轮逻辑测试（合成数据包，不需要真实鼠标）。

运行：python -I -m unittest discover -s spikes/raw-input/tools -p "test_*.py"
"""

import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rawinput_counter as rc  # noqa: E402


def packet(dx: int = 0, dy: int = 0, buttons: int = 0, absolute: bool = False) -> rc.RAWINPUT_MOUSE:
    p = rc.RAWINPUT_MOUSE()
    p.header.dwType = rc.RIM_TYPEMOUSE
    p.mouse.usFlags = rc.MOUSE_MOVE_ABSOLUTE if absolute else 0
    p.mouse.usButtonFlags = buttons
    p.mouse.lLastX = dx
    p.mouse.lLastY = dy
    return p


MID = rc.RI_MOUSE_MIDDLE_BUTTON_DOWN
RIGHT = rc.RI_MOUSE_RIGHT_BUTTON_DOWN


class CounterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "runs.csv")
        self.c = rc.Counter(self.path)

    def tearDown(self) -> None:
        self.dir.cleanup()

    def rows(self) -> list[dict]:
        with open(self.path, encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_layout_matches_windows_x64(self) -> None:
        import ctypes
        self.assertEqual(ctypes.sizeof(rc.RAWINPUTHEADER), 24)
        self.assertEqual(ctypes.sizeof(rc.RAWMOUSE), 24)
        self.assertEqual(rc.RAWMOUSE.lLastX.offset, 12)
        self.assertEqual(rc.RAWMOUSE.lLastY.offset, 16)

    def test_normal_round(self) -> None:
        self.c.on_mouse(packet(buttons=MID))
        self.c.on_mouse(packet(dx=10, dy=-3))
        self.c.on_mouse(packet(dx=5))
        self.c.on_mouse(packet(buttons=RIGHT))
        r = self.rows()[0]
        self.assertEqual((r["round"], r["valid"], r["raw_x"], r["raw_y"], r["events"]), ("1", "1", "15", "-3", "2"))

    def test_motion_before_first_round_is_discarded(self) -> None:
        self.c.on_mouse(packet(dx=100))
        self.c.on_mouse(packet(buttons=MID))
        self.c.on_mouse(packet(buttons=RIGHT))
        self.assertEqual(self.rows()[0]["raw_x"], "0")

    def test_middle_with_motion_flags_boundary(self) -> None:
        self.c.on_mouse(packet(dx=5, buttons=MID))
        self.c.on_mouse(packet(buttons=RIGHT))
        r = self.rows()[0]
        self.assertEqual((r["valid"], r["boundary_motion"]), ("0", "1"))

    def test_right_with_motion_flags_boundary(self) -> None:
        self.c.on_mouse(packet(buttons=MID))
        self.c.on_mouse(packet(dx=5, buttons=RIGHT))
        r = self.rows()[0]
        self.assertEqual((r["valid"], r["boundary_motion"], r["raw_x"]), ("0", "1", "5"))

    def test_absolute_and_read_errors_invalidate(self) -> None:
        self.c.on_mouse(packet(buttons=MID))
        self.c.on_mouse(packet(dx=500, absolute=True))
        self.c.on_read_error()
        self.c.on_mouse(packet(buttons=RIGHT))
        r = self.rows()[0]
        self.assertEqual((r["valid"], r["absolute_events"], r["read_errors"], r["raw_x"]), ("0", "1", "1", "0"))

    def test_new_round_clears_flags(self) -> None:
        self.c.on_mouse(packet(dx=5, buttons=MID))
        self.c.on_mouse(packet(buttons=MID))
        self.c.on_mouse(packet(dx=1))
        self.c.on_mouse(packet(buttons=RIGHT))
        r = self.rows()[0]
        self.assertEqual((r["round"], r["valid"], r["raw_x"]), ("2", "1", "1"))

    def test_repeated_right_click_logs_same_round_twice(self) -> None:
        self.c.on_mouse(packet(buttons=MID))
        self.c.on_mouse(packet(dx=3))
        self.c.on_mouse(packet(buttons=RIGHT))
        self.c.on_mouse(packet(buttons=RIGHT))
        rows = self.rows()
        self.assertEqual([r["round"] for r in rows], ["1", "1"])


if __name__ == "__main__":
    unittest.main()
