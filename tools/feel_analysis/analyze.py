"""切枪「按键 → 第一发」时长分析（P0-5，指引见 docs/measurement/p0-5-guide.md）。

两个数据源，分工明确：
- 按键记录 input_log.csv（输入显示层从 Raw Input 读到的每一次按下 / 松开，毫秒精度）是**输入时间线的权威**：
  手里是哪把武器、左键何时按下与松开、按了几次，都以它为准
- 录像里输入显示层的格子只用来**把按键对到录像的帧上**：格子每次至少亮 0.1 秒，两次快速连按会合成一次亮起，
  所以不能用它数按键或判断左键状态

步骤：
1. 对齐：OBS 日志里的开录时刻（毫秒）给出录像第 0 帧的大致 unix 时间；在 ±ALIGN_SEARCH_S 内逐个试偏移，
   取「物理模型」矛盾最少的那个（见 _classify）。最优偏移必须唯一（连成一段）；录像里**每一次**格子亮起都必须
   在记录里找到开启它的按下，down / up 必须交替，否则整段录像作废
2. 逐次切枪：遍历记录里的切枪键按下，从人工声明的初始武器（--initial）开始推算武器。触发键必须有**自己的**
   格子亮起（不是被合并进上一次亮起的），起点 s = 那一次亮起的帧
3. 终点 f：s 之后、下一次切枪按键之前的第一声枪响（音量从低于到不低于 AUDIO_SHOT_MIN），在它之前
   AV_MIN_LAG–AV_MAX_LAG 帧内开始的火光（火光指标 ≥ FLASH_MIN）。窗口内必须**恰好一段**火光开始，
   且连续至少 MIN_FLASH_FRAMES 帧；有两段（例如旁边的橙色特效）就无法确定是哪一段，作废。
   已知局限：橙色特效与真实火光无缝重叠时没有第二个上升沿，工具分不出来，靠人工逐帧抽查兜底
4. 时长 = (f − s) / fps × timescale

逐次检查（任何一条不满足就作废，并写明原因）：
- 切枪前后的武器与该项要求一致
- 切枪键按下时左键没有按着（按记录）
- 开火时左键按着，且这一次按住开始于切枪之后、比火光至少早 MIN_LEAD_S 秒（按记录）；
  录像里左键格子在这段时间也一直亮着（与记录一致）
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
AV_MIN_LAG, AV_MAX_LAG = 2, 7   # 枪声开始相对火光开始的延迟窗口（帧）；第一批 33 次实测 3–6（另有 1 次 2）
ALIGN_SEARCH_S = 0.15       # 对齐时，在 OBS 开录时刻附近搜索的范围
ALIGN_STEP_S = 0.002
MATCH_EARLY_S = 0.03        # 对齐后，格子亮起最多比按下早这么多（第一批实测最早 −19 ms）
MATCH_LATE_S = 0.07         # 对齐后，格子亮起最多比按下晚这么多（第一批实测最晚 +47 ms）
INSIDE_MARGIN_S = 0.03      # 按下前这么久格子已经亮着，才算「并进已有的亮起」
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
    if not (math.isfinite(fps) and fps > 0):
        return [f"帧率 {fps} 不合法"]
    bad = [i for i, fr in enumerate(frames) if not abs(fr.t - i / fps) <= MAX_FRAME_T_ERR_S]
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


def _classify(frames: list[Frame], fps: float, presses: list[Press]) -> tuple[int, int, list[str]]:
    """按「物理模型」给已换算到录像时间的按下分类，返回 (认领了亮起的按下数, 矛盾数, 矛盾说明)。

    一次按下发生时，如果同一格**之前**就亮着（按下前 INSIDE_MARGIN_S 那一帧已亮），它被并进这次亮起（merged）；
    否则它必须开启一次新的亮起：认领 [按下 − MATCH_EARLY_S, 按下 + MATCH_LATE_S] 内同键的一次亮起（shown），
    找不到就是漏显示（missing）。录像里没有被任何按下认领的亮起 = 记录里缺了这次按下。
    """
    n = len(frames)
    owned, bad, notes = 0, 0, []
    for k in OVERLAY_KEYS:
        ons = onsets(frames, k)
        taken: set[int] = set()
        for p in (q for q in presses if q.key == k and is_press(q.event)):
            p.onset, p.status = None, ""
            before = int(math.floor((p.t - INSIDE_MARGIN_S) * fps))
            if 0 <= before < n and frames[before].lit[k]:
                p.status = "merged"
                continue
            cand = [i for i in ons if i not in taken and -MATCH_EARLY_S <= frames[i].t - p.t <= MATCH_LATE_S]
            if cand:
                p.onset = min(cand, key=lambda i: abs(frames[i].t - p.t))
                taken.add(p.onset)
                p.status = "shown"
                owned += 1
            else:
                p.status = "missing"
                bad += 1
        for i in ons:
            if i not in taken:
                bad += 1
                notes.append(f"{frames[i].t:.2f}s 的 {k} 亮起在按键记录里没有对应的按下")
    return owned, bad, notes


def _event_problems(log: list[tuple[float, str, str]], obs_start: float, offset: float, end_t: float) -> list[str]:
    """每个键的 down / up 必须交替出现；录像时间范围内出现重复按下或无主松开，说明记录不完整。"""
    out = []
    state: dict[str, str] = {}
    for t, k, e in log:
        if e not in ("down", "up"):
            continue
        v = t - obs_start - offset
        if state.get(k) == e and 0.0 <= v <= end_t:
            out.append(f"按键记录里 {v:.2f}s 的 {k} 连续两次 {e}，记录不完整")
        state[k] = e
    return out


def build_timeline(frames: list[Frame], fps: float, log: list[tuple[float, str, str]], obs_start: float) -> Timeline:
    """录像第 0 帧 = obs_start + offset。在 ±ALIGN_SEARCH_S 内逐个试 offset，取物理模型矛盾最少的；
    矛盾最少的 offset 必须连成一段（否则有两种对齐同样可信，拒绝），最后在这一段的中点上分类。"""
    end_t = len(frames) / fps
    steps = int(round(ALIGN_SEARCH_S / ALIGN_STEP_S))
    scored = []
    for j in range(-steps, steps + 1):
        off = j * ALIGN_STEP_S
        ps = [Press(t - obs_start - off, k, e) for t, k, e in log if 0.0 <= t - obs_start - off <= end_t]
        owned, bad, _ = _classify(frames, fps, ps)
        scored.append((bad, -owned, j))
    best = min(scored)[:2]
    js = sorted(j for b, o, j in scored if (b, o) == best)
    if js[-1] - js[0] != len(js) - 1:
        return Timeline(0.0, 0, problems=["有两种相距较远的对齐同样可信，无法确定录像起点"])
    offset = (js[0] + js[-1]) / 2 * ALIGN_STEP_S
    # 细调：让「亮起 − 按下」的中位数为 0；细调后矛盾不能变多
    ps = [Press(t - obs_start - offset, k, e) for t, k, e in log if 0.0 <= t - obs_start - offset <= end_t]
    _classify(frames, fps, ps)
    res = [frames[p.onset].t - p.t for p in ps if p.onset is not None]
    if res:
        fine = offset - statistics.median(res)
        ps2 = [Press(t - obs_start - fine, k, e) for t, k, e in log if 0.0 <= t - obs_start - fine <= end_t]
        if _classify(frames, fps, ps2)[:2] == (-best[1], best[0]):
            offset = fine
    tl = Timeline(offset, 0)
    tl.presses = [Press(t - obs_start - offset, k, e) for t, k, e in log if 0.0 <= t - obs_start - offset <= end_t]
    owned, bad, notes = _classify(frames, fps, tl.presses)
    tl.pairs = owned
    if owned < MIN_PAIRS:
        tl.problems.append(f"按键记录与录像对不上（配对 {owned} 个）")
    tl.problems += notes
    tl.problems += _event_problems(log, obs_start, offset, end_t)
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


def left_shown_held(frames: list[Frame], fps: float, since: float, until: float) -> bool:
    """录像里左键格子在 [since + MATCH_LATE_S, until] 是否一直亮着（与记录说的「按着」一致）。"""
    a = max(0, int(math.ceil((since + MATCH_LATE_S) * fps)))
    b = min(len(frames) - 1, int(math.floor(until * fps)))
    return all(frames[i].lit["L"] for i in range(a, b + 1))


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
        if not left_shown_held(frames, fps, hold, frames[f].t):
            c.reason = "按键记录说开火时左键按着，但录像里左键格子没有一直亮着（记录可能缺了松开）"
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
