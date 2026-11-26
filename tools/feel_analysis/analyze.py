"""切枪「按键 → 第一发」时长分析（P0-5，指引见 docs/measurement/p0-5-guide.md）。

两个数据源，分工明确：
- 按键记录 input_log.csv（输入显示层从 Raw Input 读到的每一次按下 / 松开，毫秒精度）是**输入时间线的权威**：
  手里是哪把武器、左键何时按下与松开、按了几次，都以它为准
- 录像里输入显示层的格子只用来**把按键对到录像的帧上**：格子每次至少亮 0.1 秒，两次快速连按会合成一次亮起，
  所以不能用它数按键或判断左键状态

步骤：
1. 对齐：OBS 日志里的开录时刻（毫秒）给出录像第 0 帧的大致 unix 时间；在 ±ALIGN_SEARCH_S 内用「记录时间 −
   格子亮起时间」的众数求出精确偏移。录像里**每一次**格子亮起都必须在记录里找到对应的按下，否则整段录像作废
2. 逐次切枪：遍历记录里的切枪键按下，从人工声明的初始武器（--initial）开始推算武器。触发键必须有**自己的**
   格子亮起（不是被合并进上一次亮起的），起点 s = 那一次亮起的帧
3. 终点 f：s 之后、下一次切枪按键之前的第一声枪响（音量从低于到不低于 AUDIO_SHOT_MIN），在它之前
   AV_MIN_LAG–AV_MAX_LAG 帧内开始的火光（火光指标 ≥ FLASH_MIN）。窗口内必须**恰好一段**火光开始，
   且连续至少 MIN_FLASH_FRAMES 帧；有两段（例如旁边的橙色特效）就无法确定是哪一段，作废
4. 时长 = (f − s) / fps × timescale

逐次检查（任何一条不满足就作废，并写明原因）：
- 切枪前后的武器与该项要求一致
- 切枪键按下时左键没有按着（按记录）
- 开火时左键按着，且这一次按住开始于切枪之后、比火光至少早 MIN_LEAD_S 秒（按记录）
- 从上一次切枪按键到火光之间，记录里的按下都在录像里显示出来了（被合并进同一键亮起期间的除外）

只处理有枪口火光的项目。挥刀（D）、检视（F、G）、拔刀（K1）需要另外的判据，不在这里。
"""

import argparse
import csv
import datetime
import math
import statistics
import sys
from dataclasses import dataclass, field

SELECT_KEYS = {"1": "ak", "2": "glock", "3": "knife"}
WEAPONS = set(SELECT_KEYS.values())
SWITCH_KEYS = ("1", "2", "3", "Q", "wheel")
OVERLAY_KEYS = ("1", "2", "3", "Q", "F", "wheel", "L", "R")
LOG_KEY_NAMES = {"1": "1", "2": "2", "3": "3", "Q": "Q", "F": "F", "滚轮": "wheel", "左键": "L", "右键": "R"}

# 每个测量项：触发键、切之前手里的武器、切之后的武器
ITEMS: dict[str, tuple[str, str, str]] = {
    "A": ("1", "knife", "ak"),
    "B": ("2", "ak", "glock"),
    "C": ("1", "glock", "ak"),
    "E1": ("Q", "glock", "ak"),
    "E2": ("Q", "ak", "glock"),
}

MIN_LEAD_S = 0.2            # 这次按住左键至少要比火光早这么多（录像时间，即真实时间）
FLASH_MIN = 100             # 火光帧的最低指标（实测开枪 650–2200，非开枪帧为 0 或个位数）
MIN_FLASH_FRAMES = 3        # 火光至少连续这么多帧（慢动作下真实火光持续多帧）
AUDIO_SHOT_MIN = 2500       # 枪声的音量下限（实测：枪声 3800–14500，拔枪等声音不超过约 1000）
AV_MIN_LAG, AV_MAX_LAG = 1, 8   # 枪声开始相对火光开始的延迟窗口（帧），实测 3–5
ALIGN_SEARCH_S = 0.15       # 对齐时，在 OBS 开录时刻附近搜索的范围
ALIGN_BIN_S = 0.01
MATCH_TOL_S = 0.05          # 对齐后，一次按下与一次格子亮起的对应容差
MIN_PAIRS = 3
MAX_FRAME_T_ERR_S = 0.0005  # 特征文件里第 i 帧的时间必须是 i / fps


@dataclass
class Frame:
    t: float
    lit: dict[str, bool]
    flash: int
    audio: float = 0.0


@dataclass
class Press:
    t: float            # 录像时间（秒）
    key: str
    event: str          # down / up / wheel
    onset: int | None = None   # 这次按下拥有的格子亮起帧
    status: str = ""    # shown / merged / missing


@dataclass
class Cycle:
    item: str
    start_frame: int | None
    press_t: float
    flash_frame: int | None = None
    duration_s: float | None = None
    valid: bool = False
    reason: str = ""


@dataclass
class Timeline:
    """一段录像对齐后的按键时间线。"""
    offset: float               # 录像第 0 帧 = OBS 开录时刻 + offset
    pairs: int
    presses: list[Press] = field(default_factory=list)   # 录像时间范围内、按时间排序
    problems: list[str] = field(default_factory=list)    # 非空 = 整段录像作废


def read_features(path: str) -> tuple[list[Frame], float]:
    frames, fps = [], 0.0
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            fps = float(r["fps"])
            lit = {k[4:]: r[k] == "1" for k in r if k.startswith("lit_")}
            frames.append(Frame(float(r["t"]), lit, int(r["flash"]), float(r.get("audio") or 0)))
    return frames, fps


def timeline_problems(frames: list[Frame], fps: float) -> list[str]:
    bad = [i for i, fr in enumerate(frames) if abs(fr.t - i / fps) > MAX_FRAME_T_ERR_S]
    return [f"第 {bad[0]} 帧的时间戳不是 帧号 / fps，时间线不连续"] if bad else []


def onsets(frames: list[Frame], key: str) -> list[int]:
    """格子从灭到亮的帧号（第 0 帧就亮着的不算，因为看不到它亮起的那一刻）。"""
    return [i for i in range(1, len(frames)) if frames[i].lit[key] and not frames[i - 1].lit[key]]


def lit_until(frames: list[Frame], key: str, start: int) -> int:
    """从 start 开始连续点亮到哪一帧为止（返回第一个熄灭的帧号）。"""
    e = start
    while e < len(frames) and frames[e].lit[key]:
        e += 1
    return e


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


def track_weapons(keys: list[str],
                  initial: tuple[str | None, str | None] = (None, None)) -> list[tuple[str | None, str | None]]:
    """对每个切枪按键，返回 (按之前手里的武器, 按之后手里的武器)。initial 为录像开始时的 (手里, 上一把)。"""
    current, previous = initial
    out = []
    for k in keys:
        before = current
        current, previous = step_weapon(current, previous, k)
        out.append((before, current))
    return out


# ---------- 按键记录 ----------

def read_key_log(path: str) -> list[tuple[float, str, str]]:
    """input_log.csv → [(unix 时间, 键, 事件)]，事件为 down / up / wheel。"""
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("key") in LOG_KEY_NAMES and r.get("event") in ("down", "up", "wheel"):
                out.append((float(r["t_unix"]), LOG_KEY_NAMES[r["key"]], r["event"]))
    return sorted(out)


def is_press(event: str) -> bool:
    return event in ("down", "wheel")


def align(frames: list[Frame], log: list[tuple[float, str, str]], obs_start: float) -> tuple[float | None, int]:
    """录像第 0 帧 = obs_start + offset。返回 (offset, 参与估计的配对数)；对不上时 offset 为 None。"""
    diffs = []
    for k in OVERLAY_KEYS:
        lt = [t - obs_start for t, kk, e in log if kk == k and is_press(e)]
        for i in onsets(frames, k):
            diffs += [d - frames[i].t for d in lt if abs(d - frames[i].t) <= ALIGN_SEARCH_S]
    if not diffs:
        return None, 0
    bins: dict[int, int] = {}
    for d in diffs:
        bins[round(d / ALIGN_BIN_S)] = bins.get(round(d / ALIGN_BIN_S), 0) + 1
    best = max(bins.values())
    modes = [b for b, n in bins.items() if n == best]
    if max(modes) - min(modes) > 1:
        return None, 0   # 两个相距较远的偏移一样可信：无法确定
    mode = statistics.mean(modes) * ALIGN_BIN_S
    near = [d for d in diffs if abs(d - mode) <= 2 * ALIGN_BIN_S]
    return statistics.median(near), len(near)


def build_timeline(frames: list[Frame], fps: float, log: list[tuple[float, str, str]], obs_start: float) -> Timeline:
    offset, pairs = align(frames, log, obs_start)
    if offset is None or pairs < MIN_PAIRS:
        return Timeline(0.0, pairs, problems=[f"按键记录与录像对不上（配对 {pairs} 个）"])
    tl = Timeline(offset, pairs)
    end_t = len(frames) / fps
    tl.presses = [Press(t - obs_start - offset, k, e) for t, k, e in log
                  if 0.0 <= t - obs_start - offset <= end_t]
    # 每一次格子亮起认领离它最近的一次同键按下
    for k in OVERLAY_KEYS:
        cand = [p for p in tl.presses if p.key == k and is_press(p.event)]
        for i in onsets(frames, k):
            near = [p for p in cand if p.onset is None and abs(p.t - frames[i].t) <= MATCH_TOL_S]
            if not near:
                tl.problems.append(f"{frames[i].t:.2f}s 的 {k} 亮起在按键记录里没有对应的按下")
                continue
            min(near, key=lambda p: abs(p.t - frames[i].t)).onset = i
    # 没认领到亮起的按下：落在同键亮起期间 = 被合并；否则 = 漏显示
    for p in tl.presses:
        if not is_press(p.event):
            continue
        if p.onset is not None:
            p.status = "shown"
            continue
        f = min(len(frames) - 1, max(0, int(math.floor(p.t * fps))))
        lo, hi = max(0, f - 1), min(len(frames), f + int(MATCH_TOL_S * fps) + 2)
        p.status = "merged" if any(frames[j].lit[p.key] for j in range(lo, hi)) else "missing"
    return tl


def left_held_since(presses: list[Press], t: float) -> float | None:
    """时刻 t 左键所在的那一次按住从何时开始（按记录）；没按着返回 None。"""
    since = None
    for p in presses:
        if p.t > t:
            break
        if p.key == "L":
            since = p.t if p.event == "down" else None
    return since


# ---------- 火光 ----------

def audio_onsets(frames: list[Frame], start: int, end: int) -> list[int]:
    """(start, end) 之间枪声开始的帧：音量从低于阈值变为不低于阈值。"""
    return [f for f in range(max(start + 1, 1), end)
            if frames[f].audio >= AUDIO_SHOT_MIN and frames[f - 1].audio < AUDIO_SHOT_MIN]


def flash_onsets(frames: list[Frame], start: int, end: int) -> list[int]:
    return [f for f in range(max(start + 1, 1), end)
            if frames[f].flash >= FLASH_MIN and frames[f - 1].flash < FLASH_MIN]


def find_flash(frames: list[Frame], start: int, end: int) -> tuple[int | None, str]:
    """(start, end) 之间第一声枪响对应的火光开始帧。返回 (帧, 失败原因)。"""
    shots = audio_onsets(frames, start, end)
    if not shots:
        return None, "下一次切枪之前没有开枪（可能左键松得太早）"
    a = shots[0]
    cand = [f for f in flash_onsets(frames, start, end) if a - AV_MAX_LAG <= f <= a - AV_MIN_LAG]
    if not cand:
        return None, "有枪声，但没有找到与之配对的火光"
    if len(cand) > 1:
        return None, f"第一声枪响前有 {len(cand)} 段火光开始，无法确定哪一段是开枪"
    f = cand[0]
    run = f
    while run < end and frames[run].flash >= FLASH_MIN:
        run += 1
    if run - f < MIN_FLASH_FRAMES:
        return None, f"与枪声配对的火光只持续 {run - f} 帧，可能不是枪口火光"
    return f, ""


# ---------- 分析 ----------

def analyze(frames: list[Frame], fps: float, item: str, timescale: float,
            initial: tuple[str | None, str | None], tl: Timeline) -> list[Cycle]:
    trigger, want_from, want_to = ITEMS[item]
    switches = [p for p in tl.presses if p.key in SWITCH_KEYS and is_press(p.event)]
    states = track_weapons([p.key for p in switches], initial)
    cycles = []
    for idx, (p, (before, after)) in enumerate(zip(switches, states)):
        if p.key != trigger:
            continue
        c = Cycle(item, p.onset, p.t)
        cycles.append(c)
        if tl.problems:
            c.reason = "整段录像作废：" + "；".join(tl.problems[:2])
            continue
        if p.onset is None:
            c.reason = f"这次按下没有自己的格子亮起（{'与上一次亮起合并' if p.status == 'merged' else '漏显示'}），起点不可靠"
            continue
        if before != want_from or after != want_to:
            c.reason = f"切枪方向不对或无法确定（{before} → {after}，应为 {want_from} → {want_to}）"
            continue
        if left_held_since(tl.presses, p.t) is not None:
            c.reason = "切枪时左键已经按着"
            continue
        next_t = switches[idx + 1].t if idx + 1 < len(switches) else len(frames) / fps
        end = min(len(frames), int(math.ceil(next_t * fps)))
        s = p.onset
        f, why = find_flash(frames, s, end)
        if f is None:
            c.reason = why
            continue
        c.flash_frame = f
        hold = left_held_since(tl.presses, frames[f].t)
        if hold is None:
            c.reason = "开火时左键没有按着"
            continue
        if hold <= p.t:
            c.reason = "开火时的这次按住在切枪之前就开始了"
            continue
        if frames[f].t - hold < MIN_LEAD_S:
            c.reason = f"这次按住左键只比火光早 {(frames[f].t - hold) * 1000:.0f} ms，可能按晚了"
            continue
        prev_t = switches[idx - 1].t if idx > 0 else 0.0
        lost = [q for q in tl.presses if q.status == "missing" and prev_t <= q.t <= frames[f].t]
        if lost:
            c.reason = f"按键记录里 {lost[0].t:.2f}s 的 {lost[0].key} 在录像里没有显示，输入显示层可能卡顿"
            continue
        c.duration_s = (f - s) / fps * timescale
        c.valid = True
    return cycles


def summarize(cycles: list[Cycle]) -> dict:
    """median_s：有效样本的中位数；max_dev_s：max(|样本 − 中位数|)，不是极差，也不是测量误差。"""
    vals = [c.duration_s for c in cycles if c.valid]
    if not vals:
        return {"samples": 0}
    med = statistics.median(vals)
    return {"samples": len(vals), "median_s": med, "max_dev_s": max(abs(v - med) for v in vals),
            "min_s": min(vals), "max_s": max(vals)}


def parse_initial(text: str) -> tuple[str | None, str | None]:
    """'ak,glock' → ('ak', 'glock')；'?' 表示不知道（'-' 也可以，但在命令行开头会被当成选项）。"""
    parts = [p.strip() or "-" for p in text.split(",")]
    if len(parts) != 2:
        raise ValueError(f"--initial 的格式应为「手里,上一把」，例如 ak,glock：{text}")
    out = []
    for p in parts:
        if p in ("-", "?"):
            out.append(None)
        elif p in WEAPONS:
            out.append(p)
        else:
            raise ValueError(f"未知武器 {p}（可用：{', '.join(sorted(WEAPONS))} 或 ?）")
    return out[0], out[1]


def parse_start(text: str) -> float:
    """OBS 日志里的开录时刻（本地时间，须精确到毫秒），例如 '2026-11-26 11:39:34.437'。"""
    dt = datetime.datetime.fromisoformat(text)
    if dt.microsecond == 0 and "." not in text:
        raise ValueError(f"开录时刻需要精确到毫秒（从 OBS 日志里取）：{text}")
    return dt.timestamp()


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="切枪按键 → 第一发 时长分析")
    ap.add_argument("item", choices=sorted(ITEMS))
    ap.add_argument("features_csv", nargs="+", help="同一项的一个或多个特征文件（例如 A 和 A2）")
    ap.add_argument("--key-log", required=True, help="输入显示层的 input_log.csv")
    ap.add_argument("--starts", nargs="+", required=True,
                    help="每段录像在 OBS 日志里的开录时刻，例如 '2026-11-26 11:39:34.437'，与特征文件一一对应")
    ap.add_argument("--timescale", type=float, default=0.1)
    ap.add_argument("--initial", nargs="+", required=True,
                    help="人工看过录像后，声明每段录像开始时的「手里,上一把」，例如 knife,ak；'?' 表示不知道")
    ap.add_argument("--samples-out", help="把逐样本结果（帧号、时长、作废原因）写入这个 CSV")
    a = ap.parse_args()
    if len(a.starts) != len(a.features_csv) or len(a.initial) != len(a.features_csv):
        sys.exit("--starts 与 --initial 的个数必须与特征文件个数相同")
    log = read_key_log(a.key_log)
    rows = []
    all_cycles = []
    for idx, path in enumerate(a.features_csv):
        frames, fps = read_features(path)
        name = path.replace("\\", "/").split("/")[-1]
        tl = build_timeline(frames, fps, log, parse_start(a.starts[idx]))
        tl.problems = timeline_problems(frames, fps) + tl.problems
        merged = sum(1 for p in tl.presses if p.status == "merged")
        missing = sum(1 for p in tl.presses if p.status == "missing")
        print(f"{name}：录像起点 = OBS 开录时刻 {tl.offset * 1000:+.0f} ms（{tl.pairs} 个配对）；"
              f"合并显示的按下 {merged} 次，漏显示 {missing} 次")
        for prob in tl.problems:
            print(f"  整段作废：{prob}")
        for c in analyze(frames, fps, a.item, a.timescale, parse_initial(a.initial[idx]), tl):
            tag = "有效" if c.valid else "作废"
            dur = f"{c.duration_s * 1000:7.1f} ms" if c.valid else " " * 10
            flash = f"{frames[c.flash_frame].t:8.3f}s" if c.flash_frame is not None else "       —"
            print(f"{name:10s} 按键 {c.press_t:8.3f}s  火光 {flash}  {dur}  {tag} {c.reason}")
            rows.append([a.item, name, c.start_frame if c.start_frame is not None else "",
                         c.flash_frame if c.flash_frame is not None else "",
                         f"{c.duration_s:.4f}" if c.valid else "", int(c.valid), c.reason])
            all_cycles.append(c)
    if a.samples_out:
        exists = False
        try:
            with open(a.samples_out, encoding="utf-8") as f:
                exists = bool(f.readline())
        except FileNotFoundError:
            pass
        with open(a.samples_out, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if not exists:
                w.writerow(["item", "video", "start_frame", "flash_frame", "duration_s", "valid", "reason"])
            w.writerows(rows)
    s = summarize(all_cycles)
    if s["samples"]:
        print(f"{a.item}：有效 {s['samples']} 次，中位数 {s['median_s'] * 1000:.1f} ms，"
              f"最大偏差 {s['max_dev_s'] * 1000:.1f} ms（范围 {s['min_s'] * 1000:.1f}–{s['max_s'] * 1000:.1f} ms）")
    else:
        print(f"{a.item}：没有有效样本")
        sys.exit(1)


if __name__ == "__main__":
    main()
