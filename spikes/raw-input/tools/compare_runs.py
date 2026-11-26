"""把 Godot spike 与 Raw Input 基准的两个 CSV 逐条配对，生成 P0-4 报告的数据部分（Markdown）。

用法：
    python -I compare_runs.py <godot 的 spike_runs.csv> <基准的 rawinput_runs.csv> [--out 报告.md]

配对方式：两边在同一次鼠标右键时各写一行，每行都带系统时钟的毫秒时间戳 t_unix，
按时间戳配对（相差不超过 MAX_PAIR_SKEW_S）。
- 基准收到的是整个系统的点击（包括在其他窗口里改设置时的点击），所以基准多出来的行是正常的，只做提示
- Godot 有、基准找不到对应行，说明基准漏记或程序不同步，判为无法判定

判据（见 spikes/raw-input/README.md）：
- 只比较两边都有效（valid=1）且有移动的记录
- X、Y 两轴：Godot screen_relative 计数 == 基准原始计数
- 每个备注分组至少 MIN_ROUNDS_PER_GROUP 个不同的轮次
"""

import argparse
import csv
import os
import statistics
import sys
from dataclasses import dataclass, field

EXACT_TOL = 1e-9  # Godot 记录为 6 位小数的浮点数，基准为整数
MIN_ROUNDS_PER_GROUP = 5
MAX_PAIR_SKEW_S = 0.5
SMALL_DIFF_COUNTS = 2


class FormatError(Exception):
    pass


@dataclass
class RoundResult:
    key: tuple[int, int, int]  # (第几组文件, Godot 会话, Godot 轮号)
    t: float
    note: str
    godot_x: float
    godot_y: float
    raw_x: int
    raw_y: int
    fractional: int
    mismatch: int

    @property
    def label(self) -> str:
        return _label(self.key)

    @property
    def diff_x(self) -> float:
        return self.godot_x - self.raw_x

    @property
    def diff_y(self) -> float:
        return self.godot_y - self.raw_y

    @property
    def exact(self) -> bool:
        return abs(self.diff_x) <= EXACT_TOL and abs(self.diff_y) <= EXACT_TOL

    @property
    def moved(self) -> bool:
        return self.raw_x != 0 or self.raw_y != 0 or self.godot_x != 0 or self.godot_y != 0


@dataclass
class Comparison:
    compared: list[RoundResult] = field(default_factory=list)
    godot_unpaired: list[str] = field(default_factory=list)
    raw_extra: int = 0
    invalid: list[tuple[str, str]] = field(default_factory=list)
    no_motion: list[str] = field(default_factory=list)
    ambiguous: list[str] = field(default_factory=list)
    legacy: bool = False


LEGACY_MAX_SKEW_S = 2.0


def read_csv(path: str) -> list[dict]:
    # 两个程序写出的 CSV 都不使用引号（备注中的逗号、引号已在写入时替换），按无引号解析
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, quoting=csv.QUOTE_NONE))


def _legacy_time(row: dict) -> float:
    import datetime
    return datetime.datetime.fromisoformat(row["time"].strip()).timestamp()


def _with_legacy_times(godot_rows: list[dict], raw_rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """旧格式（没有 t_unix）：只能按出现顺序一一配对，要求两边行数相同，且每对的秒级时间相差 ≤2 秒。
    配对成功后给两边写入同一个 t_unix，交给常规流程处理。"""
    if len(godot_rows) != len(raw_rows):
        raise FormatError(f"旧格式记录只能按顺序配对，但两边行数不同（Godot {len(godot_rows)} / 基准 {len(raw_rows)}）")
    g_out, r_out = [], []
    for i, (gr, rr) in enumerate(zip(godot_rows, raw_rows)):
        tg, tr = _legacy_time(gr), _legacy_time(rr)
        if abs(tg - tr) > LEGACY_MAX_SKEW_S:
            raise FormatError(f"旧格式第 {i + 1} 行两边时间相差 {abs(tg - tr):.0f} 秒，无法按顺序配对")
        # 旧版两个程序都只在中键时加轮号、同时启动，轮号必须逐行相同；否则说明错位（例如一边漏记一行）
        if gr["round"] != rr["round"]:
            raise FormatError(f"旧格式第 {i + 1} 行轮号不一致（Godot {gr['round']} / 基准 {rr['round']}），无法证明对应关系")
        g_out.append({**gr, "t_unix": f"{i:.3f}"})
        r_out.append({**rr, "t_unix": f"{i:.3f}"})
    return g_out, r_out


def _godot_keys(rows: list[dict]) -> list[tuple[int, int]]:
    """Godot 的轮号在程序重启后从头开始；轮号变小处视为新会话。"""
    keys, session, prev = [], 1, None
    for r in rows:
        n = int(r["round"])
        if prev is not None and n < prev:
            session += 1
        prev = n
        keys.append((session, n))
    return keys


def _label(key: tuple[int, int, int]) -> str:
    run, session, n = key
    return (f"第{run}组文件·" if run > 1 else "") + f"会话{session}·第{n}轮"


def compare(godot_rows: list[dict], raw_rows: list[dict], run: int = 1) -> Comparison:
    c = Comparison()
    legacy = (godot_rows and "t_unix" not in godot_rows[0]) or (raw_rows and "t_unix" not in raw_rows[0])
    if legacy:
        godot_rows, raw_rows = _with_legacy_times(godot_rows, raw_rows)
        c.legacy = True
    keys = [(run, s, n) for s, n in _godot_keys(godot_rows)]
    g = sorted(zip(keys, godot_rows), key=lambda kr: float(kr[1]["t_unix"]))
    r = sorted(raw_rows, key=lambda row: float(row["t_unix"]))
    tr = [float(row["t_unix"]) for row in r]
    tgs = [float(gr["t_unix"]) for _, gr in g]

    def within(a: float, b: float) -> bool:
        return abs(a - b) <= MAX_PAIR_SKEW_S

    # 只接受「双向唯一」的配对：时间窗口内恰好一行基准，且这行基准的窗口内也恰好只有这一行 Godot。
    # 两边记录的是处理/写入时刻，毫秒时间戳不能保证就是同一次点击，所以有歧义时宁可判为无法判定。
    used = [False] * len(r)
    for gi, (key, gr) in enumerate(g):
        tg = tgs[gi]
        label = f"{_label(key)}（{gr.get('time', '')}）"
        cands = [k for k in range(len(r)) if within(tr[k], tg)]
        if not cands:
            c.godot_unpaired.append(label)
            continue
        if len(cands) > 1 or sum(1 for t in tgs if within(t, tr[cands[0]])) > 1:
            c.ambiguous.append(label)
            for k in cands:
                used[k] = True
            continue
        best = cands[0]
        used[best] = True
        rr = r[best]
        reasons = []
        if gr["valid"] != "1":
            reasons.append(f"Godot：{gr.get('invalid_reason') or '无效'}")
        if rr["valid"] != "1":
            flags = [f for f in ("absolute_events", "read_errors", "boundary_motion", "sync_lost") if rr.get(f, "0") not in ("0", "")]
            reasons.append("基准：" + ("、".join(flags) or "无效"))
        if reasons:
            c.invalid.append((label, "；".join(reasons)))
            continue
        res = RoundResult(
            key=key, t=tg, note=gr.get("note", ""),
            godot_x=float(gr["counts_x"]), godot_y=float(gr["counts_y"]),
            raw_x=int(rr["raw_x"]), raw_y=int(rr["raw_y"]),
            fractional=int(gr["fractional"]), mismatch=int(gr["mismatch"]),
        )
        if not res.moved:
            c.no_motion.append(label)
            continue
        c.compared.append(res)
    c.raw_extra = used.count(False)
    return c


def _row_signature(row: dict) -> tuple:
    return (row.get("time", ""), row.get("t_unix", ""), row.get("round", ""),
            row.get("counts_x", ""), row.get("counts_y", ""), row.get("note", ""))


def check_no_overlap(godot_runs: list[list[dict]]) -> None:
    """多对文件合并前检查：不同文件里不能出现完全相同的 Godot 记录（例如把同一份数据复制了一份），否则会重复计数。"""
    seen: dict[tuple, int] = {}
    for i, rows in enumerate(godot_runs, start=1):
        for row in rows:
            sig = _row_signature(row)
            if sig in seen and seen[sig] != i:
                raise FormatError(f"第 {seen[sig]} 组和第 {i} 组文件包含相同的记录（{row.get('time', '')} 第 {row.get('round', '')} 轮），会重复计数")
            seen.setdefault(sig, i)


def merge(parts: list[Comparison]) -> Comparison:
    """把多次测试（多对文件）的结果合并成一份。"""
    out = Comparison()
    for p in parts:
        out.compared += p.compared
        out.godot_unpaired += p.godot_unpaired
        out.raw_extra += p.raw_extra
        out.invalid += p.invalid
        out.no_motion += p.no_motion
        out.ambiguous += p.ambiguous
        out.legacy = out.legacy or p.legacy
    return out


def _groups(c: Comparison) -> dict[str, list[RoundResult]]:
    groups: dict[str, list[RoundResult]] = {}
    for x in c.compared:
        groups.setdefault(x.note or "（无备注）", []).append(x)
    return groups


def _ratio(results: list[RoundResult]) -> str:
    """Godot/基准 的合计位移比例，用来发现「固定比例丢失」。"""
    g = sum(abs(x.godot_x) + abs(x.godot_y) for x in results)
    r = sum(abs(x.raw_x) + abs(x.raw_y) for x in results)
    return "—" if r == 0 else f"{g / r:.6f}"


def verdict(c: Comparison) -> str:
    if c.ambiguous:
        return ("**无法判定**：有记录在 0.5 秒内出现多次右键，无法确定配对（见上文）。"
                "请避免连续快速按右键，并重测这些条件。")
    if c.godot_unpaired:
        return ("**无法判定**：有 Godot 记录在基准中找不到对应行（见上文）。"
                "请确认对照工具全程开着，然后重测。")
    if not c.compared:
        return "**无法判定**：没有有效且有移动的记录。"
    bad = [x for x in c.compared if not x.exact]
    if bad:
        diffs = [max(abs(x.diff_x), abs(x.diff_y)) for x in bad]
        if max(diffs) <= SMALL_DIFF_COUNTS:
            return (f"**待复核**：{len(bad)} 条记录有 ≤{SMALL_DIFF_COUNTS} counts 的偏差，可能是点击边界处的移动。"
                    "请对这些条件重测；如果偏差能稳定复现，则按不通过处理。")
        return (f"**不通过**：{len(bad)}/{len(c.compared)} 条记录不一致（偏差中位数 {statistics.median(diffs):g} counts）。"
                "请看「合计比例」列判断是固定比例丢失还是随机偏差，并评估改用 GDExtension 读取 Raw Input。")
    # 样本数按不同的（会话, 轮号）计算：同一轮重复按右键不增加样本
    thin = [note for note, rs in _groups(c).items() if len({x.key for x in rs}) < MIN_ROUNDS_PER_GROUP]
    if thin:
        return (f"**证据不足**：已有记录全部一致，但以下分组不足 {MIN_ROUNDS_PER_GROUP} 轮：{'、'.join(thin)}。"
                "补测后再判定。")
    rounds = len({x.key for x in c.compared})
    return (f"**数据层通过**：{rounds} 个有效轮次两轴计数全部与 Raw Input 完全一致，"
            f"每组至少 {MIN_ROUNDS_PER_GROUP} 轮。还需人工确认测试条件覆盖了 T1–T4，并完成 T5。")


def render(c: Comparison) -> str:
    lines = ["## 逐条比对结果（自动生成）", ""]
    if c.legacy:
        lines.append("- 注意：有记录是旧格式（没有毫秒时间戳），这部分按出现顺序逐条配对，并用秒级时间核对（每对相差 ≤2 秒）")
    lines.append(f"- 参与比较的记录：**{len(c.compared)}**，完全一致：**{sum(1 for x in c.compared if x.exact)}**")
    if c.invalid:
        lines.append(f"- 作废记录：{len(c.invalid)}（不参与比较）")
    if c.no_motion:
        lines.append(f"- 没有移动的记录：{len(c.no_motion)}（不参与比较）")
    if c.raw_extra:
        lines.append(f"- 基准多出的记录：{c.raw_extra}（在其他窗口里的点击等，正常）")
    if c.ambiguous:
        lines.append(f"- ⚠ 配对有歧义（0.5 秒内有多次右键）：{c.ambiguous}")
    if c.godot_unpaired:
        lines.append(f"- ⚠ Godot 有、基准找不到对应行：{c.godot_unpaired}")
    lines.append("")

    lines += ["### 按备注分组", "",
              "| 备注 | 轮数 | 完全一致的记录（条） | 最大偏差 X / Y（counts） | 合计比例 Godot/基准 | 含小数事件 | 两路不一致事件 |",
              "|---|---|---|---|---|---|---|"]
    for note, rs in _groups(c).items():
        mx = max(abs(x.diff_x) for x in rs)
        my = max(abs(x.diff_y) for x in rs)
        lines.append(f"| {note} | {len({x.key for x in rs})} | {sum(1 for x in rs if x.exact)} | {mx:g} / {my:g} | {_ratio(rs)} | "
                     f"{sum(x.fractional for x in rs)} | {sum(x.mismatch for x in rs)} |")
    lines.append("")

    bad = [x for x in c.compared if not x.exact]
    if bad:
        lines += ["### 不一致的记录", "", "| 轮 | 备注 | Godot X / Y | 基准 X / Y | 差 X / Y |", "|---|---|---|---|---|"]
        for x in bad:
            lines.append(f"| {x.label} | {x.note} | {x.godot_x:g} / {x.godot_y:g} | {x.raw_x} / {x.raw_y} | {x.diff_x:+g} / {x.diff_y:+g} |")
        lines.append("")

    if c.invalid:
        lines += ["### 作废记录", "", "| 记录 | 原因 |", "|---|---|"]
        lines += [f"| {n} | {why} |" for n, why in c.invalid]
        lines.append("")

    lines += ["### 初步判定", "", verdict(c), ""]
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description="P0-4 逐条比对")
    p.add_argument("csv", nargs="+", help="成对给出：Godot 的 CSV、基准的 CSV；多次测试可以给多对，合并成一份报告")
    p.add_argument("--out", help="把结果写入这个 Markdown 文件（默认打印）")
    a = p.parse_args()
    try:
        if len(a.csv) % 2:
            raise FormatError("CSV 必须成对给出：Godot 的、基准的")
        resolved = [os.path.normcase(os.path.realpath(x)) for x in a.csv]
        if len(set(resolved)) != len(resolved):
            raise FormatError("同一个 CSV 文件被给了不止一次，会重复计数")
        godot_runs = [read_csv(a.csv[i]) for i in range(0, len(a.csv), 2)]
        check_no_overlap(godot_runs)
        parts = [compare(godot_runs[i // 2], read_csv(a.csv[i + 1]), run=i // 2 + 1) for i in range(0, len(a.csv), 2)]
        text = render(merge(parts))
    except FormatError as e:
        sys.exit(str(e))
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"已写入 {a.out}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)


if __name__ == "__main__":
    main()
