"""切枪「按键 → 第一发」时长分析（P0-5，指引见 docs/measurement/p0-5-guide.md）。

输入是 features.py 产出的逐帧特征 CSV。对每一次「切枪键」按下：
- 起点 s：输入显示层对应格子从灭变亮的第一帧
- 终点 f：之后第一帧枪口火光：火光指标 flash 不低于 FLASH_MIN，且之后 AV_WINDOW_FRAMES 帧内有枪声
  （音量不低于 AUDIO_SHOT_MIN）。只看音频不准（实测 OBS 录像里声音比画面晚 3–5 帧），
  所以音频只用来确认，时刻取画面
- 时长 = (f - s) / fps × timescale

逐次检查是否有效（任何一条不满足就作废，并写明原因）：
1. 切枪前手里的武器与该项要求一致；切过去的武器也一致（按录像里的按键顺序推算）
2. 切枪键按下时左键没有按着（否则拿刀时会先挥刀，或者测的不是切枪）
3. 在下一次切枪之前找到了经枪声确认的火光
4. 火光之前左键已经亮起，且左键亮起到火光至少相隔 MIN_LEAD_FRAMES 帧
   （否则可能是左键按晚了：测到的是人的反应，而不是游戏允许开火的时刻）

录像开始时手里拿什么，录像本身看不出来，所以每段录像里的第一次切枪默认作废；
人工看过录像确认后，可以用 --initial 声明录像开始时的武器。不用输入显示层的完整按键记录推断：
它记录的是全系统按键（在控制台敲 host_timescale 0.1 也会按到 1），不可靠。

只处理有枪口火光的项目。挥刀（D）、检视（F、G）、拔刀（K1）需要另外的判据，不在这里。
"""

import argparse
import csv
import statistics
import sys
from dataclasses import dataclass

SELECT_KEYS = {"1": "ak", "2": "glock", "3": "knife"}
WEAPONS = set(SELECT_KEYS.values())

# 每个测量项：触发键、切之前手里的武器、切之后的武器
ITEMS: dict[str, tuple[str, str, str]] = {
    "A": ("1", "knife", "ak"),
    "B": ("2", "ak", "glock"),
    "C": ("1", "glock", "ak"),
    "E1": ("Q", "glock", "ak"),
    "E2": ("Q", "ak", "glock"),
}

MIN_LEAD_FRAMES = 12        # 左键至少要比火光早这么多帧（60 fps 下 0.2 s 真实时间）
FLASH_MIN = 100             # 火光帧的最低指标（实测开枪 650–2200，非开枪帧为 0 或个位数）
AUDIO_SHOT_MIN = 2500       # 枪声的音量下限（实测：枪声 3800–14500，拔枪等声音不超过约 1000）
AV_WINDOW_FRAMES = 15       # 火光之后多少帧内必须出现枪声


@dataclass
class Frame:
    t: float
    lit: dict[str, bool]
    flash: int
    audio: float = 0.0


@dataclass
class Cycle:
    item: str
    start_frame: int
    flash_frame: int | None = None
    duration_s: float | None = None
    valid: bool = False
    reason: str = ""


def read_features(path: str) -> tuple[list[Frame], float]:
    frames, fps = [], 0.0
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            fps = float(r["fps"])
            lit = {k[4:]: r[k] == "1" for k in r if k.startswith("lit_")}
            frames.append(Frame(float(r["t"]), lit, int(r["flash"]), float(r.get("audio") or 0)))
    return frames, fps


def onsets(frames: list[Frame], key: str) -> list[int]:
    """格子从灭到亮的帧号（第 0 帧就亮着的不算，因为看不到它亮起的那一刻）。"""
    return [i for i in range(1, len(frames)) if frames[i].lit[key] and not frames[i - 1].lit[key]]


def key_events(frames: list[Frame]) -> list[tuple[int, str]]:
    """按时间排序的所有切枪相关按键：1、2、3、Q、wheel。"""
    return sorted((i, k) for k in ("1", "2", "3", "Q", "wheel") for i in onsets(frames, k))


def step_weapon(current: str | None, previous: str | None, key: str) -> tuple[str | None, str | None]:
    """按下一个切枪相关的键之后，返回新的 (手里的武器, 上一把武器)。不知道时为 None。"""
    if key in SELECT_KEYS:
        new = SELECT_KEYS[key]
        if new != current:
            return new, current
        return current, previous
    if key == "Q":
        if current is not None and previous is not None:
            return previous, current
        return None, current
    # 滚轮：切到哪把取决于游戏内顺序，这里不推断
    return None, current


def track_weapons(events: list[tuple[int, str]],
                  initial: tuple[str | None, str | None] = (None, None)) -> list[tuple[str | None, str | None]]:
    """对每个按键事件，返回 (按之前手里的武器, 按之后手里的武器)。initial 为录像开始时的 (手里, 上一把)。"""
    current, previous = initial
    out = []
    for _, k in events:
        before = current
        current, previous = step_weapon(current, previous, k)
        out.append((before, current))
    return out


def find_flash(frames: list[Frame], start: int, end: int) -> int | None:
    """(start, end) 之间第一帧经枪声确认的火光。"""
    for f in range(start + 1, end):
        if frames[f].flash < FLASH_MIN:
            continue
        if any(fr.audio >= AUDIO_SHOT_MIN for fr in frames[f:min(len(frames), f + AV_WINDOW_FRAMES + 1)]):
            return f
    return None


def has_gunshot(frames: list[Frame], start: int, end: int) -> bool:
    return any(fr.audio >= AUDIO_SHOT_MIN for fr in frames[start + 1:end])


def analyze(frames: list[Frame], fps: float, item: str, timescale: float,
            initial: tuple[str | None, str | None] = (None, None)) -> list[Cycle]:
    trigger, want_from, want_to = ITEMS[item]
    events = key_events(frames)
    states = track_weapons(events, initial)
    left_on = onsets(frames, "L")
    cycles = []
    for idx, ((s, k), (before, after)) in enumerate(zip(events, states)):
        if k != trigger:
            continue
        c = Cycle(item, s)
        cycles.append(c)
        end = events[idx + 1][0] if idx + 1 < len(events) else len(frames)
        if before != want_from or after != want_to:
            c.reason = f"切枪方向不对或无法确定（{before} → {after}，应为 {want_from} → {want_to}）"
            continue
        if frames[s].lit["L"] or frames[s - 1].lit["L"]:
            c.reason = "切枪时左键已经按着"
            continue
        f = find_flash(frames, s, end)
        if f is None:
            c.reason = ("有枪声，但没有找到对应的火光帧" if has_gunshot(frames, s, end)
                        else "下一次切枪之前没有开枪（可能左键松得太早）")
            continue
        c.flash_frame = f
        lefts = [l for l in left_on if s < l < f]
        if not lefts:
            c.reason = "火光之前没有看到左键亮起"
            continue
        if f - lefts[0] < MIN_LEAD_FRAMES:
            c.reason = f"左键只比火光早 {f - lefts[0]} 帧，可能按晚了"
            continue
        c.duration_s = (f - s) / fps * timescale
        c.valid = True
    return cycles


def summarize(cycles: list[Cycle]) -> dict:
    vals = [c.duration_s for c in cycles if c.valid]
    if not vals:
        return {"samples": 0}
    med = statistics.median(vals)
    return {"samples": len(vals), "median_s": med, "max_dev_s": max(abs(v - med) for v in vals),
            "min_s": min(vals), "max_s": max(vals)}


def parse_initial(text: str) -> tuple[str | None, str | None]:
    """'ak,glock' → ('ak', 'glock')；'-' 表示不知道。"""
    parts = [p.strip() or "-" for p in text.split(",")]
    if len(parts) != 2:
        raise ValueError(f"--initial 的格式应为「手里,上一把」，例如 ak,glock：{text}")
    out = []
    for p in parts:
        if p == "-":
            out.append(None)
        elif p in WEAPONS:
            out.append(p)
        else:
            raise ValueError(f"未知武器 {p}（可用：{', '.join(sorted(WEAPONS))} 或 -）")
    return out[0], out[1]


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="切枪按键 → 第一发 时长分析")
    ap.add_argument("item", choices=sorted(ITEMS))
    ap.add_argument("features_csv", nargs="+", help="同一项的一个或多个特征文件（例如 A 和 A2）")
    ap.add_argument("--timescale", type=float, default=0.1)
    ap.add_argument("--initial", nargs="*", default=[],
                    help="人工看过录像后，声明每段录像开始时的「手里,上一把」，例如 knife,ak；'-' 表示不知道。"
                         "个数须与特征文件相同")
    a = ap.parse_args()
    if a.initial and len(a.initial) != len(a.features_csv):
        sys.exit("--initial 的个数必须与特征文件个数相同")
    all_cycles = []
    for idx, path in enumerate(a.features_csv):
        frames, fps = read_features(path)
        initial = parse_initial(a.initial[idx]) if a.initial else (None, None)
        name = path.replace("\\", "/").split("/")[-1]
        for c in analyze(frames, fps, a.item, a.timescale, initial):
            tag = "有效" if c.valid else "作废"
            dur = f"{c.duration_s * 1000:7.1f} ms" if c.valid else " " * 10
            flash = f"{frames[c.flash_frame].t:8.3f}s" if c.flash_frame is not None else "       —"
            print(f"{name:10s} 按键 {frames[c.start_frame].t:8.3f}s  火光 {flash}  {dur}  {tag} {c.reason}")
            all_cycles.append(c)
    s = summarize(all_cycles)
    if s["samples"]:
        print(f"{a.item}：有效 {s['samples']} 次，中位数 {s['median_s'] * 1000:.1f} ms，"
              f"最大偏差 {s['max_dev_s'] * 1000:.1f} ms（范围 {s['min_s'] * 1000:.1f}–{s['max_s'] * 1000:.1f} ms）")
    else:
        print(f"{a.item}：没有有效样本")
        sys.exit(1)


if __name__ == "__main__":
    main()
