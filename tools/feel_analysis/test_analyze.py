"""analyze.py 的测试（合成帧序列，不需要录像）。

运行：python -I -B -m unittest discover -s tools/feel_analysis -p "test_*.py"
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as an  # noqa: E402

KEYS = ["1", "2", "3", "Q", "F", "wheel", "L", "R"]
AV_LAG = 4  # 合成数据里枪声比火光晚的帧数（实测 3–5）


def make(n: int, presses: dict[str, list[tuple[int, int]]], flashes: list[tuple[int, int]] = (),
         flash_value: int = 1800, sound: bool = True, extra_audio: list[tuple[int, int]] = ()) -> list[an.Frame]:
    """presses：键 → [(亮起帧, 熄灭帧)]；flashes：[(开始帧, 结束帧)] 期间火光指标为 flash_value，
    sound 为真时每段火光开始后 AV_LAG 帧起有枪声；extra_audio：额外的枪声区间。"""
    shots = [(a + AV_LAG, b + AV_LAG) for a, b in flashes] if sound else []
    shots += list(extra_audio)
    frames = []
    for i in range(n):
        lit = {k: any(a <= i < b for a, b in presses.get(k, [])) for k in KEYS}
        flash = flash_value if any(a <= i < b for a, b in flashes) else 0
        audio = 9000.0 if any(a <= i < b for a, b in shots) else 100.0
        frames.append(an.Frame(i / 60, lit, flash, audio))
    return frames


class TrackerTest(unittest.TestCase):
    def test_onset_ignores_already_lit_first_frame(self):
        fr = make(20, {"1": [(0, 5), (10, 12)]})
        self.assertEqual(an.onsets(fr, "1"), [10])

    def test_select_keys(self):
        self.assertEqual(an.track_weapons([(1, "3"), (2, "1")]), [(None, "knife"), ("knife", "ak")])

    def test_q_swaps(self):
        st = an.track_weapons([(1, "1"), (2, "2"), (3, "Q"), (4, "Q")])
        self.assertEqual(st[2], ("glock", "ak"))
        self.assertEqual(st[3], ("ak", "glock"))

    def test_q_without_previous_is_unknown(self):
        self.assertEqual(an.track_weapons([(1, "1"), (2, "Q")])[1], ("ak", None))

    def test_same_key_twice_keeps_previous(self):
        st = an.track_weapons([(1, "2"), (2, "1"), (3, "1"), (4, "Q")])
        self.assertEqual(st[3], ("ak", "glock"))

    def test_wheel_is_unknown(self):
        self.assertEqual(an.track_weapons([(1, "1"), (2, "wheel")])[1], ("ak", None))

    def test_initial_state(self):
        self.assertEqual(an.track_weapons([(1, "Q")], ("ak", "glock"))[0], ("ak", "glock"))


class InitialArgTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(an.parse_initial("knife,ak"), ("knife", "ak"))
        self.assertEqual(an.parse_initial("ak,-"), ("ak", None))

    def test_rejects_bad_input(self):
        for bad in ("ak", "ak,glock,knife", "m4,ak"):
            with self.assertRaises(ValueError):
                an.parse_initial(bad)


class FlashTest(unittest.TestCase):
    def test_detects_first_flash_frame(self):
        fr = make(200, {}, flashes=[(100, 110)])
        self.assertEqual(an.find_flash(fr, 10, 200), 100)

    def test_small_glock_flash_detected(self):
        fr = make(200, {}, flashes=[(100, 110)], flash_value=600)
        self.assertEqual(an.find_flash(fr, 10, 200), 100)

    def test_flash_without_gunshot_is_not_a_shot(self):
        fr = make(200, {}, flashes=[(100, 110)], sound=False)
        self.assertIsNone(an.find_flash(fr, 10, 200))

    def test_gunshot_without_flash_returns_none(self):
        fr = make(200, {}, extra_audio=[(100, 110)])
        self.assertIsNone(an.find_flash(fr, 10, 200))
        self.assertTrue(an.has_gunshot(fr, 10, 200))

    def test_silent_bright_frames_then_real_shot(self):
        # 先有一段无声的橙色（例如别的特效），之后才是真正的开枪
        fr = make(300, {}, flashes=[(60, 70), (200, 210)])
        fr = [an.Frame(x.t, x.lit, x.flash, 100.0 if i < 150 else x.audio) for i, x in enumerate(fr)]
        self.assertEqual(an.find_flash(fr, 10, 300), 200)

    def test_gunshot_too_late_does_not_confirm(self):
        fr = make(300, {}, flashes=[(100, 105)], sound=False, extra_audio=[(100 + an.AV_WINDOW_FRAMES + 5, 140)])
        self.assertIsNone(an.find_flash(fr, 10, 300))

    def test_flash_must_be_before_end(self):
        fr = make(200, {}, flashes=[(150, 160)])
        self.assertIsNone(an.find_flash(fr, 10, 120))

    def test_below_threshold_ignored(self):
        fr = make(200, {}, flashes=[(100, 110)], flash_value=an.FLASH_MIN - 1)
        self.assertIsNone(an.find_flash(fr, 10, 200))


class AnalyzeTest(unittest.TestCase):
    def cycle(self, item="A", initial=(None, None), **kw):
        presses = {"3": [(10, 16)], "1": [(100, 106)], "L": [(150, 320)]}
        presses.update(kw.pop("presses", {}))
        fr = make(400, presses, flashes=kw.pop("flashes", [(300, 340)]), **kw)
        return an.analyze(fr, 60.0, item, 0.1, initial)

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

    def test_unknown_start_is_invalid_unless_declared(self):
        cs = self.cycle(presses={"3": []})
        self.assertFalse(cs[0].valid)
        cs2 = self.cycle(presses={"3": []}, initial=("knife", "ak"))
        self.assertTrue(cs2[0].valid, cs2[0].reason)

    def test_no_shot_is_invalid(self):
        cs = self.cycle(flashes=[])
        self.assertFalse(cs[0].valid)
        self.assertIn("没有开枪", cs[0].reason)

    def test_gunshot_but_no_flash_reason(self):
        cs = self.cycle(flashes=[], extra_audio=[(300, 310)])
        self.assertFalse(cs[0].valid)
        self.assertIn("没有找到对应的火光", cs[0].reason)

    def test_e2_with_declared_initial_state(self):
        presses = {"Q": [(100, 106)], "L": [(150, 320)]}
        fr = make(400, presses, flashes=[(300, 340)])
        self.assertTrue(an.analyze(fr, 60.0, "E2", 0.1, ("ak", "glock"))[0].valid)
        self.assertFalse(an.analyze(fr, 60.0, "E2", 0.1)[0].valid)

    def test_summary(self):
        cs = [an.Cycle("A", 0, valid=True, duration_s=v) for v in (1.0, 1.02, 1.01)] + [an.Cycle("A", 0)]
        s = an.summarize(cs)
        self.assertEqual(s["samples"], 3)
        self.assertAlmostEqual(s["median_s"], 1.01)
        self.assertAlmostEqual(s["max_dev_s"], 0.01)


if __name__ == "__main__":
    unittest.main()
