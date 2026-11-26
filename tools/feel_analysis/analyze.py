"""切枪「按键 → 第一发」时长分析（P0-5，指引见 docs/measurement/p0-5-guide.md）。

输入是 features.py 产出的逐帧特征 CSV。对每一次「切枪键」按下：
- 起点 s：输入显示层对应格子从灭变亮的第一帧
- 终点 f：第一发的枪口火光帧。先用音频找到第一声枪响（音量超过 AUDIO_SHOT_MIN），
  再在枪响之前 AV_WINDOW_FRAMES 帧内找画面火光指标 hot 的跳升。只看画面会被拔枪时手套、枪身的高光误触发；
  只看音频则不准（实测 OBS 录像里声音比画面晚约 5 帧）
- 时长 = (f - s) / fps × timescale

逐次检查是否有效（任何一条不满足就作废，并写明原因）：
1. 切枪前手里的武器与该项要求一致；切过去的武器也一致（按按键顺序推算手里的武器）
2. 切枪键按下时左键没有按着（否则拿刀时会先挥刀，或者测的不是切枪）
3. 在下一次切枪之前找到了火光
4. 火光之前左键已经亮起，且左键亮起到火光至少相隔 MIN_LEAD_FRAMES 帧
   （否则可能是左键按晚了：测到的是人的反应，而不是游戏允许开火的时刻）

只处理有枪口火光的项目。挥刀（D）、检视（F、G）、拔刀（K1）需要另外的判据，不在这里。
"""

import argparse
import csv
import statistics
import sys
from dataclasses import dataclass, field

SELECT_KEYS = {"1": "ak", "2": "glock", "3": "knife"}

# 每个测量项：触发键、切之前手里的武器、切之后的武器
ITEMS: dict[str, tuple[str, str, str]] = {
    "A": ("1", "knife", "ak"),
    "B": ("2", "ak", "glock"),
    "C": ("1", "glock", "ak"),
    "E1": ("Q", "glock", "ak"),
    "E2": ("Q", "ak", "glock"),
}

MIN_LEAD_FRAMES = 12        # 左键至少要比火光早这么多帧（60 fps 下 0.2 s 真实时间）
AUDIO_SHOT_MIN = 2500       # 枪声的音量下限（实测：枪声 3800–14500，拔枪等声音不超过约 1000）
AV_WINDOW_FRAMES = 15       # 在枪声之前多少帧内找画面火光
FLASH_ABS_MIN = 150         # 火光帧 hot 的最低值
FLASH_RATIO = 2.0           # 火光帧 hot 至少是此前基线（中位数）的这么多倍
BASELINE_FRAMES = 30        # 基线：火光搜索窗口之前这么多帧的中位数


@dataclass
class Frame:
    t: float
    lit: dict[str, bool]
    hot: int
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
            frames.append(Frame(float(r["t"]), lit, int(r["hot"]), float(r.get("audio") or 0)))
    return frames, fps


def onsets(frames: list[Frame], key: str) -> list[int]:
    """格子从灭到亮的帧号（第 0 帧就亮着的不算，因为看不到它亮起的那一刻）。"""
    return [i for i in range(1, len(frames)) if frames[i].lit[key] and not frames[i - 1].lit[key]]


def key_events(frames: list[Frame]) -> list[tuple[int, str]]:
    """按时间排序的所有切枪相关按键：1、2、3、Q、wheel。"""
    ev = [(i, k) for k in ("1", "2", "3", "Q", "wheel") for i in onsets(frames, k)]
    return sorted(ev)


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
    """对每个按键事件，返回 (按之前手里的武器, 按之后手里的武器)；不知道时为 None。

    initial：录像开始时的 (手里的武器, 上一把武器)，可由 state_from_key_log() 从完整按键记录推出。
    """
    current, previous = initial
    out = []
    for _, k in events:
        before = current
        current, previous = step_weapon(current, previous, k)
        out.append((before, current))
    return out


LOG_KEYS = {"1": "1", "2": "2", "3": "3", "Q": "Q", "滚轮": "wheel"}


def state_from_key_log(rows: list[dict], before_unix: float) -> tuple[str | None, str | None]:
    """用输入显示层的完整按键记录（input_log.csv），推出某一时刻之前手里的武器和上一把武器。"""
    events = [(float(r["t_unix"]), LOG_KEYS[r["key"]]) for r in rows
              if r.get("event") in ("down", "wheel") and r.get("key") in LOG_KEYS and float(r["t_unix"]) < before_unix]
    events.sort()
    current, previous = None, None
    for _, k in events:
        current, previous = step_weapon(current, previous, k)
    return current, previous


def audio_shot(frames: list[Frame], start: int, end: int) -> int | None:
    """(start, end) 之间第一帧枪声（音量超过 AUDIO_SHOT_MIN）。"""
    for f in range(start + 1, end):
        if frames[f].audio >= AUDIO_SHOT_MIN:
            return f
    return None


def find_flash(frames: list[Frame], start: int, end: int) -> int | None:
    """第一发的火光帧：先找第一声枪响，再在它之前 AV_WINDOW_FRAMES 帧内找 hot 的跳升。

    基线取搜索窗口之前、切枪之后的 BASELINE_FRAMES 帧的中位数。找不到枪声或找不到画面跳升都返回 None。
    """
    a = audio_shot(frames, start, end)
    if a is None:
        return None
    lo = max(start + 1, a - AV_WINDOW_FRAMES)
    base_frames = frames[max(start + 1, lo - BASELINE_FRAMES):lo]
    if len(base_frames) < 5:
        return None
    base = statistics.median(fr.hot for fr in base_frames)
    for f in range(lo, a + 1):
        if frames[f].hot >= max(FLASH_ABS_MIN, FLASH_RATIO * base):
            return f
    return None


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
        if audio_shot(frames, s, end) is None:
            c.reason = "下一次切枪之前没有枪声（可能左键松得太早，枪没有打出去）"
            continue
        f = find_flash(frames, s, end)
        if f is None:
            c.reason = "有枪声，但枪声之前的画面里没找到火光跳升"
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


def main() -> None:
    ap = argparse.ArgumentParser(description="切枪按键 → 第一发 时长分析")
    ap.add_argument("item", choices=sorted(ITEMS))
    ap.add_argument("features_csv", nargs="+", help="同一项的一个或多个特征文件（例如 A 和 A2）")
    ap.add_argument("--timescale", type=float, default=0.1)
    ap.add_argument("--key-log", help="输入显示层的 input_log.csv，用来推出每段录像开始时手里的武器")
    ap.add_argument("--starts", nargs="*", default=[],
                    help="每段录像的开始时间（与 features_csv 一一对应），格式 'YYYY-MM-DD HH-MM-SS'，即 OBS 文件名")
    a = ap.parse_args()
    log_rows = []
    if a.key_log:
        with open(a.key_log, newline="", encoding="utf-8") as f:
            log_rows = list(csv.DictReader(f))
    if a.starts and len(a.starts) != len(a.features_csv):
        sys.exit("--starts 的个数必须与特征文件个数相同")
    all_cycles = []
    for idx, path in enumerate(a.features_csv):
        frames, fps = read_features(path)
        initial: tuple[str | None, str | None] = (None, None)
        if log_rows and a.starts:
            import datetime
            t0 = datetime.datetime.strptime(a.starts[idx], "%Y-%m-%d %H-%M-%S").timestamp()
            initial = state_from_key_log(log_rows, t0)
            print(f"{path.split(chr(92))[-1]}：录像开始时手里 {initial[0]}，上一把 {initial[1]}")
        for c in analyze(frames, fps, a.item, a.timescale, initial):
            tag = "有效" if c.valid else "作废"
            dur = f"{c.duration_s * 1000:7.1f} ms" if c.valid else "          "
            flash = f"{frames[c.flash_frame].t:8.3f}" if c.flash_frame is not None else "       —"
            print(f"{path.split(chr(92))[-1]:10s} 按键 {frames[c.start_frame].t:8.3f}s  火光 {flash}s  {dur}  {tag} {c.reason}")
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
