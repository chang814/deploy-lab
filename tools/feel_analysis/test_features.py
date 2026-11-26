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


class SpecTest(unittest.TestCase):
    def info(self, **v):
        video = {"width": 1724, "height": 1080, "r_frame_rate": "60/1", "avg_frame_rate": "60/1",
                 "start_time": "0.000000", "nb_frames": "3649"}
        video.update(v.pop("video", {}))
        audio = v.pop("audio", {"start_time": "0.000000"})
        return {"video": video, "audio": audio}

    def test_calibrated_recording_passes(self):
        self.assertEqual(ft.check_spec(self.info()), [])

    def test_other_resolution_rejected(self):
        self.assertTrue(any("分辨率" in p for p in ft.check_spec(self.info(video={"width": 431, "height": 270}))))

    def test_variable_frame_rate_rejected(self):
        p = ft.check_spec(self.info(video={"avg_frame_rate": "20940000/737311"}))
        self.assertTrue(any("恒定" in x for x in p))

    def test_missing_audio_rejected(self):
        self.assertTrue(any("音轨" in p for p in ft.check_spec(self.info(audio=None))))

    def test_audio_offset_rejected(self):
        self.assertTrue(any("起始时间" in p for p in ft.check_spec(self.info(audio={"start_time": "0.021000"}))))

    def test_missing_start_time_rejected(self):
        # 第 2 轮反例：缺少 start_time 时旧版按 0 处理，等于没检查
        self.assertTrue(any("缺少起始时间" in p for p in ft.check_spec(self.info(video={"start_time": "N/A"}))))
        self.assertTrue(any("缺少起始时间" in p for p in ft.check_spec(self.info(audio={}))))


class FrameTimesTest(unittest.TestCase):
    def test_uniform_timeline_passes(self):
        self.assertEqual(ft.check_timeline([i / 60 for i in range(600)], 60.0), [])

    def test_dropped_frame_rejected(self):
        times = [i / 60 for i in range(600) if i != 300]
        self.assertTrue(any("帧间隔" in p for p in ft.check_timeline(times, 60.0)))

    def test_duplicated_frame_rejected(self):
        times = [i / 60 for i in range(600)]
        times.insert(300, times[300])
        self.assertTrue(ft.check_timeline(times, 60.0))

    def test_late_first_frame_rejected(self):
        self.assertTrue(any("第一帧" in p for p in ft.check_timeline([0.1 + i / 60 for i in range(60)], 60.0)))

    def test_codex_r3_nan_rejected(self):
        times = [i / 60 for i in range(600)]
        times[200] = float("nan")
        self.assertTrue(ft.check_timeline(times, 60.0))
        self.assertTrue(ft.check_timeline([float("nan")] + times[1:], 60.0))
        self.assertTrue(ft.check_timeline(times, float("nan")))

    def test_empty_rejected(self):
        self.assertTrue(ft.check_timeline([], 60.0))


if __name__ == "__main__":
    unittest.main()
