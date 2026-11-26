"""features.py 中颜色判据的测试（合成像素，不需要录像）。颜色值取自实测录像中的典型像素。"""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import features as ft  # noqa: E402


def patch(rgb: tuple[int, int, int], n: int = 10) -> np.ndarray:
    return np.full((n, n, 3), rgb, dtype=np.uint8)


class SaturatedOrangeTest(unittest.TestCase):
    def test_muzzle_flash_orange_counts(self):
        self.assertEqual(ft.saturated_orange(patch((255, 160, 60))), 100)
        self.assertEqual(ft.saturated_orange(patch((250, 200, 80))), 100)

    def test_dust2_sand_does_not_count(self):
        self.assertEqual(ft.saturated_orange(patch((215, 165, 110))), 0)

    def test_glove_and_slide_highlights_do_not_count(self):
        # 拔 Glock 时的近白高光：很亮但不饱和
        self.assertEqual(ft.saturated_orange(patch((250, 235, 210))), 0)

    def test_pure_red_does_not_count(self):
        self.assertEqual(ft.saturated_orange(patch((255, 30, 20))), 0)

    def test_mixed_frame(self):
        fr = patch((215, 165, 110), 20)
        fr[5:9, 5:10] = (255, 160, 60)
        self.assertEqual(ft.saturated_orange(fr), 20)


if __name__ == "__main__":
    unittest.main()
