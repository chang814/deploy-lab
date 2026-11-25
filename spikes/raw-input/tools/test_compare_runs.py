"""compare_runs 的测试（合成数据 + 真实格式的 CSV 文件）。"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compare_runs as cr  # noqa: E402

T0 = "2026-11-25T22:00:00"


def g(n, x, y, note="T1-慢", valid="1", reason="", frac="0", mis="0", time=T0):
    return {"time": time, "round": str(n), "valid": valid, "invalid_reason": reason, "note": note,
            "counts_x": f"{x:.6f}", "counts_y": f"{y:.6f}", "fractional": frac, "mismatch": mis}


def r(n, x, y, valid="1", time=T0, **flags):
    row = {"time": time, "round": str(n), "valid": valid, "raw_x": str(x), "raw_y": str(y),
           "absolute_events": "0", "read_errors": "0", "boundary_motion": "0", "sync_lost": "0"}
    row.update({k: str(v) for k, v in flags.items()})
    return row


def five(note="A", x=3150):
    return [g(i, x, 0, note=note) for i in range(1, 6)], [r(i, x, 0) for i in range(1, 6)]


class CompareTest(unittest.TestCase):
    def test_all_exact_with_enough_rounds_passes(self):
        gg, rr = five()
        self.assertIn("**数据层通过**", cr.verdict(cr.compare(gg, rr)))

    def test_too_few_rounds_is_insufficient(self):
        c = cr.compare([g(1, 3150, -12), g(2, -3149, 4)], [r(1, 3150, -12), r(2, -3149, 4)])
        self.assertIn("**证据不足**", cr.verdict(c))

    def test_zero_motion_rounds_do_not_count(self):
        c = cr.compare([g(1, 0, 0)], [r(1, 0, 0)])
        self.assertEqual(c.no_motion, ["会话1·第1轮"])
        self.assertIn("无法判定", cr.verdict(c))

    def test_proportional_loss_fails(self):
        gg = [g(i, 3150 * 0.995, 0, note="T1-快") for i in range(1, 6)]
        rr = [r(i, 3150, 0) for i in range(1, 6)]
        c = cr.compare(gg, rr)
        self.assertIn("**不通过**", cr.verdict(c))
        self.assertIn("0.995000", cr.render(c))

    def test_many_small_diffs_need_recheck_not_fail(self):
        gg = [g(i, 101, 0) for i in range(1, 5)]
        rr = [r(i, 100, 0) for i in range(1, 5)]
        self.assertIn("**待复核**", cr.verdict(cr.compare(gg, rr)))

    def test_invalid_rounds_are_excluded(self):
        c = cr.compare(
            [g(1, 10, 0), g(2, 99, 0, valid="0", reason="释放了鼠标"), g(3, 5, 0)],
            [r(1, 10, 0), r(2, 50, 0), r(3, 5, 0, valid="0", boundary_motion=1)],
        )
        self.assertEqual([x.key[1] for x in c.compared], [1])
        self.assertEqual(len(c.invalid), 2)
        self.assertIn("boundary_motion", c.invalid[1][1])

    def test_unpaired_rounds_cannot_judge(self):
        c = cr.compare([g(1, 10, 0), g(2, 10, 0)], [r(1, 10, 0)])
        self.assertEqual(c.unpaired_godot, ["会话1·第2轮"])
        self.assertIn("无法判定", cr.verdict(c))

    def test_restart_creates_new_session_and_failure_is_not_hidden(self):
        # 第一次会话第 1 轮失败，重启后第 1 轮成功；不能被「取最后一条」掩盖
        gg = [g(1, 90, 0), g(2, 50, 0), g(1, 100, 0)]
        rr = [r(1, 100, 0), r(2, 50, 0), r(1, 100, 0)]
        c = cr.compare(gg, rr)
        self.assertEqual(c.sessions, (2, 2))
        self.assertEqual(len(c.compared), 3)
        self.assertIn("**不通过**", cr.verdict(c))

    def test_repeated_right_click_pairs_by_occurrence(self):
        gg = [g(1, 3, 0), g(1, 5, 0)]
        rr = [r(1, 3, 0), r(1, 5, 0)]
        c = cr.compare(gg, rr)
        self.assertEqual([(x.godot_x, x.raw_x) for x in c.compared], [(3.0, 3), (5.0, 5)])

    def test_repeated_right_clicks_do_not_inflate_sample_count(self):
        gg = [g(1, 100, 0) for _ in range(5)]
        rr = [r(1, 100, 0) for _ in range(5)]
        self.assertIn("**证据不足**", cr.verdict(cr.compare(gg, rr)))

    def test_session_count_mismatch_cannot_judge(self):
        c = cr.compare([g(1, 1, 0), g(1, 1, 0, time="2026-11-25T22:10:00")], [r(1, 1, 0), r(2, 1, 0)])
        self.assertIn("无法判定", cr.verdict(c))

    def test_time_skew_flags_mispairing(self):
        c = cr.compare([g(1, 1, 0, time="2026-11-25T22:00:00")], [r(1, 1, 0, time="2026-11-25T22:05:00")])
        self.assertEqual(len(c.time_skew), 1)
        self.assertIn("无法判定", cr.verdict(c))

    def test_round_zero_ignored(self):
        c = cr.compare([g(0, 7, 7), g(1, 2, 0)], [r(0, 9, 9), r(1, 2, 0)])
        self.assertEqual([x.key[1] for x in c.compared], [1])

    def test_fractional_godot_counts_not_exact(self):
        c = cr.compare([g(1, 10.5, 0)], [r(1, 10, 0)])
        self.assertFalse(c.compared[0].exact)


class FileFormatTest(unittest.TestCase):
    """用与 main.gd / rawinput_counter.py 相同格式的文件测试解析。"""

    GODOT_HEADER = ("time,round,valid,invalid_reason,note,dpi,sens,counts_x,counts_y,rel_x,rel_y,events,"
                    "fractional,mismatch,max_abs_dx,cm_x,round_yaw_delta_deg,window_mode,viewport_w,viewport_h,content_scale")
    RAW_HEADER = "time,round,valid,raw_x,raw_y,events,absolute_events,read_errors,boundary_motion,sync_lost,devices"

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.dir.cleanup()

    def write(self, name, text, bom=False):
        path = os.path.join(self.dir.name, name)
        with open(path, "w", encoding="utf-8-sig" if bom else "utf-8", newline="") as f:
            f.write(text)
        return path

    def test_real_format_with_bom_chinese_comma_and_quote(self):
        godot = self.write("g.csv", self.GODOT_HEADER + "\n"
                           + '2026-11-25T22:00:00,1,1,,"T1，慢,800,1.000000,-3150.000000,12.000000,-3150.000000,12.000000,'
                           + "40,0,0,120,-10.001250,-69.300000000,0,1280,800,1.0000\n", bom=True)
        raw = self.write("r.csv", self.RAW_HEADER + "\n2026-11-25T22:00:01,1,1,-3150,12,40,0,0,0,0,1\n")
        c = cr.compare(cr.read_csv(godot), cr.read_csv(raw))
        self.assertEqual(len(c.compared), 1)
        self.assertTrue(c.compared[0].exact)
        self.assertEqual(c.compared[0].note, '"T1，慢')


if __name__ == "__main__":
    unittest.main()
