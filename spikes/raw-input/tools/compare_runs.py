"""按轮号对齐 Godot spike 与 Raw Input 基准的两个 CSV，生成 P0-4 报告的数据部分（Markdown）。

用法：
    python -I compare_runs.py <godot 的 spike_runs.csv> <基准的 rawinput_runs.csv> [--out 报告.md]

配对方式：两边在同一次鼠标右键时各写一行，所以按「会话 → 轮号 → 该轮第几次记录」逐条配对。
- 会话：程序重启后轮号会重新开始，轮号变小处视为新会话
- 同一轮多次记录（重复按右键）：按出现顺序一一配对
- 安全检查：配对的两行记录时间相差超过 MAX_TIME_SKEW_S，说明配错了，整体判为无法判定

判据（见 spikes/raw-input/README.md）：
- 只比较两边都有效（valid=1）且有移动的轮次
- 每轮 X、Y 两轴：Godot screen_relative 计数 == 基准原始计数
- 每个备注分组至少 MIN_ROUNDS_PER_GROUP 个有效轮次才算证据充分
"""

import argparse
import csv
import datetime
import statistics
import sys
from dataclasses import dataclass, field

EXACT_TOL = 1e-9  # Godot 记录为 6 位小数的浮点数，基准为整数
MIN_ROUNDS_PER_GROUP = 5
MAX_TIME_SKEW_S = 3.0
SMALL_DIFF_COUNTS = 2


@dataclass
class RoundResult:
    key: tuple[int, int, int]  # (会话, 轮号, 第几次记录)
    note: str
    godot_x: float
    godot_y: float
    raw_x: int
    raw_y: int
    fractional: int
    mismatch: int

    @property
    def label(self) -> str:
        s, n, k = self.key
        return f"会话{s}·第{n}轮" + (f"（第{k + 1}次记录）" if k else "")

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
    unpaired_godot: list[str] = field(default_factory=list)
    unpaired_raw: list[str] = field(default_factory=list)
    invalid: list[tuple[str, str]] = field(default_factory=list)
    no_motion: list[str] = field(default_factory=list)
    time_skew: list[str] = field(default_factory=list)
    sessions: tuple[int, int] = (0, 0)


def read_csv(path: str) -> list[dict]:
    # 两个程序写出的 CSV 都不使用引号（备注中的逗号、引号已在写入时替换），按无引号解析
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, quoting=csv.QUOTE_NONE))


def _keyed(rows: list[dict]) -> tuple[dict[tuple[int, int, int], dict], int]:
    out: dict[tuple[int, int, int], dict] = {}
    session = 1
    prev_round = None
    seen: dict[tuple[int, int], int] = {}
    for r in rows:
        n = int(r["round"])
        if prev_round is not None and n < prev_round:
            session += 1
        prev_round = n
        k = seen.get((session, n), 0)
        seen[(session, n)] = k + 1
        out[(session, n, k)] = r
    return out, (session if rows else 0)


def _label(key: tuple[int, int, int]) -> str:
    s, n, k = key
    return f"会话{s}·第{n}轮" + (f"（第{k + 1}次记录）" if k else "")


def _parse_time(text: str) -> datetime.datetime | None:
    try:
        return datetime.datetime.fromisoformat(text.strip())
    except (ValueError, AttributeError):
        return None


def compare(godot_rows: list[dict], raw_rows: list[dict]) -> Comparison:
    c = Comparison()
    g, gs = _keyed(godot_rows)
    r, rs = _keyed(raw_rows)
    c.sessions = (gs, rs)
    for key in sorted(set(g) | set(r)):
        if key[1] == 0:
            continue  # 第 0 轮是按中键之前，不是测量轮
        if key not in r:
            c.unpaired_godot.append(_label(key))
            continue
        if key not in g:
            c.unpaired_raw.append(_label(key))
            continue
        gr, rr = g[key], r[key]
        tg, tr = _parse_time(gr.get("time", "")), _parse_time(rr.get("time", ""))
        if tg and tr and abs((tg - tr).total_seconds()) > MAX_TIME_SKEW_S:
            c.time_skew.append(f"{_label(key)}（Godot {gr['time']} / 基准 {rr['time']}）")
        reasons = []
        if gr["valid"] != "1":
            reasons.append(f"Godot：{gr.get('invalid_reason') or '无效'}")
        if rr["valid"] != "1":
            flags = [k for k in ("absolute_events", "read_errors", "boundary_motion", "sync_lost") if rr.get(k, "0") not in ("0", "")]
            reasons.append("基准：" + ("、".join(flags) or "无效"))
        if reasons:
            c.invalid.append((_label(key), "；".join(reasons)))
            continue
        res = RoundResult(
            key=key, note=gr.get("note", ""),
            godot_x=float(gr["counts_x"]), godot_y=float(gr["counts_y"]),
            raw_x=int(rr["raw_x"]), raw_y=int(rr["raw_y"]),
            fractional=int(gr["fractional"]), mismatch=int(gr["mismatch"]),
        )
        if not res.moved:
            c.no_motion.append(res.label)
            continue
        c.compared.append(res)
    return c


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
    if c.unpaired_godot or c.unpaired_raw or c.time_skew or c.sessions[0] != c.sessions[1]:
        return "**无法判定**：两边的记录没有一一对齐（见上文的配对问题）。请按 README 重启两个程序、换新的 CSV 文件后重测。"
    if not c.compared:
        return "**无法判定**：没有有效且有移动的轮次。"
    bad = [x for x in c.compared if not x.exact]
    if bad:
        diffs = [max(abs(x.diff_x), abs(x.diff_y)) for x in bad]
        if max(diffs) <= SMALL_DIFF_COUNTS:
            return (f"**待复核**：{len(bad)} 个轮次有 ≤{SMALL_DIFF_COUNTS} counts 的偏差，可能是点击边界处的移动。"
                    "请对这些条件重测；如果偏差能稳定复现，则按不通过处理。")
        return (f"**不通过**：{len(bad)}/{len(c.compared)} 个轮次不一致（偏差中位数 {statistics.median(diffs):g} counts）。"
                "请看「合计比例」列判断是固定比例丢失还是随机偏差，并评估改用 GDExtension 读取 Raw Input。")
    thin = [note for note, rs in _groups(c).items() if len(rs) < MIN_ROUNDS_PER_GROUP]
    if thin:
        return (f"**证据不足**：已有 {len(c.compared)} 轮全部一致，但以下分组不足 {MIN_ROUNDS_PER_GROUP} 轮：{'、'.join(thin)}。"
                "补测后再判定。")
    return (f"**数据层通过**：{len(c.compared)} 个有效轮次两轴计数全部与 Raw Input 完全一致，"
            f"每组至少 {MIN_ROUNDS_PER_GROUP} 轮。还需人工确认测试条件覆盖了 T1–T4，并完成 T5。")


def render(c: Comparison) -> str:
    lines = ["## 逐轮比对结果（自动生成）", ""]
    total = len(c.compared)
    exact = sum(1 for x in c.compared if x.exact)
    lines.append(f"- 会话数：Godot {c.sessions[0]}，基准 {c.sessions[1]}")
    lines.append(f"- 参与比较的轮次：**{total}**，完全一致：**{exact}**")
    if c.invalid:
        lines.append(f"- 作废轮次：{len(c.invalid)}（不参与比较）")
    if c.no_motion:
        lines.append(f"- 没有移动的轮次：{len(c.no_motion)}（不参与比较）")
    if c.unpaired_godot or c.unpaired_raw:
        lines.append(f"- ⚠ 无法配对：只有 Godot 有 {c.unpaired_godot or '无'}；只有基准有 {c.unpaired_raw or '无'}")
    if c.time_skew:
        lines.append(f"- ⚠ 配对的两行记录时间相差超过 {MAX_TIME_SKEW_S:g} 秒，可能配错：{c.time_skew}")
    lines.append("")

    lines += ["### 按备注分组", "",
              "| 备注 | 轮数 | 完全一致 | 最大偏差 X / Y（counts） | 合计比例 Godot/基准 | 含小数事件 | 两路不一致事件 |",
              "|---|---|---|---|---|---|---|"]
    for note, rs in _groups(c).items():
        mx = max(abs(x.diff_x) for x in rs)
        my = max(abs(x.diff_y) for x in rs)
        lines.append(f"| {note} | {len(rs)} | {sum(1 for x in rs if x.exact)} | {mx:g} / {my:g} | {_ratio(rs)} | "
                     f"{sum(x.fractional for x in rs)} | {sum(x.mismatch for x in rs)} |")
    lines.append("")

    bad = [x for x in c.compared if not x.exact]
    if bad:
        lines += ["### 不一致的轮次", "", "| 轮 | 备注 | Godot X / Y | 基准 X / Y | 差 X / Y |", "|---|---|---|---|---|"]
        for x in bad:
            lines.append(f"| {x.label} | {x.note} | {x.godot_x:g} / {x.godot_y:g} | {x.raw_x} / {x.raw_y} | {x.diff_x:+g} / {x.diff_y:+g} |")
        lines.append("")

    if c.invalid:
        lines += ["### 作废轮次", "", "| 轮 | 原因 |", "|---|---|"]
        lines += [f"| {n} | {why} |" for n, why in c.invalid]
        lines.append("")

    lines += ["### 初步判定", "", verdict(c), ""]
    return "\n".join(lines)


def main() -> None:
    p = argparse.ArgumentParser(description="P0-4 逐轮比对")
    p.add_argument("godot_csv")
    p.add_argument("raw_csv")
    p.add_argument("--out", help="把结果写入这个 Markdown 文件（默认打印）")
    a = p.parse_args()
    text = render(compare(read_csv(a.godot_csv), read_csv(a.raw_csv)))
    if a.out:
        with open(a.out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        print(f"已写入 {a.out}")
    else:
        sys.stdout.reconfigure(encoding="utf-8")
        print(text)


if __name__ == "__main__":
    main()
