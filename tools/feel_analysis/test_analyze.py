"""analyze.py 的测试（合成帧序列，不需要录像）。包含 GPT 审查给出的反例。

运行：python -I -B -m unittest discover -s tools/feel_analysis -p "test_*.py"
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as an  # noqa: E402

KEYS = ["1", "2", "3", "Q", "F", "wheel", "L", "R"]
AV_LAG = 4  # 合成数据里枪声比火光晚的帧数（实测 3–5）
FPS = 60.0


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
        frames.append(an.Frame(i / FPS, lit, flash, audio))
    return frames


def vlog_from(presses: dict[str, list[tuple[int, int]]], extra: list[tuple[float, str]] = ()) -> list[tuple[float, str]]:
    """由合成按键生成「已换算成录像时间」的按键记录：每次亮起对应一次按下。"""
    out = [(a / FPS, k) for k, spans in presses.items() if k in an.SWITCH_KEYS for a, _ in spans]
    return sorted(out + list(extra))


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
        self.assertEqual(an.find_flash(make(200, {}, flashes=[(100, 110)]), 10, 200), 100)

    def test_small_glock_flash_detected(self):
        self.assertEqual(an.find_flash(make(200, {}, flashes=[(100, 110)], flash_value=600), 10, 200), 100)

    def test_flash_without_gunshot_is_not_a_shot(self):
        self.assertIsNone(an.find_flash(make(200, {}, flashes=[(100, 110)], sound=False), 10, 200))

    def test_gunshot_without_flash(self):
        fr = make(200, {}, extra_audio=[(100, 110)])
        self.assertIsNone(an.find_flash(fr, 10, 200))
        self.assertTrue(an.has_gunshot(fr, 10, 200))

    def test_single_frame_orange_is_ignored(self):
        fr = make(200, {}, flashes=[(100, 101)])
        self.assertIsNone(an.find_flash(fr, 10, 200))

    def test_codex_orange_effect_cannot_borrow_later_gunshot(self):
        # 第 690 帧无声橙色特效，第 700 帧真实火光，第 704 帧枪声：应返回 700，而不是 690
        fr = make(800, {}, flashes=[(690, 695), (700, 710)])
        fr = [an.Frame(x.t, x.lit, x.flash, 9000.0 if 704 <= i < 714 else 100.0) for i, x in enumerate(fr)]
        self.assertEqual(an.find_flash(fr, 10, 800), 700)

    def test_codex_pairing_does_not_cross_end(self):
        # 第 695 帧橙色、第 700 帧下一次切枪、第 704 帧枪声：不能确认前一个周期
        fr = make(800, {}, flashes=[(695, 700)], sound=False, extra_audio=[(704, 714)])
        self.assertIsNone(an.find_flash(fr, 10, 700))

    def test_gunshot_already_ongoing_is_not_an_onset(self):
        # 枪声在火光前就已经持续（例如连射中途），没有新的枪声开始，不能确认
        fr = make(300, {}, flashes=[(100, 110)], sound=False, extra_audio=[(90, 130)])
        self.assertIsNone(an.find_flash(fr, 10, 300))

    def test_below_threshold_ignored(self):
        self.assertIsNone(an.find_flash(make(200, {}, flashes=[(100, 110)], flash_value=an.FLASH_MIN - 1), 10, 200))


class AnalyzeTest(unittest.TestCase):
    BASE = {"3": [(10, 16)], "1": [(100, 106)], "L": [(150, 320)]}

    def run_cycle(self, item="A", initial=(None, None), presses=None, flashes=((300, 340),), vlog="auto",
                  log_extra=(), **kw):
        p = dict(self.BASE)
        p.update(presses or {})
        fr = make(400, p, flashes=list(flashes), **kw)
        log = vlog_from(p, log_extra) if vlog == "auto" else vlog
        return an.analyze(fr, FPS, item, 0.1, initial, log)

    def test_valid_cycle_duration(self):
        cs = self.run_cycle()
        self.assertEqual(len(cs), 1)
        self.assertTrue(cs[0].valid, cs[0].reason)
        self.assertAlmostEqual(cs[0].duration_s, 200 / FPS * 0.1)

    def test_left_held_before_trigger_is_invalid(self):
        cs = self.run_cycle(presses={"L": [(90, 320)]})
        self.assertFalse(cs[0].valid)
        self.assertIn("左键已经按着", cs[0].reason)

    def test_left_pressed_late_is_invalid(self):
        cs = self.run_cycle(presses={"L": [(295, 320)]})
        self.assertFalse(cs[0].valid)
        self.assertIn("按晚", cs[0].reason)

    def test_codex_early_tap_does_not_hide_late_press(self):
        # 先轻点左键 [150,156)，很晚才再按住 [296,340)：开火时的这次按住只早 4 帧，应作废
        cs = self.run_cycle(presses={"L": [(150, 156), (296, 340)]})
        self.assertFalse(cs[0].valid)
        self.assertIn("按晚", cs[0].reason)

    def test_left_released_before_shot_is_invalid(self):
        cs = self.run_cycle(presses={"L": [(150, 200)]})
        self.assertFalse(cs[0].valid)
        self.assertIn("没有按着", cs[0].reason)

    def test_wrong_direction_is_invalid(self):
        cs = self.run_cycle(presses={"3": [], "2": [(10, 16)]})
        self.assertFalse(cs[0].valid)
        self.assertIn("方向", cs[0].reason)

    def test_unknown_start_is_invalid_unless_declared(self):
        self.assertFalse(self.run_cycle(presses={"3": []})[0].valid)
        cs = self.run_cycle(presses={"3": []}, initial=("knife", "ak"))
        self.assertTrue(cs[0].valid, cs[0].reason)

    def test_no_shot_is_invalid(self):
        cs = self.run_cycle(flashes=())
        self.assertFalse(cs[0].valid)
        self.assertIn("没有开枪", cs[0].reason)

    def test_gunshot_but_no_flash_reason(self):
        cs = self.run_cycle(flashes=(), extra_audio=[(300, 310)])
        self.assertIn("没有找到与之配对的火光", cs[0].reason)

    def test_without_key_log_is_invalid(self):
        cs = self.run_cycle(vlog=None)
        self.assertFalse(cs[0].valid)
        self.assertIn("按键记录", cs[0].reason)

    def test_codex_merged_double_press_is_invalid(self):
        # 两次快速按 1 合成一次亮起：记录里在亮起期间有两次按下
        cs = self.run_cycle(log_extra=[(103 / FPS, "1")])
        self.assertFalse(cs[0].valid)
        self.assertIn("2 次按下", cs[0].reason)

    def test_codex_key_missing_from_video_is_invalid(self):
        # 记录里有一次按 2，录像里没有亮起：武器推算不可靠
        cs = self.run_cycle(log_extra=[(50 / FPS, "2")])
        self.assertFalse(cs[0].valid)
        self.assertIn("没有亮起", cs[0].reason)

    def test_e2_with_declared_initial_state(self):
        p = {"Q": [(100, 106)], "L": [(150, 320)]}
        fr = make(400, p, flashes=[(300, 340)])
        self.assertTrue(an.analyze(fr, FPS, "E2", 0.1, ("ak", "glock"), vlog_from(p))[0].valid)
        self.assertFalse(an.analyze(fr, FPS, "E2", 0.1, (None, None), vlog_from(p))[0].valid)

    def test_summary(self):
        cs = [an.Cycle("A", 0, valid=True, duration_s=v) for v in (1.0, 1.02, 1.01)] + [an.Cycle("A", 0)]
        s = an.summarize(cs)
        self.assertEqual(s["samples"], 3)
        self.assertAlmostEqual(s["median_s"], 1.01)
        self.assertAlmostEqual(s["max_dev_s"], 0.01)


class AlignTest(unittest.TestCase):
    def test_align_recovers_offset(self):
        presses = {"1": [(100, 106), (400, 406)], "3": [(250, 256)], "Q": [(500, 506)]}
        fr = make(600, presses)
        true_start = 1_800_000_000.437
        log = [(true_start + t + 0.008, k) for t, k in vlog_from(presses)]  # 记录比画面早 8 ms
        start, pairs = an.align_log(fr, log, 1_800_000_000.0)
        self.assertGreaterEqual(pairs, 3)
        self.assertAlmostEqual(start, true_start + 0.008, places=3)

    def test_log_in_video_window(self):
        log = [(99.0, "1"), (100.5, "2"), (200.0, "3")]
        self.assertEqual(an.log_in_video(log, 100.0, 600, 60.0), [(0.5, "2")])


if __name__ == "__main__":
    unittest.main()
