"""输入显示层的测试。纯逻辑部分与平台无关；结构体布局只在 Windows 上检查。

运行：python -I -m unittest discover -s tools/input_overlay -p "test_*.py"
"""

import ctypes
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import overlay_state as s  # noqa: E402


class DecodeTest(unittest.TestCase):
    def test_keyboard_down_up(self):
        self.assertEqual(s.decode_keyboard(0x31, 0), ("1", True))
        self.assertEqual(s.decode_keyboard(0x31, s.RI_KEY_BREAK), ("1", False))
        self.assertEqual(s.decode_keyboard(0x46, 0), ("F", True))

    def test_irrelevant_key_ignored(self):
        self.assertIsNone(s.decode_keyboard(0x41, 0))  # A

    def test_mouse_buttons_and_wheel(self):
        self.assertEqual(s.decode_mouse(s.RI_MOUSE_LEFT_BUTTON_DOWN), [("左键", True)])
        self.assertEqual(s.decode_mouse(s.RI_MOUSE_RIGHT_BUTTON_UP), [("右键", False)])
        self.assertEqual(s.decode_mouse(s.RI_MOUSE_WHEEL), [("滚轮", True)])
        self.assertEqual(s.decode_mouse(0), [])

    def test_mouse_multiple_flags_in_one_packet(self):
        got = s.decode_mouse(s.RI_MOUSE_LEFT_BUTTON_UP | s.RI_MOUSE_RIGHT_BUTTON_DOWN)
        self.assertEqual(got, [("左键", False), ("右键", True)])


class StateTest(unittest.TestCase):
    def test_press_release_lights_and_logs(self):
        st = s.OverlayState()
        self.assertTrue(st.apply("Q", True, 1.0))
        self.assertTrue(st.is_lit("Q", 1.0))
        self.assertTrue(st.apply("Q", False, 1.2))
        self.assertFalse(st.is_lit("Q", 1.2))
        self.assertEqual(st.log, [(1.0, "Q", "down"), (1.2, "Q", "up")])

    def test_keyboard_autorepeat_not_logged(self):
        st = s.OverlayState()
        st.apply("1", True, 1.0)
        self.assertFalse(st.apply("1", True, 1.03))
        self.assertEqual(len(st.log), 1)

    def test_wheel_flashes_for_a_while(self):
        st = s.OverlayState()
        st.apply("滚轮", True, 5.0)
        self.assertTrue(st.is_lit("滚轮", 5.0 + s.WHEEL_FLASH_S / 2))
        self.assertFalse(st.is_lit("滚轮", 5.0 + s.WHEEL_FLASH_S + 0.001))
        # 滚轮流光至少覆盖 60 fps 录像的 5 帧
        self.assertGreaterEqual(s.WHEEL_FLASH_S, 5 / 60)

    def test_short_tap_stays_lit_for_min_time(self):
        # Codex 反例：1.001 s 按下、1.003 s 松开，1.004 s 刷新时也必须是亮的
        st = s.OverlayState()
        st.apply("Q", True, 1.001)
        st.apply("Q", False, 1.003)
        self.assertTrue(st.is_lit("Q", 1.004))
        self.assertTrue(st.is_lit("Q", 1.001 + s.MIN_LIT_S - 0.001))
        self.assertFalse(st.is_lit("Q", 1.001 + s.MIN_LIT_S + 0.001))
        self.assertGreaterEqual(s.MIN_LIT_S, 5 / 60)

    def test_press_counter_counts_downs_only(self):
        st = s.OverlayState()
        for t in (1.0, 2.0, 3.0):
            st.apply("1", True, t)
            st.apply("1", False, t + 0.05)
        st.apply("1", True, 4.0)
        st.apply("1", True, 4.03)  # 自动重复不计
        st.apply("滚轮", True, 5.0)
        self.assertEqual(st.presses["1"], 4)
        self.assertEqual(st.presses["滚轮"], 1)

    def test_all_keys_have_cells(self):
        self.assertEqual(set(s.VKEY_NAMES.values()) | {"滚轮", "左键", "右键"}, set(s.KEYS))


@unittest.skipUnless(sys.platform == "win32", "Windows 专用")
class LayoutTest(unittest.TestCase):
    def test_struct_layout_x64(self):
        import input_overlay as io
        self.assertEqual(ctypes.sizeof(io.RAWINPUTHEADER), 24)
        self.assertEqual(ctypes.sizeof(io.RAWMOUSE), 24)
        self.assertEqual(ctypes.sizeof(io.RAWKEYBOARD), 16)
        self.assertEqual(io.RAWKEYBOARD.VKey.offset, 6)
        self.assertEqual(io.RAWINPUT.data.offset, 24)


if __name__ == "__main__":
    unittest.main()
