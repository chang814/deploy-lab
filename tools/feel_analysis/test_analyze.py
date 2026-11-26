"""analyze.py 的测试（合成帧序列与按键记录，不需要录像）。包含 GPT 两轮审查给出的反例。

运行：python -I -B -m unittest discover -s tools/feel_analysis -p "test_*.py"
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import analyze as an  # noqa: E402

KEYS = list(an.OVERLAY_KEYS)
AV_LAG = 4  # 合成数据里枪声比火光晚的帧数（实测 3–5）
FPS = 60.0
OBS = 1_800_000_000.0   # 合成的 OBS 开录时刻
DISPLAY_LAG = 0.005     # 合成的「按下 → 格子亮起」延迟


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


def log_from(presses: dict[str, list[tuple[int, int]]], extra: list[tuple[float, str, str]] = (),
             shift: float = 0.0) -> list[tuple[float, str, str]]:
    """由合成按键生成 unix 时间的按键记录：每段亮起 = 一次按下（亮起前 DISPLAY_LAG）+ 熄灭时松开。
    extra：额外的 (录像时间, 键, 事件)。shift：整体平移（模拟对不上）。"""
    out = []
    for k, spans in presses.items():
        for a, b in spans:
            if k == "wheel":
                out.append((a / FPS - DISPLAY_LAG, k, "wheel"))
            else:
                out += [(a / FPS - DISPLAY_LAG, k, "down"), (b / FPS - DISPLAY_LAG, k, "up")]
    out += [(t - DISPLAY_LAG, k, e) for t, k, e in extra]
    return sorted((OBS + t + shift, k, e) for t, k, e in out)


def timeline(frames, presses, extra=(), shift=0.0):
    return an.build_timeline(frames, FPS, log_from(presses, extra, shift), OBS)


class TrackerTest(unittest.TestCase):
    def test_onset_ignores_already_lit_first_frame(self):
        fr = make(20, {"1": [(0, 5), (10, 12)]})
        self.assertEqual(an.onsets(fr, "1"), [10])

    def test_select_keys(self):
        self.assertEqual(an.track_weapons(["3", "1"]), [(None, "knife"), ("knife", "ak")])

    def test_q_swaps(self):
        st = an.track_weapons(["1", "2", "Q", "Q"])
        self.assertEqual(st[2], ("glock", "ak"))
        self.assertEqual(st[3], ("ak", "glock"))

    def test_q_without_previous_is_unknown(self):
        self.assertEqual(an.track_weapons(["1", "Q"])[1], ("ak", None))

    def test_same_key_twice_keeps_previous(self):
        self.assertEqual(an.track_weapons(["2", "1", "1", "Q"])[3], ("ak", "glock"))

    def test_wheel_is_unknown(self):
        self.assertEqual(an.track_weapons(["1", "wheel"])[1], ("ak", None))

    def test_initial_state(self):
        self.assertEqual(an.track_weapons(["Q"], ("ak", "glock"))[0], ("ak", "glock"))


class ArgsTest(unittest.TestCase):
    def test_parse_initial(self):
        self.assertEqual(an.parse_initial("knife,ak"), ("knife", "ak"))
        self.assertEqual(an.parse_initial("ak,-"), ("ak", None))
        self.assertEqual(an.parse_initial("?,?"), (None, None))

    def test_rejects_bad_initial(self):
        for bad in ("ak", "ak,glock,knife", "m4,ak"):
            with self.assertRaises(ValueError):
                an.parse_initial(bad)

    def test_start_needs_milliseconds(self):
        self.assertAlmostEqual(an.parse_start("2026-11-26 11:39:34.437") % 1, 0.437, places=3)
        with self.assertRaises(ValueError):
            an.parse_start("2026-11-26 11:39:34")


class FlashTest(unittest.TestCase):
    def test_detects_first_flash_frame(self):
        self.assertEqual(an.find_flash(make(200, {}, flashes=[(100, 110)]), 10, 200)[0], 100)

    def test_small_glock_flash_detected(self):
        self.assertEqual(an.find_flash(make(200, {}, flashes=[(100, 110)], flash_value=600), 10, 200)[0], 100)

    def test_flash_without_gunshot_is_not_a_shot(self):
        f, why = an.find_flash(make(200, {}, flashes=[(100, 110)], sound=False), 10, 200)
        self.assertIsNone(f)
        self.assertIn("没有开枪", why)

    def test_gunshot_without_flash(self):
        f, why = an.find_flash(make(200, {}, extra_audio=[(100, 110)]), 10, 200)
        self.assertIsNone(f)
        self.assertIn("没有找到与之配对的火光", why)

    def test_short_orange_is_not_a_flash(self):
        f, why = an.find_flash(make(200, {}, flashes=[(100, 101)]), 10, 200)
        self.assertIsNone(f)
        self.assertIn("只持续 1 帧", why)

    def test_unrelated_orange_far_before_shot_is_ignored(self):
        # 第 600 帧无声橙色特效（离枪声远），第 700 帧真实火光
        fr = make(800, {}, flashes=[(600, 605), (700, 710)])
        fr = [an.Frame(x.t, x.lit, x.flash, 9000.0 if 704 <= i < 714 else 100.0) for i, x in enumerate(fr)]
        self.assertEqual(an.find_flash(fr, 10, 800)[0], 700)

    def test_codex_r2_nearby_orange_makes_flash_ambiguous(self):
        # 第 2 轮反例：无声橙色 [690,693)、真实火光 [694,704)、枪声从 698 开始。两段都在配对窗口内 → 作废
        fr = make(800, {}, flashes=[(690, 693), (694, 704)], sound=False, extra_audio=[(698, 708)])
        f, why = an.find_flash(fr, 10, 800)
        self.assertIsNone(f)
        self.assertIn("无法确定", why)

    def test_codex_pairing_does_not_cross_end(self):
        # 第 695 帧橙色、第 700 帧下一次切枪、第 704 帧枪声：不能确认前一个周期
        fr = make(800, {}, flashes=[(695, 700)], sound=False, extra_audio=[(704, 714)])
        self.assertIsNone(an.find_flash(fr, 10, 700)[0])

    def test_gunshot_already_ongoing_is_not_an_onset(self):
        fr = make(300, {}, flashes=[(100, 110)], sound=False, extra_audio=[(90, 130)])
        self.assertIsNone(an.find_flash(fr, 10, 300)[0])

    def test_below_threshold_ignored(self):
        fr = make(200, {}, flashes=[(100, 110)], flash_value=an.FLASH_MIN - 1)
        self.assertIsNone(an.find_flash(fr, 10, 200)[0])


class TimelineTest(unittest.TestCase):
    P = {"1": [(100, 106), (400, 406)], "3": [(250, 256)], "Q": [(500, 506)]}

    def test_alignment_recovers_display_lag(self):
        tl = timeline(make(600, self.P), self.P)
        self.assertEqual(tl.problems, [])
        self.assertGreaterEqual(tl.pairs, 3)
        self.assertAlmostEqual(tl.offset, -DISPLAY_LAG, places=3)
        self.assertTrue(all(p.status == "shown" for p in tl.presses if an.is_press(p.event)))

    def test_codex_r2_one_second_shift_is_rejected(self):
        # 第 2 轮反例：旧版 ±2 s 的搜索能接受整体错开 1 s 的配对；现在只在 OBS 开录时刻 ±0.15 s 内找
        tl = timeline(make(600, self.P), self.P, shift=1.0)
        self.assertTrue(tl.problems)

    def test_codex_r2_overlay_press_without_log_rejects_video(self):
        # 第 2 轮反例：录像里亮了一次 3，记录里没有 → 整段录像作废
        fr = make(600, dict(self.P, **{"3": [(250, 256), (550, 556)]}))
        tl = timeline(fr, self.P)
        self.assertTrue(any("没有对应的按下" in p for p in tl.problems))

    def test_press_inside_lit_period_is_merged(self):
        tl = timeline(make(600, self.P), self.P, extra=[(103 / FPS, "1", "down"), (104 / FPS, "1", "up")])
        self.assertEqual([p.status for p in tl.presses if p.key == "1" and p.event == "down"],
                         ["shown", "merged", "shown"])

    def test_press_never_shown_is_missing(self):
        tl = timeline(make(600, self.P), self.P, extra=[(50 / FPS, "2", "down"), (52 / FPS, "2", "up")])
        self.assertEqual([p.status for p in tl.presses if p.key == "2" and p.event == "down"], ["missing"])

    def test_frame_times_must_be_continuous(self):
        fr = make(100, {})
        self.assertEqual(an.timeline_problems(fr, FPS), [])
        fr[50] = an.Frame(fr[50].t + 0.01, fr[50].lit, 0)
        self.assertTrue(an.timeline_problems(fr, FPS))


class AnalyzeTest(unittest.TestCase):
    # F 与切枪无关，只是让对齐有足够的配对
    BASE = {"F": [(30, 36)], "3": [(10, 16)], "1": [(100, 106)], "L": [(150, 320)]}

    def run_cycle(self, item="A", initial=(None, None), presses=None, flashes=((300, 340),), log_extra=(),
                  log_presses=None, n=400, **kw):
        p = dict(self.BASE)
        p.update(presses or {})
        fr = make(n, p, flashes=list(flashes), **kw)
        tl = timeline(fr, p if log_presses is None else log_presses, log_extra)
        return an.analyze(fr, FPS, item, 0.1, initial, tl)

    def test_valid_cycle_duration(self):
        cs = self.run_cycle()
        self.assertEqual(len(cs), 1)
        self.assertTrue(cs[0].valid, cs[0].reason)
        self.assertAlmostEqual(cs[0].duration_s, 200 / FPS * 0.1)

    def test_left_held_before_trigger_is_invalid(self):
        cs = self.run_cycle(presses={"L": [(90, 320)]})
        self.assertIn("左键已经按着", cs[0].reason)

    def test_left_pressed_late_is_invalid(self):
        cs = self.run_cycle(presses={"L": [(295, 320)]})
        self.assertIn("按晚", cs[0].reason)

    def test_codex_early_tap_does_not_hide_late_press(self):
        cs = self.run_cycle(presses={"L": [(150, 156), (296, 340)]})
        self.assertIn("按晚", cs[0].reason)

    def test_codex_r2_merged_taps_do_not_hide_late_press(self):
        # 第 2 轮反例：280/285/290 三次轻点被输入显示层合成一次亮起，295 才真正按住，300 开火。
        # 录像里左键格子从 280 一直亮着，但记录显示开火时的这次按住只早 5 帧 → 作废
        overlay = {"L": [(280, 340)]}
        log = dict(self.BASE, L=[(280, 282)])
        taps = [(285 / FPS, "L", "down"), (287 / FPS, "L", "up"), (290 / FPS, "L", "down"),
                (292 / FPS, "L", "up"), (295 / FPS, "L", "down"), (340 / FPS, "L", "up")]
        cs = self.run_cycle(presses=overlay, log_presses=log, log_extra=taps)
        self.assertFalse(cs[0].valid)
        self.assertIn("按晚", cs[0].reason)

    def test_left_released_before_shot_is_invalid(self):
        cs = self.run_cycle(presses={"L": [(150, 200)]})
        self.assertIn("没有按着", cs[0].reason)

    def test_wrong_direction_is_invalid(self):
        cs = self.run_cycle(presses={"3": [], "2": [(10, 16)]})
        self.assertIn("方向", cs[0].reason)

    def test_unknown_start_is_invalid_unless_declared(self):
        self.assertFalse(self.run_cycle(presses={"3": []})[0].valid)
        cs = self.run_cycle(presses={"3": []}, initial=("knife", "ak"))
        self.assertTrue(cs[0].valid, cs[0].reason)

    def test_no_shot_is_invalid(self):
        self.assertIn("没有开枪", self.run_cycle(flashes=())[0].reason)

    def test_gunshot_but_no_flash_reason(self):
        cs = self.run_cycle(flashes=(), extra_audio=[(300, 310)])
        self.assertIn("没有找到与之配对的火光", cs[0].reason)

    def test_codex_merged_double_press(self):
        # 两次快速按 1 合成一次亮起：第一次的窗口在第二次按下前结束（找不到开枪）；第二次没有自己的亮起
        cs = self.run_cycle(log_extra=[(103 / FPS, "1", "down"), (104 / FPS, "1", "up")])
        self.assertEqual(len(cs), 2)
        self.assertIn("没有开枪", cs[0].reason)
        self.assertIn("没有自己的格子亮起", cs[1].reason)

    def test_codex_r2_merged_q_history_is_tracked_from_log(self):
        # 第 2 轮反例：第 10 帧按 Q，第 13 帧又按了一次 Q 被合并进同一次亮起。录像只看到一次 Q，
        # 但记录里是两次：手里仍是 AK。第 100 帧的 Q 是 AK → Glock，不是 E1 要的 Glock → AK
        p = {"Q": [(10, 16), (100, 106)], "L": [(150, 320)]}
        fr = make(400, p, flashes=[(300, 340)])
        tl = timeline(fr, p, [(13 / FPS, "Q", "down"), (14 / FPS, "Q", "up")])
        cs = an.analyze(fr, FPS, "E1", 0.1, ("ak", "glock"), tl)
        self.assertIn("方向", cs[-1].reason)
        self.assertEqual(an.analyze(fr, FPS, "E2", 0.1, ("ak", "glock"), tl)[-1].reason, "")

    def test_missing_display_near_cycle_is_invalid(self):
        cs = self.run_cycle(log_extra=[(200 / FPS, "2", "down"), (202 / FPS, "2", "up")])
        self.assertFalse(cs[0].valid)

    def test_missing_display_of_left_button_is_invalid(self):
        cs = self.run_cycle(log_extra=[(250 / FPS, "R", "down"), (252 / FPS, "R", "up")])
        self.assertIn("没有显示", cs[0].reason)

    def test_whole_video_rejected_on_timeline_problem(self):
        p = dict(self.BASE)
        fr = make(400, p, flashes=[(300, 340)])
        tl = timeline(fr, p, shift=1.0)
        cs = an.analyze(fr, FPS, "A", 0.1, (None, None), tl)
        self.assertTrue(cs == [] or "整段录像作废" in cs[0].reason)

    def test_e2_with_declared_initial_state(self):
        p = {"F": [(30, 36)], "Q": [(100, 106)], "L": [(150, 320)]}
        fr = make(400, p, flashes=[(300, 340)])
        tl = timeline(fr, p)
        self.assertTrue(an.analyze(fr, FPS, "E2", 0.1, ("ak", "glock"), tl)[0].valid)
        self.assertFalse(an.analyze(fr, FPS, "E2", 0.1, (None, None), tl)[0].valid)

    def test_summary(self):
        cs = [an.Cycle("A", 0, 0.0, valid=True, duration_s=v) for v in (1.0, 1.02, 1.01)] + [an.Cycle("A", 0, 0.0)]
        s = an.summarize(cs)
        self.assertEqual(s["samples"], 3)
        self.assertAlmostEqual(s["median_s"], 1.01)
        self.assertAlmostEqual(s["max_dev_s"], 0.01)


if __name__ == "__main__":
    unittest.main()
