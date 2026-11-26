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
         flash_value: int = 1800, sound: bool = True, extra_audio: list[tuple[int, int]] = (),
         ammo_shift: int | None = 0, extra_ammo: list[int] = ()) -> list[an.Frame]:
    """presses：键 → [(亮起帧, 熄灭帧)]；flashes：[(开始帧, 结束帧)] 期间火光指标为 flash_value，
    sound 为真时每段火光开始后 AV_LAG 帧起有枪声；extra_audio：额外的枪声区间。
    ammo_shift：弹药数字在每段火光开始帧 + ammo_shift 变白 2 帧（None = 特征文件没有 ammo 列）；extra_ammo：额外变白的帧。"""
    shots = [(a + AV_LAG, b + AV_LAG) for a, b in flashes] if sound else []
    shots += list(extra_audio)
    ammo_on = ([a + ammo_shift for a, _ in flashes] if ammo_shift is not None else []) + list(extra_ammo)
    frames = []
    for i in range(n):
        lit = {k: any(a <= i < b for a, b in presses.get(k, [])) for k in KEYS}
        flash = flash_value if any(a <= i < b for a, b in flashes) else 0
        audio = 9000.0 if any(a <= i < b for a, b in shots) else 100.0
        ammo = -1 if ammo_shift is None else (500 if any(a <= i < a + 2 for a in ammo_on) else 3)
        frames.append(an.Frame(i / FPS, lit, flash, audio, ammo))
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


class Base(unittest.TestCase):
    def invalid(self, c, text):
        self.assertFalse(c.valid, f"应作废：{text}")
        self.assertIn(text, c.reason)


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


class OverlayRuleTest(unittest.TestCase):
    def test_constants_match_input_overlay(self):
        # 推算点亮时间段用的规则必须与输入显示层一致
        import importlib.util
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "input_overlay", "overlay_state.py")
        spec = importlib.util.spec_from_file_location("overlay_state", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.assertEqual(an.MIN_LIT_S, mod.MIN_LIT_S)
        self.assertEqual(an.WHEEL_LIT_S, mod.WHEEL_FLASH_S)

    def test_spans_follow_overlay_rule(self):
        ps = [an.Press(1.0, "Q", "down"), an.Press(1.02, "Q", "up"), an.Press(1.05, "Q", "down"),
              an.Press(1.3, "Q", "up"), an.Press(2.0, "Q", "down"), an.Press(2.01, "Q", "up")]
        spans = an.predicted_spans(ps, "Q", 10.0)
        self.assertEqual([(round(a, 3), round(b, 3), len(x)) for a, b, x in spans], [(1.0, 1.3, 2), (2.0, 2.1, 1)])


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
        # 第 2 轮反例：无声橙色 [690,693)、真实火光 [694,704)、枪声从 698 开始。
        # 配对窗口按实测收窄为 2–7 帧后，690（早 8 帧）不在窗口内，选中真实火光 694
        fr = make(800, {}, flashes=[(690, 693), (694, 704)], sound=False, extra_audio=[(698, 708)])
        self.assertEqual(an.find_flash(fr, 10, 800)[0], 694)
        # 橙色特效落进窗口（691，早 7 帧）：两段火光开始都可能是开枪 → 作废
        fr = make(800, {}, flashes=[(691, 693), (694, 704)], sound=False, extra_audio=[(698, 708)])
        f, why = an.find_flash(fr, 10, 800)
        self.assertIsNone(f)
        self.assertIn("无法确定", why)

    def test_codex_r3_overlapping_orange_outside_lag_window(self):
        # 第 3 轮反例：橙色特效从 696 一直连到真实火光 [700,710)，枪声 704。只有一个上升沿 696，
        # 但它比枪声早 8 帧，超出实测的 2–7 帧 → 不确认（重叠更紧的情况靠人工抽查）
        fr = make(800, {}, flashes=[(696, 710)], sound=False, extra_audio=[(704, 714)])
        self.assertIsNone(an.find_flash(fr, 10, 800)[0])

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
        self.assertTrue(any("推不出来" in p for p in tl.problems))

    def test_press_inside_lit_period_is_merged(self):
        tl = timeline(make(600, self.P), self.P, extra=[(103 / FPS, "1", "down"), (104 / FPS, "1", "up")])
        self.assertEqual([p.status for p in tl.presses if p.key == "1" and p.event == "down"],
                         ["shown", "merged", "shown"])

    def test_press_never_shown_is_missing(self):
        tl = timeline(make(600, self.P), self.P, extra=[(50 / FPS, "2", "down"), (52 / FPS, "2", "up")])
        self.assertEqual([p.status for p in tl.presses if p.key == "2" and p.event == "down"], ["missing"])

    def test_codex_r3_merged_presses_cannot_shift_alignment(self):
        # 第 3 轮反例：F 在 30/60/90 帧亮起，每次亮起期间又快速按了两次（f+2、f+2.2 帧）；
        # Q 在 120 帧亮起，记录里 120 与 122.1 帧各一次。旧版投票被合并的按下带偏到 +30 ms
        overlay = {"F": [(30, 40), (60, 70), (90, 100)], "Q": [(120, 130)], "L": [(150, 320)]}
        log = {"F": [(30, 31), (60, 61), (90, 91)], "Q": [(120, 121)], "L": [(150, 320)]}
        extra = []
        for f in (30, 60, 90):
            extra += [((f + 2) / FPS, "F", "down"), ((f + 2.1) / FPS, "F", "up"),
                      ((f + 2.2) / FPS, "F", "down"), ((f + 2.3) / FPS, "F", "up")]
        extra += [(122.1 / FPS, "Q", "down"), (122.5 / FPS, "Q", "up")]
        fr = make(400, overlay, flashes=[(300, 340)])
        tl = timeline(fr, log, extra)
        self.assertEqual(tl.problems, [])
        self.assertAlmostEqual(tl.offset, -DISPLAY_LAG, delta=0.004)
        qs = [p for p in tl.presses if p.key == "Q" and p.event == "down"]
        self.assertEqual([p.status for p in qs], ["shown", "merged"])
        self.assertFalse(any(c.valid for c in an.analyze(fr, FPS, "E1", 0.1, ("glock", "ak"), tl)))

    def test_codex_r3_unshown_press_before_onset_is_missing(self):
        # 第 3 轮反例的变体：R 在 190 帧按下、191 帧松开（按显示层规则应亮到 196 帧），录像里没亮；
        # 200 帧另一次 R 才亮起 → 漏显示，整段作废。
        # （原反例 198 帧按下：按规则应在 198 亮起，录像 200 才亮，差 33 ms，在实测显示延迟范围内，
        #   两次按下合成一段，与「延迟 33 ms」自洽，无法也不必判为漏显示）
        p = dict(self.P, R=[(200, 210)])
        tl = timeline(make(600, p), p, [(190 / FPS, "R", "down"), (191 / FPS, "R", "up")])
        self.assertIn("missing", [p.status for p in tl.presses if p.key == "R" and p.event == "down"])
        self.assertTrue(any("录像里没有" in x for x in tl.problems))

    def test_codex_r3_original_input_is_ambiguous(self):
        # 第 3 轮原反例保留：R 198 帧按下、199 帧松开，录像 200 帧才亮（另一次按下在 200 帧）。
        # 按显示层规则两次按下合成一段 [198,206)，录像 [200,210) 与「显示延迟 33 ms」自洽，工具判为一致。
        # 这不证明没有漏显示，只说明这组数据分辨不出来；它不影响切枪起点（R 与切枪无关）。人类已知悉此行为变化
        p = dict(self.P, R=[(200, 210)])
        tl = timeline(make(600, p), p, [(198 / FPS, "R", "down"), (199 / FPS, "R", "up")])
        self.assertEqual(tl.problems, [])
        self.assertEqual([x.status for x in tl.presses if x.key == "R" and x.event == "down"], ["shown", "merged"])

    def test_codex_r4_press_after_lit_period_ended_is_missing(self):
        # 第 4 轮反例：R 显示于 [200,206)，第 207 帧又按下、208 帧松开，录像里没亮 → 不能算合并
        p = dict(self.P, R=[(200, 206)])
        tl = timeline(make(600, p), p, [(207 / FPS, "R", "down"), (208 / FPS, "R", "up")])
        # 按规则应在 207 帧再亮起；录像里 206 熄灭后没有再亮 → 漏显示，整段作废
        self.assertTrue(any("录像里没有" in x for x in tl.problems), tl.problems)
        # 间隔拉开到 4 帧（第 210 帧按下）：单独成段，录像里没有 → 漏显示
        tl = timeline(make(600, p), p, [(210 / FPS, "R", "down"), (211 / FPS, "R", "up")])
        self.assertEqual([x.status for x in tl.presses if x.key == "R" and x.event == "down"], ["shown", "missing"])
        self.assertTrue(any("录像里没有" in x for x in tl.problems))

    def test_codex_r4_fast_double_press_is_merged(self):
        # 第 4 轮反例：F 显示于 [30,38)，记录两次按住 [30,31)、[31.5,32)。按显示层规则两次合成一段，
        # 第二次是合并，对齐不能被带偏
        p = dict(self.P, F=[(30, 38)])
        log = dict(self.P, F=[(30, 31)])
        tl = timeline(make(600, p), log, [(31.5 / FPS, "F", "down"), (32 / FPS, "F", "up")])
        self.assertEqual(tl.problems, [])
        self.assertAlmostEqual(tl.offset, -DISPLAY_LAG, delta=0.004)
        self.assertEqual([x.status for x in tl.presses if x.key == "F" and x.event == "down"], ["shown", "merged"])

    def test_codex_r5_missing_release_near_video_end(self):
        # 第 5 轮反例：R 显示 [200,206)，记录缺了松开 → 推算一直亮到录像结束，录像里早熄了 → 矛盾
        p = dict(self.P, R=[(200, 206)])
        log = [x for x in log_from(p) if not (x[1] == "R" and x[2] == "up")]
        tl = an.build_timeline(make(600, p), FPS, log, OBS)
        self.assertTrue(any("应亮到" in x for x in tl.problems), tl.problems)

    def test_codex_r5_one_frame_dark_gap_is_two_spans(self):
        # 第 5 轮反例：R 显示与记录都是 [200,206)、[207,213)，中间 1 帧暗帧录像看得到 → 两段都对上
        p = dict(self.P, R=[(200, 206), (207, 213)])
        tl = timeline(make(600, p), p)
        self.assertEqual(tl.problems, [])
        self.assertEqual([x.status for x in tl.presses if x.key == "R" and x.event == "down"], ["shown", "shown"])

    def test_short_gap_not_visible_is_merged(self):
        # 记录两段间隔不到 1 帧，录像里没有暗帧、连成 [200,213) → 以录像为准合并
        p = dict(self.P, R=[(200, 213)])
        log = dict(self.P, R=[(200, 206)])
        tl = timeline(make(600, p), log, [(206.5 / FPS, "R", "down"), (207 / FPS, "R", "up")])
        self.assertEqual(tl.problems, [])
        self.assertEqual([x.status for x in tl.presses if x.key == "R" and x.event == "down"], ["shown", "merged"])

    def test_codex_r5_unshown_press_at_video_start_is_missing(self):
        # 第 5 轮反例：记录在第 2 帧按 R，录像完全没亮 → 漏显示（以前开头 100 ms 不比较）
        tl = timeline(make(600, self.P), self.P, [(2 / FPS, "R", "down"), (3 / FPS, "R", "up")])
        self.assertTrue(any("录像里没有" in x for x in tl.problems), tl.problems)

    def test_codex_r5_shown_press_at_video_start_is_ok(self):
        # 第 5 轮反例：记录与录像都在第 2 帧亮起 R [2,8) → 一致
        p = dict(self.P, R=[(2, 8)])
        tl = timeline(make(600, p), p)
        self.assertEqual(tl.problems, [])

    def test_key_held_before_video_start(self):
        # 录像开始前就按住了 F（第 0 帧亮着），录像中松开 → 一致；如果录像第 0 帧没亮 → 矛盾
        p = dict(self.P, F=[(0, 20)])
        log = log_from(self.P, [(-0.5, "F", "down"), (20 / FPS, "F", "up")])
        self.assertEqual(an.build_timeline(make(600, p), FPS, log, OBS).problems, [])
        self.assertTrue(an.build_timeline(make(600, self.P), FPS, log, OBS).problems)

    def test_codex_r6_long_hold_before_lookback_is_checked(self):
        # 第 6 轮反例：R 在录像前 11 s 按下、第 20 帧松开，录像里 R 完全没亮 → 第 0 帧本应亮着，矛盾
        log = log_from(self.P, [(-11.0, "R", "down"), (20 / FPS, "R", "up")])
        self.assertTrue(an.build_timeline(make(600, self.P), FPS, log, OBS).problems)
        # 录像正确显示 R [0,20) → 一致（不再误杀）
        p = dict(self.P, R=[(0, 20)])
        self.assertEqual(an.build_timeline(make(600, p), FPS, log, OBS).problems, [])

    def test_lit_period_end_must_match(self):
        # 记录说 1 按住到 300 帧，录像里 1 只亮到 106 帧 → 结束对不上
        p = dict(self.P)
        log = dict(self.P, **{"1": [(100, 300), (400, 406)]})
        tl = timeline(make(600, p), log)
        self.assertTrue(any("应亮到" in x for x in tl.problems))

    def test_double_down_is_inconsistent(self):
        tl = timeline(make(600, self.P), self.P, extra=[(103 / FPS, "1", "down")])
        self.assertTrue(any("连续两次" in p for p in tl.problems))

    def test_frame_times_must_be_continuous(self):
        fr = make(100, {})
        self.assertEqual(an.timeline_problems(fr, FPS), [])
        fr[50] = an.Frame(fr[50].t + 0.01, fr[50].lit, 0)
        self.assertTrue(an.timeline_problems(fr, FPS))

    def test_codex_r3_nan_time_is_rejected(self):
        fr = make(100, {})
        fr[50] = an.Frame(float("nan"), fr[50].lit, 0)
        self.assertTrue(an.timeline_problems(fr, FPS))
        self.assertTrue(an.timeline_problems(make(10, {}), float("nan")))


class AnalyzeTest(Base):
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
        self.invalid(cs[0], "左键已经按着")

    def test_left_pressed_late_is_invalid(self):
        cs = self.run_cycle(presses={"L": [(295, 320)]})
        self.invalid(cs[0], "按晚")

    def test_codex_early_tap_does_not_hide_late_press(self):
        cs = self.run_cycle(presses={"L": [(150, 156), (296, 340)]})
        self.invalid(cs[0], "按晚")

    def test_codex_r2_merged_taps_do_not_hide_late_press(self):
        # 第 2 轮反例：280/285/290 三次轻点被输入显示层合成一次亮起，295 才真正按住，300 开火。
        # 录像里左键格子从 280 一直亮着，但记录显示开火时的这次按住只早 5 帧 → 作废
        overlay = {"L": [(280, 340)]}
        log = dict(self.BASE, L=[(280, 282)])
        taps = [(285 / FPS, "L", "down"), (287 / FPS, "L", "up"), (290 / FPS, "L", "down"),
                (292 / FPS, "L", "up"), (295 / FPS, "L", "down"), (340 / FPS, "L", "up")]
        cs = self.run_cycle(presses=overlay, log_presses=log, log_extra=taps)
        self.assertFalse(cs[0].valid)
        self.invalid(cs[0], "按晚")

    def test_codex_r3_missing_left_release_is_invalid(self):
        # 第 3 轮反例：左键格子只亮于 [150,160)，记录里有按下、缺了松开；300 帧开火
        overlay = {"L": [(150, 160)]}
        log = {k: v for k, v in self.BASE.items() if k != "L"}
        cs = self.run_cycle(presses=overlay, log_presses=log, log_extra=[(150 / FPS, "L", "down")])
        self.invalid(cs[0], "整段录像作废")   # 按记录左键应一直亮，录像里 160 帧就熄了 → 结束对不上
        self.assertIn("应亮到", cs[0].reason)

    def test_codex_r3_unshown_press_invalidates_cycle(self):
        overlay = {"R": [(200, 210)]}
        cs = self.run_cycle(presses=overlay, log_extra=[(190 / FPS, "R", "down"), (191 / FPS, "R", "up")])
        self.invalid(cs[0], "整段录像作废")

    def test_left_lead_uses_worst_case_offset(self):
        # 左键在火光前 13 帧（217 ms）按住：按估计偏移够 0.2 s；对齐区间最不利的一端扣掉后不够 → 作废
        p = dict(self.BASE, L=[(287, 320)])
        fr = make(400, p, flashes=[(300, 340)])
        tl = timeline(fr, p)
        self.assertGreater(tl.offset - tl.offset_lo, 0.017)   # 合成数据下候选区间有一定宽度
        self.invalid(an.analyze(fr, FPS, "A", 0.1, (None, None), tl)[0], "最不利")

    def test_offset_range_is_reported(self):
        p = dict(self.BASE)
        tl = timeline(make(400, p, flashes=[(300, 340)]), p)
        self.assertLessEqual(tl.offset_lo, tl.offset)
        self.assertLessEqual(tl.offset, tl.offset_hi + 1e-9)

    def test_presses_before_video_do_not_change_weapon_tracking(self):
        # 录像开始前按过 2（若参与推算，手里会变成 Glock）；武器推算只以 --initial 声明为准，
        # 录像前的切枪按键不参与，否则 A（刀 → AK）会被推成别的方向
        # （去掉 BASE 里录像内的那次 3，否则它会把手里重置成刀、掩盖问题）
        base = {k: v for k, v in self.BASE.items() if k != "3"}
        base["R"] = [(60, 66)]   # 补一段与切枪无关的按键，保证对齐有足够的配对
        log = log_from(base, [(-2.0, "2", "down"), (-1.95, "2", "up")])
        fr = make(400, base, flashes=[(300, 340)])
        tl = an.build_timeline(fr, FPS, log, OBS)
        self.assertEqual(tl.problems, [])
        self.assertTrue(any(x.t < 0 and x.key == "2" for x in tl.presses))   # 录像前的事件仍在时间线里
        cs = an.analyze(fr, FPS, "A", 0.1, ("knife", "ak"), tl)
        self.assertEqual(len(cs), 1)
        self.assertTrue(cs[0].valid, cs[0].reason)
        # 录像前的滚轮也不参与（否则手里会变成「不知道」）
        log = log_from(base, [(-0.5, "wheel", "wheel")])
        tl = an.build_timeline(fr, FPS, log, OBS)
        self.assertTrue(an.analyze(fr, FPS, "A", 0.1, ("knife", "ak"), tl)[0].valid)

    def test_codex_r6_left_held_since_before_video(self):
        # 第 6 轮反例：左键在录像前 0.5 s 按下、第 120 帧松开（切枪在第 100 帧，那时左键按着）→ 作废
        overlay = {"L": [(0, 120), (150, 320)]}
        log = {k: v for k, v in self.BASE.items() if k != "L"}
        log["L"] = [(150, 320)]
        cs = self.run_cycle(presses=overlay, log_presses=log,
                            log_extra=[(-0.5 + DISPLAY_LAG, "L", "down"), (120 / FPS, "L", "up")])
        self.invalid(cs[0], "左键已经按着")

    def test_codex_r6_trigger_lit_at_frame_zero_is_invalid(self):
        # 第 6 轮反例：切枪键 1 在第 0 帧就亮着（记录在第 2 帧按下），看不到亮起时刻 → 作废
        overlay = {"3": [], "1": [(0, 8)]}
        log = dict(self.BASE, **{"3": [], "1": [(2, 8)]})
        cs = self.run_cycle(presses=overlay, log_presses=log, initial=("knife", "ak"))
        self.invalid(cs[0], "第 0 帧就亮着")

    def test_left_released_before_shot_is_invalid(self):
        cs = self.run_cycle(presses={"L": [(150, 200)]})
        self.invalid(cs[0], "没有按着")

    def test_wrong_direction_is_invalid(self):
        cs = self.run_cycle(presses={"3": [], "2": [(10, 16)]})
        self.invalid(cs[0], "方向")

    def test_unknown_start_is_invalid_unless_declared(self):
        self.assertFalse(self.run_cycle(presses={"3": []})[0].valid)
        cs = self.run_cycle(presses={"3": []}, initial=("knife", "ak"))
        self.assertTrue(cs[0].valid, cs[0].reason)

    def test_no_shot_is_invalid(self):
        self.invalid(self.run_cycle(flashes=())[0], "没有开枪")

    def test_gunshot_but_no_flash_reason(self):
        cs = self.run_cycle(flashes=(), extra_audio=[(300, 310)])
        self.invalid(cs[0], "没有找到与之配对的火光")

    def test_codex_merged_double_press(self):
        # 两次快速按 1 合成一次亮起：第一次的窗口在第二次按下前结束（找不到开枪）；第二次没有自己的亮起
        # 记录里第一次按 1 在第 101 帧就松开了，第 103 帧又按下：格子仍是一次亮起 [100,106)
        log = dict(self.BASE, **{"1": [(100, 101)]})
        cs = self.run_cycle(log_presses=log, log_extra=[(103 / FPS, "1", "down"), (104 / FPS, "1", "up")])
        self.assertEqual(len(cs), 2)
        self.assertFalse(cs[0].valid)
        self.assertFalse(cs[1].valid)
        self.invalid(cs[0], "没有开枪")
        self.invalid(cs[1], "没有自己的格子亮起")

    def test_codex_r2_merged_q_history_is_tracked_from_log(self):
        # 第 2 轮反例：第 10 帧按 Q，第 13 帧又按了一次 Q 被合并进同一次亮起。录像只看到一次 Q，
        # 但记录里是两次：手里仍是 AK。第 100 帧的 Q 是 AK → Glock，不是 E1 要的 Glock → AK
        p = {"Q": [(10, 16), (100, 106)], "L": [(150, 320)]}
        fr = make(400, p, flashes=[(300, 340)])
        tl = timeline(fr, dict(p, Q=[(10, 11), (100, 106)]), [(13 / FPS, "Q", "down"), (14 / FPS, "Q", "up")])
        self.assertEqual(tl.problems, [])
        cs = an.analyze(fr, FPS, "E1", 0.1, ("ak", "glock"), tl)
        self.invalid(cs[-1], "方向")
        self.assertEqual(an.analyze(fr, FPS, "E2", 0.1, ("ak", "glock"), tl)[-1].reason, "")

    def test_missing_display_near_cycle_is_invalid(self):
        cs = self.run_cycle(log_extra=[(200 / FPS, "2", "down"), (202 / FPS, "2", "up")])
        self.assertFalse(cs[0].valid)

    def test_missing_display_of_left_button_is_invalid(self):
        cs = self.run_cycle(log_extra=[(250 / FPS, "R", "down"), (252 / FPS, "R", "up")])
        self.invalid(cs[0], "整段录像作废")

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

    def test_shot_frame_is_ammo_change(self):
        # 弹药数字比火光早 1 帧（火光很暗那一帧没达到阈值）：开枪帧取弹药数字那一帧
        cs = self.run_cycle(ammo_shift=-1)
        self.assertTrue(cs[0].valid, cs[0].reason)
        self.assertEqual((cs[0].flash_frame, cs[0].shot_frame), (300, 299))
        self.assertAlmostEqual(cs[0].duration_s, 199 / FPS * 0.1)

    def test_ammo_and_flash_must_agree(self):
        self.invalid(self.run_cycle(ammo_shift=1)[0], "对不上")      # 弹药数字晚于火光
        self.invalid(self.run_cycle(ammo_shift=-2)[0], "对不上")     # 早于实测范围（0–1 帧）
        self.invalid(self.run_cycle(ammo_shift=-1, extra_ammo=[200])[0], "2 次")   # 更早有一次变白

    def test_codex_pr34_white_interference_before_shot(self):
        # PR #34 第 1 轮反例：真实变化在 300，第 298 帧另有白色干扰（合成数据里每次变白持续 2 帧，
        # 所以 298–301 连成一段、只有一个上升沿 298）→ 比火光早 2 帧，超出实测 0–1 帧 → 作废
        self.invalid(self.run_cycle(extra_ammo=[298])[0], "对不上")
        # 干扰与真实变化之间有间隔（297–298 变白，299 恢复，300 再变白）→ 两次变白，无法确定 → 作废
        self.invalid(self.run_cycle(extra_ammo=[297])[0], "无法确定")

    def test_codex_pr34_r3_interference_far_before_late_change(self):
        # PR #34 第 3 轮反例：299–300 白色干扰、301–305 暗、306 真实变化（不在任何固定窗口内）。
        # 之后没有第二段火光 → 检查范围到窗口结束 → 两次变白 → 作废
        self.invalid(self.run_cycle(ammo_shift=6, extra_ammo=[299])[0], "无法确定")

    def test_codex_pr34_r4_unconfirmed_orange_cannot_cut_window(self):
        # PR #34 第 4 轮反例：真实火光 [300,306)，299 白色干扰，306 真实变化，307 一帧无声橙色。
        # 单帧、无枪声的橙色不算「下一发」，不能截断检查范围 → 两次变白 → 作废
        p = dict(self.BASE)
        fr = make(400, p, flashes=[(300, 306)], ammo_shift=6, extra_ammo=[299])
        fr[307] = an.Frame(fr[307].t, fr[307].lit, 1800, fr[307].audio, fr[307].ammo)
        cs = an.analyze(fr, FPS, "A", 0.1, (None, None), timeline(fr, p))
        self.invalid(cs[0], "无法确定")

    def test_second_shot_ammo_one_frame_before_its_flash(self):
        # 连射第二发：弹药数字（359）比它的火光（360）早 1 帧 → 属于第二发，不算冲突
        cs = self.run_cycle(flashes=((300, 310), (360, 370)), extra_ammo=[359])
        self.assertTrue(cs[0].valid, cs[0].reason)
        self.assertEqual(cs[0].shot_frame, 300)

    def test_spray_shots_with_own_flash_are_not_conflicts(self):
        # 连射：第二发有自己的火光（360 开始）和弹药变化（360）→ 不算冲突，第一发仍有效
        cs = self.run_cycle(flashes=((300, 310), (360, 370)))
        self.assertTrue(cs[0].valid, cs[0].reason)
        self.assertEqual(cs[0].shot_frame, 300)
        # 第二发的弹药数字比它的火光早 1 帧（359）也不算冲突
        cs = self.run_cycle(flashes=((300, 310),), extra_ammo=[359], extra_audio=[(364, 374)])
        self.assertFalse(cs[0].valid)   # 没有第二段火光时，359 的变白就是冲突

    def test_codex_pr34_r2_interference_then_late_change(self):
        # PR #34 第 2 轮反例：299 帧变白（干扰）、300 帧暗、301 帧真实变化（比火光晚 1 帧）→ 两次变白 → 作废
        p = dict(self.BASE)
        fr = make(400, p, flashes=[(300, 340)], ammo_shift=1)
        fr[299] = an.Frame(fr[299].t, fr[299].lit, fr[299].flash, fr[299].audio, 500)
        fr[300] = an.Frame(fr[300].t, fr[300].lit, fr[300].flash, fr[300].audio, 3)
        cs = an.analyze(fr, FPS, "A", 0.1, (None, None), timeline(fr, p))
        self.invalid(cs[0], "无法确定")

    def test_seamless_white_interference_is_a_known_limit(self):
        # 已知局限：干扰在火光前 1 帧且与真实变化无缝相连 → 只有一个上升沿 299，工具会取 299（早 1 帧）。
        # 这与人工抽查里「火光很暗、数字早 1 帧」的真实情形分不开，由人工逐帧抽查兜底
        cs = self.run_cycle(extra_ammo=[299])
        self.assertTrue(cs[0].valid, cs[0].reason)
        self.assertEqual(cs[0].shot_frame, 299)

    def test_white_after_flash_without_own_flash_is_conflict(self):
        # 火光之后再变白、但这次变白没有自己的火光（不是连射的下一发）→ 是干扰 → 作废
        # （连射的下一发有自己的火光，见 test_spray_shots_with_own_flash_are_not_conflicts）
        self.invalid(self.run_cycle(extra_ammo=[310])[0], "无法确定")

    def test_no_ammo_change_is_invalid(self):
        self.invalid(self.run_cycle(ammo_shift=500)[0], "没有看到弹药数字变化")

    def test_old_features_without_ammo_column(self):
        self.invalid(self.run_cycle(ammo_shift=None)[0], "ammo 列")

    def test_samples_csv_header_must_match(self):
        import tempfile
        d = tempfile.mkdtemp()
        path = os.path.join(d, "s.csv")
        an.append_samples(path, [["A", "x", 1, 2, 2, "0.1", 1, ""]])
        an.append_samples(path, [["A", "x", 3, 4, 4, "0.1", 1, ""]])
        with open(path, encoding="utf-8") as f:
            self.assertEqual(len(f.read().strip().splitlines()), 3)
        old = os.path.join(d, "old.csv")
        with open(old, "w", encoding="utf-8") as f:
            f.write("item,video,start_frame,flash_frame,duration_s,valid,reason\n")
        with self.assertRaises(ValueError):
            an.append_samples(old, [["A", "x", 1, 2, 2, "0.1", 1, ""]])
        # 合法文件末尾没有换行：追加时不能和上一行粘在一起
        import csv as _csv
        for content in (",".join(an.SAMPLES_HEADER), ",".join(an.SAMPLES_HEADER) + "\r\nA,x,1,2,2,0.1,1,"):
            path2 = os.path.join(d, "nonl.csv")
            with open(path2, "w", encoding="utf-8", newline="") as f:
                f.write(content)
            an.append_samples(path2, [["B", "y", 5, 6, 6, "0.2", 1, ""]])
            with open(path2, encoding="utf-8", newline="") as f:
                rows = list(_csv.reader(f))
            self.assertEqual(rows[0], an.SAMPLES_HEADER)
            self.assertEqual(rows[-1], ["B", "y", "5", "6", "6", "0.2", "1", ""])
            self.assertTrue(all(len(r) == len(an.SAMPLES_HEADER) for r in rows))

    def test_summary(self):
        cs = [an.Cycle("A", 0, 0.0, valid=True, duration_s=v) for v in (1.0, 1.02, 1.01)] + [an.Cycle("A", 0, 0.0)]
        s = an.summarize(cs)
        self.assertEqual(s["samples"], 3)
        self.assertAlmostEqual(s["median_s"], 1.01)
        self.assertAlmostEqual(s["max_dev_s"], 0.01)


if __name__ == "__main__":
    unittest.main()
