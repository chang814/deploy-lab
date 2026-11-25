"""compare_runs 的测试（合成 CSV 行）。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compare_runs as cr  # noqa: E402


def g(n, x, y, note="T1-慢", valid="1", reason="", frac="0", mis="0"):
    return {"round": str(n), "valid": valid, "invalid_reason": reason, "note": note,
            "counts_x": f"{x:.6f}", "counts_y": f"{y:.6f}", "fractional": frac, "mismatch": mis}


def r(n, x, y, valid="1", **flags):
    row = {"round": str(n), "valid": valid, "raw_x": str(x), "raw_y": str(y),
           "absolute_events": "0", "read_errors": "0", "boundary_motion": "0", "sync_lost": "0"}
    row.update({k: str(v) for k, v in flags.items()})
    return row


class CompareTest(unittest.TestCase):
    def test_all_exact_passes(self):
        c = cr.compare([g(1, 3150, -12), g(2, -3149, 4)], [r(1, 3150, -12), r(2, -3149, 4)])
        self.assertEqual(len(c.compared), 2)
        self.assertTrue(all(x.exact for x in c.compared))
        self.assertIn("**通过**", cr.verdict(c))

    def test_proportional_loss_fails(self):
        rows_g = [g(i, 3150 * 0.995, 0, note="T1-快") for i in range(1, 6)]
        rows_r = [r(i, 3150, 0) for i in range(1, 6)]
        c = cr.compare(rows_g, rows_r)
        self.assertIn("**不通过**", cr.verdict(c))
        self.assertIn("0.995000", cr.render(c))

    def test_small_boundary_diff_needs_recheck(self):
        c = cr.compare([g(1, 3151, 0), g(2, 100, 0)], [r(1, 3150, 0), r(2, 100, 0)])
        self.assertIn("**待复核**", cr.verdict(c))

    def test_invalid_rounds_are_excluded(self):
        c = cr.compare(
            [g(1, 10, 0), g(2, 99, 0, valid="0", reason="释放了鼠标"), g(3, 5, 0)],
            [r(1, 10, 0), r(2, 50, 0), r(3, 5, 0, valid="0", boundary_motion=1)],
        )
        self.assertEqual([x.round for x in c.compared], [1])
        self.assertEqual([n for n, _ in c.invalid], [2, 3])
        self.assertIn("boundary_motion", c.invalid[1][1])

    def test_misaligned_rounds_cannot_judge(self):
        c = cr.compare([g(1, 10, 0), g(2, 10, 0)], [r(1, 10, 0)])
        self.assertEqual(c.godot_only, [2])
        self.assertIn("无法判定", cr.verdict(c))

    def test_round_zero_ignored_and_duplicates_reported(self):
        c = cr.compare([g(0, 7, 7), g(1, 1, 0), g(1, 2, 0)], [r(0, 9, 9), r(1, 2, 0)])
        self.assertEqual([x.round for x in c.compared], [1])
        self.assertEqual(c.compared[0].godot_x, 2.0)  # 取最后一条
        self.assertEqual(c.duplicates, [1])

    def test_fractional_godot_counts_not_exact(self):
        c = cr.compare([g(1, 10.5, 0)], [r(1, 10, 0)])
        self.assertFalse(c.compared[0].exact)

    def test_render_groups_by_note(self):
        c = cr.compare([g(1, 1, 0, note="A"), g(2, 1, 0, note="B")], [r(1, 1, 0), r(2, 1, 0)])
        text = cr.render(c)
        self.assertIn("| A | 1 | 1 |", text)
        self.assertIn("| B | 1 | 1 |", text)


if __name__ == "__main__":
    unittest.main()
