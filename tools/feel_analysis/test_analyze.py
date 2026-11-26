"""analyze.py 的测试（合成帧序列，不需要录像）。

运行：python -I -B -m unittest discover -s tools/feel_analysis -p "test_*.py"
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as an  # noqa: E402

KEYS = ["1", "2", "3", "Q", "F", "wheel", "L", "R"]


AV_LAG = 5  # 合成数据里枪声比火光晚的帧数（与实测一致）


def make(n: int, presses: dict[str, list[tuple[int, int]]], hot_base: int = 40,
         flashes: list[tuple[int, int]] = (), hot_flash: int = 400, sound: bool = True,
         extra_audio: list[tuple[int, int]] = ()) -> list[an.Frame]:
    """presses：键 → [(亮起帧, 熄灭帧)]；flashes：[(开始帧, 结束帧)] 期间 hot 为 hot_flash，
    sound 为真时每段火光开始后 AV_LAG 帧起有枪声；extra_audio：[(开始帧, 结束帧)] 额外的枪声。"""
    frames = []
    shots = [(a + AV_LAG, b + AV_LAG) for a, b in flashes] if sound else []
    shots += list(extra_audio)
    for i in range(n):
        lit = {k: any(a <= i < b for a, b in presses.get(k, [])) for k in KEYS}
        hot = hot_flash if any(a <= i < b for a, b in flashes) else hot_base
        audio = 9000.0 if any(a <= i < b for a, b in shots) else 100.0
        frames.append(an.Frame(i / 60, lit, hot, audio))
    return frames


class OnsetAndTrackerTest(unittest.TestCase):
    def test_onset_ignores_already_lit_first_frame(self):
        fr = make(20, {"1": [(0, 5), (10, 12)]})
        self.assertEqual(an.onsets(fr, "1"), [10])

    def test_tracker_select_keys(self):
        self.assertEqual(an.track_weapons([(1, "3"), (2, "1")]), [(None, "knife"), ("knife", "ak")])

    def test_tracker_q_swaps(self):
        st = an.track_weapons([(1, "1"), (2, "2"), (3, "Q"), (4, "Q")])
        self.assertEqual(st[2], ("glock", "ak"))
        self.assertEqual(st[3], ("ak", "glock"))

    def test_tracker_q_without_previous_is_unknown(self):
        self.assertEqual(an.track_weapons([(1, "1"), (2, "Q")])[1], ("ak", None))

    def test_tracker_same_key_does_not_change_previous(self):
        st = an.track_weapons([(1, "2"), (2, "1"), (3, "1"), (4, "Q")])
        self.assertEqual(st[3], ("ak", "glock"))

    def test_tracker_wheel_is_unknown(self):
        self.assertEqual(an.track_weapons([(1, "1"), (2, "wheel")])[1], ("ak", None))


class KeyLogTest(unittest.TestCase):
    def rows(self, seq):
        return [{"t_unix": str(1000 + i), "key": k, "event": "wheel" if k == "滚轮" else "down"} for i, k in enumerate(seq)]

    def test_state_from_log(self):
        self.assertEqual(an.state_from_key_log(self.rows(["2", "1"]), 2000), ("ak", "glock"))

    def test_state_ignores_events_after_start(self):
        self.assertEqual(an.state_from_key_log(self.rows(["2", "1", "3"]), 1001.5), ("ak", "glock"))

    def test_state_ignores_up_events_and_other_keys(self):
        rows = self.rows(["2", "1"]) + [{"t_unix": "1003", "key": "1", "event": "up"},
                                        {"t_unix": "1004", "key": "F", "event": "down"}]
        self.assertEqual(an.state_from_key_log(rows, 2000), ("ak", "glock"))

    def test_wheel_makes_state_unknown(self):
        self.assertEqual(an.state_from_key_log(self.rows(["1", "滚轮"]), 2000), (None, "ak"))


class FlashTest(unittest.TestCase):
    def test_detects_jump(self):
        fr = make(100, {}, flashes=[(60, 70)])
        self.assertEqual(an.find_flash(fr, 10, 100), 60)

    def test_ignores_small_rise(self):
        fr = make(100, {}, flashes=[(60, 70)], hot_flash=70)
        self.assertIsNone(an.find_flash(fr, 10, 100))

    def test_raised_baseline_still_detected(self):
        # 枪举起来之后区域整体变亮（基线 139），火光 375 仍应检出（A2 实测值）
        fr = make(100, {}, hot_base=139, flashes=[(60, 70)], hot_flash=375)
        self.assertEqual(an.find_flash(fr, 10, 100), 60)

    def test_flash_must_be_before_end(self):
        fr = make(100, {}, flashes=[(80, 90)])
        self.assertIsNone(an.find_flash(fr, 10, 70))

    def test_bright_highlight_without_gunshot_is_not_a_shot(self):
        # B 实测：拔 Glock 时手套高光让 hot 跳升，但没有枪声，不能算开枪
        fr = make(200, {}, flashes=[(60, 70)], sound=False)
        self.assertIsNone(an.find_flash(fr, 10, 200))

    def test_gunshot_without_visual_jump_returns_none(self):
        fr = make(200, {}, extra_audio=[(100, 110)])
        self.assertIsNone(an.find_flash(fr, 10, 200))

    def test_highlight_then_real_shot_picks_the_real_one(self):
        # 先有一次无声的高光（误报候选），之后才是真正的开枪
        fr = make(300, {}, flashes=[(60, 70), (200, 210)])
        fr2 = [an.Frame(x.t, x.lit, x.hot, 100.0 if i < 150 else x.audio) for i, x in enumerate(fr)]
        self.assertEqual(an.find_flash(fr2, 10, 300), 200)

    def test_flash_found_within_window_before_gunshot(self):
        fr = make(200, {}, flashes=[(100, 110)])
        self.assertEqual(an.audio_shot(fr, 10, 200), 100 + AV_LAG)
        self.assertEqual(an.find_flash(fr, 10, 200), 100)


class AnalyzeTest(unittest.TestCase):
    def cycle(self, **kw):
        presses = {"3": [(10, 16)], "1": [(100, 106)], "L": [(150, 320)]}
        presses.update(kw.pop("presses", {}))
        fr = make(400, presses, flashes=kw.pop("flashes", [(300, 340)]))
        return an.analyze(fr, 60.0, "A", 0.1)

    def test_valid_cycle_duration(self):
        cs = self.cycle()
        self.assertEqual(len(cs), 1)
        self.assertTrue(cs[0].valid, cs[0].reason)
        self.assertAlmostEqual(cs[0].duration_s, 200 / 60 * 0.1)

    def test_left_held_before_trigger_is_invalid(self):
        cs = self.cycle(presses={"L": [(90, 320)]})
        self.assertFalse(cs[0].valid)
        self.assertIn("左键已经按着", cs[0].reason)

    def test_left_pressed_late_is_invalid(self):
        cs = self.cycle(presses={"L": [(295, 320)]})
        self.assertFalse(cs[0].valid)
        self.assertIn("按晚", cs[0].reason)

    def test_no_left_before_flash_is_invalid(self):
        cs = self.cycle(presses={"L": [(330, 360)]})
        self.assertFalse(cs[0].valid)

    def test_wrong_direction_is_invalid(self):
        cs = self.cycle(presses={"3": [], "2": [(10, 16)]})
        self.assertFalse(cs[0].valid)
        self.assertIn("方向", cs[0].reason)

    def test_unknown_start_weapon_is_invalid(self):
        cs = self.cycle(presses={"3": []})
        self.assertFalse(cs[0].valid)

    def test_no_flash_is_invalid(self):
        cs = self.cycle(flashes=[])
        self.assertFalse(cs[0].valid)
        self.assertIn("没有枪声", cs[0].reason)

    def test_initial_state_from_outside_video(self):
        # E2 实测：录像开始前已经按过「2 再 1」，录像里第一下就是 Q
        presses = {"Q": [(100, 106)], "L": [(150, 320)]}
        fr = make(400, presses, flashes=[(300, 340)])
        cs = an.analyze(fr, 60.0, "E2", 0.1, initial=("ak", "glock"))
        self.assertTrue(cs[0].valid, cs[0].reason)
        cs2 = an.analyze(fr, 60.0, "E2", 0.1)
        self.assertFalse(cs2[0].valid)

    def test_summary(self):
        a = an.Cycle("A", 0, valid=True, duration_s=1.0)
        b = an.Cycle("A", 0, valid=True, duration_s=1.02)
        c = an.Cycle("A", 0, valid=True, duration_s=1.01)
        d = an.Cycle("A", 0, valid=False)
        s = an.summarize([a, b, c, d])
        self.assertEqual(s["samples"], 3)
        self.assertAlmostEqual(s["median_s"], 1.01)
        self.assertAlmostEqual(s["max_dev_s"], 0.01)


if __name__ == "__main__":
    unittest.main()
