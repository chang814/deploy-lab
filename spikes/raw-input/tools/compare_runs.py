"""按轮号对齐 Godot spike 与 Raw Input 基准的两个 CSV，生成 P0-4 报告的数据部分（Markdown）。

用法：
    python -I compare_runs.py <godot 的 spike_runs.csv> <基准的 rawinput_runs.csv> [--out 报告.md]

判据（见 spikes/raw-input/README.md）：
- 只比较两边都有效（valid=1）的轮次
- 每轮 X、Y 两轴：Godot screen_relative 计数 == 基准原始计数
"""

import argparse
import csv
import statistics
import sys
from dataclasses import dataclass, field

EXACT_TOL = 1e-9  # Godot 记录为 6 位小数的浮点数，基准为整数


@dataclass
class RoundResult:
    round: int
    note: str
    godot_x: float
    godot_y: float
    raw_x: int
    raw_y: int
    fractional: int
    mismatch: int

    @property
    def diff_x(self) -> float:
        return self.godot_x - self.raw_x

    @property
    def diff_y(self) -> float:
        return self.godot_y - self.raw_y

    @property
    def exact(self) -> bool:
        return abs(self.diff_x) <= EXACT_TOL and abs(self.diff_y) <= EXACT_TOL


@dataclass
class Comparison:
    compared: list[RoundResult] = field(default_factory=list)
    godot_only: list[int] = field(default_factory=list)
    raw_only: list[int] = field(default_factory=list)
    invalid: list[tuple[int, str]] = field(default_factory=list)
    duplicates: list[int] = field(default_factory=list)


def _read(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _index_by_round(rows: list[dict], dup_sink: list[int]) -> dict[int, dict]:
    """同一轮被记录多次（重复按右键）时取最后一条，并报告。"""
    out: dict[int, dict] = {}
    for r in rows:
        n = int(r["round"])
        if n in out and n not in dup_sink:
            dup_sink.append(n)
        out[n] = r
    return out


def compare(godot_rows: list[dict], raw_rows: list[dict]) -> Comparison:
    c = Comparison()
    g = _index_by_round(godot_rows, c.duplicates)
    r = _index_by_round(raw_rows, c.duplicates)
    for n in sorted(set(g) | set(r)):
        if n == 0:
            continue  # 第 0 轮是按中键之前，不是测量轮
        if n not in r:
            c.godot_only.append(n)
            continue
        if n not in g:
            c.raw_only.append(n)
            continue
        gr, rr = g[n], r[n]
        reasons = []
        if gr["valid"] != "1":
            reasons.append(f"Godot：{gr.get('invalid_reason') or '无效'}")
        if rr["valid"] != "1":
            flags = [k for k in ("absolute_events", "read_errors", "boundary_motion", "sync_lost") if rr.get(k, "0") not in ("0", "")]
            reasons.append("基准：" + ("、".join(flags) or "无效"))
        if reasons:
            c.invalid.append((n, "；".join(reasons)))
            continue
        c.compared.append(RoundResult(
            round=n, note=gr.get("note", ""),
            godot_x=float(gr["counts_x"]), godot_y=float(gr["counts_y"]),
            raw_x=int(rr["raw_x"]), raw_y=int(rr["raw_y"]),
            fractional=int(gr["fractional"]), mismatch=int(gr["mismatch"]),
        ))
    return c


def _ratio(results: list[RoundResult]) -> str:
    """Godot/基准 的合计位移比例，用来发现「固定比例丢失」。"""
    g = sum(abs(x.godot_x) + abs(x.godot_y) for x in results)
    r = sum(abs(x.raw_x) + abs(x.raw_y) for x in results)
    return "—" if r == 0 else f"{g / r:.6f}"


def render(c: Comparison) -> str:
    lines = ["## 逐轮比对结果（自动生成）", ""]
    total = len(c.compared)
    exact = sum(1 for x in c.compared if x.exact)
    lines.append(f"- 参与比较的有效轮次：**{total}**，完全一致：**{exact}**")
    if c.invalid:
        lines.append(f"- 作废轮次：{len(c.invalid)}（不参与比较）")
    if c.godot_only or c.raw_only:
        lines.append(f"- ⚠ 轮号未对齐：只有 Godot 有 {c.godot_only or '无'}；只有基准有 {c.raw_only or '无'}")
    if c.duplicates:
        lines.append(f"- 注意：以下轮次被记录了多次，取最后一条：{c.duplicates}")
    lines.append("")

    lines += ["### 按备注分组", "",
              "| 备注 | 轮数 | 完全一致 | 最大偏差 X / Y（counts） | 合计比例 Godot/基准 | 含小数事件 | 两路不一致事件 |",
              "|---|---|---|---|---|---|---|"]
    groups: dict[str, list[RoundResult]] = {}
    for x in c.compared:
        groups.setdefault(x.note or "（无备注）", []).append(x)
    for note, rs in groups.items():
        mx = max(abs(x.diff_x) for x in rs)
        my = max(abs(x.diff_y) for x in rs)
        lines.append(f"| {note} | {len(rs)} | {sum(1 for x in rs if x.exact)} | {mx:g} / {my:g} | {_ratio(rs)} | "
                     f"{sum(x.fractional for x in rs)} | {sum(x.mismatch for x in rs)} |")
    lines.append("")

    bad = [x for x in c.compared if not x.exact]
    if bad:
        lines += ["### 不一致的轮次", "", "| 轮 | 备注 | Godot X / Y | 基准 X / Y | 差 X / Y |", "|---|---|---|---|---|"]
        for x in bad:
            lines.append(f"| {x.round} | {x.note} | {x.godot_x:g} / {x.godot_y:g} | {x.raw_x} / {x.raw_y} | {x.diff_x:+g} / {x.diff_y:+g} |")
        lines.append("")

    if c.invalid:
        lines += ["### 作废轮次", "", "| 轮 | 原因 |", "|---|---|"]
        lines += [f"| {n} | {why} |" for n, why in c.invalid]
        lines.append("")

    lines += ["### 初步判定", "", verdict(c), ""]
    return "\n".join(lines)


def verdict(c: Comparison) -> str:
    if c.godot_only or c.raw_only:
        return "**无法判定**：轮号未对齐，请按 README 重启两个程序后重测。"
    if not c.compared:
        return "**无法判定**：没有有效轮次。"
    bad = [x for x in c.compared if not x.exact]
    if not bad:
        return f"**通过**：{len(c.compared)} 个有效轮次两轴计数全部与 Raw Input 完全一致。（T5 与 CS2 的对照需人工填写）"
    diffs = [abs(x.diff_x) + abs(x.diff_y) for x in bad]
    if len(bad) <= 2 and max(diffs) <= 2:
        return (f"**待复核**：{len(bad)} 个轮次有 ≤2 counts 的偏差，可能是点击边界处的移动，"
                "请重测这些条件确认。")
    med = statistics.median(diffs)
    return (f"**不通过**：{len(bad)}/{len(c.compared)} 个轮次不一致（偏差中位数 {med:g} counts）。"
            "请看「合计比例」列判断是固定比例丢失还是随机偏差，并评估改用 GDExtension 读取 Raw Input。")


def main() -> None:
    p = argparse.ArgumentParser(description="P0-4 逐轮比对")
    p.add_argument("godot_csv")
    p.add_argument("raw_csv")
    p.add_argument("--out", help="把结果写入这个 Markdown 文件（默认打印）")
    a = p.parse_args()
    text = render(compare(_read(a.godot_csv), _read(a.raw_csv)))
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"已写入 {a.out}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)


if __name__ == "__main__":
    main()
