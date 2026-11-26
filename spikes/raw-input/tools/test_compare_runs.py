"""compare_runs 的测试（合成数据 + 真实格式的 CSV 文件）。"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compare_runs as cr  # noqa: E402

T0 = 1_800_000_000.0


def g(n, x, y, t, note="T1-慢", valid="1", reason="", frac="0", mis="0"):
    return {"time": "", "t_unix": f"{t:.3f}", "round": str(n), "valid": valid, "invalid_reason": reason,
            "note": note, "counts_x": f"{x:.6f}", "counts_y": f"{y:.6f}", "fractional": frac, "mismatch": mis}


def r(n, x, y, t, valid="1", **flags):
    row = {"time": "", "t_unix": f"{t:.3f}", "round": str(n), "valid": valid, "raw_x": str(x), "raw_y": str(y),
           "absolute_events": "0", "read_errors": "0", "boundary_motion": "0", "sync_lost": "0"}
    row.update({k: str(v) for k, v in flags.items()})
    return row


def five(note="A", x=3150):
    return ([g(i, x, 0, T0 + 10 * i, note=note) for i in range(1, 6)],
            [r(i, x, 0, T0 + 10 * i + 0.004) for i in range(1, 6)])


class CompareTest(unittest.TestCase):
    def test_all_exact_with_enough_rounds_passes(self):
        gg, rr = five()
        self.assertIn("**数据层通过**", cr.verdict(cr.compare(gg, rr)))

    def test_extra_raw_rows_from_other_windows_are_ignored(self):
        gg, rr = five()
        # 测试人在 Windows 设置里点了几次中键、右键：基准多出几行，轮号也和 Godot 错开
        rr += [r(90, 7, 7, T0 + 15), r(91, 0, 0, T0 + 16), r(92, 3, 3, T0 + 33.9)]
        c = cr.compare(gg, rr)
        self.assertEqual(c.raw_extra, 3)
        self.assertIn("**数据层通过**", cr.verdict(c))

    def test_godot_row_without_baseline_cannot_judge(self):
        gg, rr = five()
        gg.append(g(6, 1, 0, T0 + 100))
        c = cr.compare(gg, rr)
        self.assertEqual(len(c.godot_unpaired), 1)
        self.assertIn("无法判定", cr.verdict(c))

    def test_two_baseline_rows_in_window_is_ambiguous(self):
        c = cr.compare([g(1, 5, 0, T0)], [r(1, 9, 0, T0 - 0.4), r(2, 5, 0, T0 + 0.01)])
        self.assertEqual(len(c.ambiguous), 1)
        self.assertIn("无法判定", cr.verdict(c))

    def test_codex_counterexample_delay_is_not_hidden(self):
        # 基准两次右键 (100.000s, 100) 和 (100.200s, 90)；Godot 有效行 100.210s=90，重复作废行 100.220s
        gg, rr = five()
        gg += [g(9, 90, 0, T0 + 100.21), g(9, 90, 0, T0 + 100.22, valid="0", reason="重复记录")]
        rr += [r(9, 100, 0, T0 + 100.0), r(10, 90, 0, T0 + 100.2)]
        c = cr.compare(gg, rr)
        self.assertNotIn("通过", cr.verdict(c))
        self.assertIn("无法判定", cr.verdict(c))

    def test_outside_window_not_paired(self):
        c = cr.compare([g(1, 5, 0, T0)], [r(1, 5, 0, T0 + 0.8)])
        self.assertEqual(len(c.godot_unpaired), 1)

    def test_too_few_rounds_is_insufficient(self):
        c = cr.compare([g(1, 3150, -12, T0), g(2, -3149, 4, T0 + 5)], [r(1, 3150, -12, T0), r(2, -3149, 4, T0 + 5)])
        self.assertIn("**证据不足**", cr.verdict(c))

    def test_repeated_right_clicks_do_not_inflate_sample_count(self):
        gg = [g(1, 100, 0, T0 + i) for i in range(5)]
        rr = [r(1, 100, 0, T0 + i) for i in range(5)]
        self.assertIn("**证据不足**", cr.verdict(cr.compare(gg, rr)))

    def test_zero_motion_rows_do_not_count(self):
        c = cr.compare([g(1, 0, 0, T0)], [r(1, 0, 0, T0)])
        self.assertEqual(len(c.no_motion), 1)
        self.assertIn("无法判定", cr.verdict(c))

    def test_proportional_loss_fails(self):
        gg = [g(i, 3150 * 0.995, 0, T0 + i, note="T1-快") for i in range(1, 6)]
        rr = [r(i, 3150, 0, T0 + i) for i in range(1, 6)]
        c = cr.compare(gg, rr)
        self.assertIn("**不通过**", cr.verdict(c))
        self.assertIn("0.995000", cr.render(c))

    def test_many_small_diffs_need_recheck_not_fail(self):
        gg = [g(i, 101, 0, T0 + i) for i in range(1, 5)]
        rr = [r(i, 100, 0, T0 + i) for i in range(1, 5)]
        self.assertIn("**待复核**", cr.verdict(cr.compare(gg, rr)))

    def test_invalid_rows_are_excluded(self):
        c = cr.compare(
            [g(1, 10, 0, T0), g(2, 99, 0, T0 + 1, valid="0", reason="跨步骤"), g(3, 5, 0, T0 + 2)],
            [r(1, 10, 0, T0), r(2, 50, 0, T0 + 1), r(3, 5, 0, T0 + 2, valid="0", boundary_motion=1)],
        )
        self.assertEqual([x.key[2] for x in c.compared], [1])
        self.assertEqual(len(c.invalid), 2)
        self.assertIn("boundary_motion", c.invalid[1][1])

    def test_restart_failure_is_not_hidden(self):
        gg = [g(1, 90, 0, T0), g(2, 50, 0, T0 + 1), g(1, 100, 0, T0 + 60)]
        rr = [r(1, 100, 0, T0), r(2, 50, 0, T0 + 1), r(1, 100, 0, T0 + 60)]
        c = cr.compare(gg, rr)
        self.assertEqual({x.key for x in c.compared}, {(1, 1, 1), (1, 1, 2), (1, 2, 1)})
        self.assertIn("**不通过**", cr.verdict(c))

    def test_merge_two_runs_completes_groups(self):
        # 第一次只有 4 轮，补测 1 轮（轮号同样从 1 开始），合并后满 5 轮
        g1 = [g(i, 10, 0, T0 + i) for i in range(1, 5)]
        r1 = [r(i, 10, 0, T0 + i) for i in range(1, 5)]
        g2, r2 = [g(1, 20, 0, T0 + 500)], [r(1, 20, 0, T0 + 500)]
        first = cr.compare(g1, r1, run=1)
        self.assertIn("**证据不足**", cr.verdict(first))
        merged = cr.merge([first, cr.compare(g2, r2, run=2)])
        self.assertEqual(len({x.key for x in merged.compared}), 5)
        self.assertIn("**数据层通过**", cr.verdict(merged))
        self.assertIn("第2组文件", cr.render(merged) + merged.compared[-1].label)

    def test_same_data_twice_is_rejected(self):
        gg = [g(i, 10, 0, T0 + i) for i in range(1, 5)]
        with self.assertRaises(cr.FormatError):
            cr.check_no_overlap([gg, [dict(x) for x in gg]])
        cr.check_no_overlap([gg, [g(1, 10, 0, T0 + 500)]])  # 不同记录可以合并

    def test_fractional_godot_counts_not_exact(self):
        c = cr.compare([g(1, 10.5, 0, T0)], [r(1, 10, 0, T0)])
        self.assertFalse(c.compared[0].exact)


class FileFormatTest(unittest.TestCase):
    """用与 main.gd / rawinput_counter.py 相同格式的文件测试解析。"""

    GODOT_HEADER = ("time,t_unix,round,valid,invalid_reason,note,dpi,sens,counts_x,counts_y,rel_x,rel_y,events,"
                    "fractional,mismatch,max_abs_dx,cm_x,round_yaw_delta_deg,window_mode,viewport_w,viewport_h,content_scale")
    RAW_HEADER = "time,t_unix,round,valid,raw_x,raw_y,events,absolute_events,read_errors,boundary_motion,sync_lost,devices"

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
                           + '2026-11-25T22:00:00,1800000000.123,1,1,,"T1，慢,800,1.000000,-3150.000000,12.000000,'
                           + "-3150.000000,12.000000,40,0,0,120,-10.001250,-69.300000000,0,1280,800,1.0000\n", bom=True)
        raw = self.write("r.csv", self.RAW_HEADER + "\n2026-11-25T22:00:00,1800000000.130,4,1,-3150,12,40,0,0,0,0,1\n")
        c = cr.compare(cr.read_csv(godot), cr.read_csv(raw))
        self.assertEqual(len(c.compared), 1)
        self.assertTrue(c.compared[0].exact)
        self.assertEqual(c.compared[0].note, '"T1，慢')

    def test_header_matches_counter(self):
        import rawinput_counter as rc
        self.assertEqual(",".join(rc.CSV_HEADER), self.RAW_HEADER)

    def _legacy(self, n, t, x, note="T1-慢"):
        gg = {"time": t, "round": str(n), "valid": "1", "invalid_reason": "", "note": note,
              "counts_x": f"{x:.6f}", "counts_y": "0.000000", "fractional": "0", "mismatch": "0"}
        rr = {"time": t, "round": str(n), "valid": "1", "raw_x": str(x), "raw_y": "0",
              "absolute_events": "0", "read_errors": "0", "boundary_motion": "0", "sync_lost": "0"}
        return gg, rr

    def test_legacy_format_pairs_in_order(self):
        rows = [self._legacy(i, f"2026-11-25T23:4{i}:00", 100 + i) for i in range(1, 6)]
        c = cr.compare([a for a, _ in rows], [b for _, b in rows])
        self.assertTrue(c.legacy)
        self.assertIn("**数据层通过**", cr.verdict(c))

    def test_legacy_format_rejects_shifted_rounds(self):
        # Godot 第 1–5 轮，基准第 2–6 轮（漏首行、多末行），时间都在相邻秒内
        gs = [self._legacy(i, f"2026-11-25T23:40:0{i}", 100)[0] for i in range(1, 6)]
        rs = [self._legacy(i + 1, f"2026-11-25T23:40:0{i}", 100)[1] for i in range(1, 6)]
        with self.assertRaises(cr.FormatError):
            cr.compare(gs, rs)

    def test_legacy_format_rejects_mismatched_rows(self):
        a, b = self._legacy(1, "2026-11-25T23:40:00", 5)
        with self.assertRaises(cr.FormatError):
            cr.compare([a], [b, b])
        b2 = {**b, "time": "2026-11-25T23:41:00"}
        with self.assertRaises(cr.FormatError):
            cr.compare([a], [b2])


if __name__ == "__main__":
    unittest.main()
