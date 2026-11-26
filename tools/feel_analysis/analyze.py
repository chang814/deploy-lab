"""切枪「按键 → 第一发」时长分析（P0-5，指引见 docs/measurement/p0-5-guide.md）。

两个数据源，分工明确：
- 按键记录 input_log.csv（输入显示层从 Raw Input 读到的每一次按下 / 松开，毫秒精度）是**输入时间线的权威**：
  手里是哪把武器、左键何时按下与松开、按了几次，都以它为准
- 录像里输入显示层的格子只用来**把按键对到录像的帧上**：格子每次至少亮 0.1 秒，两次快速连按会合成一次亮起，
  所以不能用它数按键或判断左键状态

步骤：
1. 对齐：OBS 日志里的开录时刻（毫秒）给出录像第 0 帧的大致 unix 时间；在 ±ALIGN_SEARCH_S 内逐个试偏移。
   每个偏移下，按输入显示层自己的点亮规则由记录推算各格子的亮灭时间段（predicted_spans），与录像里的亮起逐段对应
   （_classify，开始与结束都要对上）；取矛盾最少的偏移。矛盾最少的候选必须连成一个区间（这不等于偏移被唯一确定，
   区间宽度记为对齐的不确定性，依赖偏移的判断按最不利的一端算）。对齐后仍有任何矛盾，或某个键的
   down / up 没有交替，整段录像作废
2. 逐次切枪：遍历记录里的切枪键按下，从人工声明的初始武器（--initial）开始推算武器。触发键必须有**自己的**
   格子亮起（不是被合并进上一次亮起的），起点 s = 那一次亮起的帧
3. 终点 f：s 之后、下一次切枪按键之前的第一声枪响（音量从低于到不低于 AUDIO_SHOT_MIN），在它之前
   AV_MIN_LAG–AV_MAX_LAG 帧内开始的火光（火光指标 ≥ FLASH_MIN）。窗口内必须**恰好一段**火光开始，
   且连续至少 MIN_FLASH_FRAMES 帧；有两段（例如旁边的橙色特效）就无法确定是哪一段，作废。
   已知局限：橙色特效与真实火光无缝重叠时没有第二个上升沿，工具分不出来，靠人工逐帧抽查兜底
4. 第二个证据：弹药数字在开枪那一帧减一并短暂变白（features.py 的 ammo 列）。s 之后第一次「变白」的帧 g
   必须落在 [f − AMMO_MAX_EARLY, f] 内，否则作废。开枪时刻取 g：第一批人工抽查中，火光很暗、没达到阈值的
   两次开枪，弹药数字比检测到的火光早 1 帧，其余 23 次两者在同一帧
5. 时长 = (g − s) / fps × timescale

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
AMMO_MIN = 200             # 弹药数字「变白」的像素数下限（第一批实测：开枪那一帧 440–680，其余 ≤ 42）
AMMO_CHECK_AFTER = 5       # 核对「只变白一次」时，火光之后再看这么多帧（连射下一发在 0.1 倍速下至少相隔约 60 帧；
                           # 第一批实测火光后 11 帧内没有第二次变白）
AMMO_MAX_EARLY = 1         # 弹药数字最多比检测到的火光早这么多帧（第一批 25 次实测：23 次 0 帧、2 次 1 帧；不另加裕量）
ALIGN_SEARCH_S = 0.15       # 对齐时，在 OBS 开录时刻附近搜索的范围
ALIGN_STEP_S = 0.002
MATCH_EARLY_S = 0.03        # 对齐后，录像里的亮起 / 熄灭最多比推算的早这么多（第一批实测见报告）
MATCH_LATE_S = 0.07         # 对齐后，录像里的亮起 / 熄灭最多比推算的晚这么多
MIN_LIT_S = 0.10            # 与 tools/input_overlay/overlay_state.py 的 MIN_LIT_S 一致（测试会核对）
WHEEL_LIT_S = 0.10          # 与 overlay_state.py 的 WHEEL_FLASH_S 一致
MERGE_GAP_S = 0.025         # 两段点亮间隔不到这么久（约 1.5 帧）时，录像里可能分辨不出；以录像为准决定合不合并
MIN_PAIRS = 3
MAX_FRAME_T_ERR_S = 0.0005  # 特征文件里第 i 帧的时间必须是 i / fps


@dataclass
class Frame:
    t: float
    lit: dict[str, bool]
    flash: int
    audio: float = 0.0
    ammo: int = -1          # 弹药数字区域接近白色的像素数；-1 = 特征文件里没有这一列


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
    shot_frame: int | None = None     # 开枪帧（弹药数字变白），时长的终点
    duration_s: float | None = None
    valid: bool = False
    reason: str = ""


@dataclass
class Timeline:
    """一段录像对齐后的按键时间线。"""
    offset: float               # 录像第 0 帧 = OBS 开录时刻 + offset
    pairs: int
    presses: list[Press] = field(default_factory=list)   # 录像结束之前的全部事件（含录像开始前），按时间排序
    problems: list[str] = field(default_factory=list)    # 非空 = 整段录像作废
    # 矛盾最少的候选偏移区间 [lo, hi]：区间内任何偏移都同样与录像一致，宽度表示对齐的不确定性
    offset_lo: float = 0.0
    offset_hi: float = 0.0


def read_features(path: str) -> tuple[list[Frame], float]:
    frames, fps = [], 0.0
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            fps = float(r["fps"])
            lit = {k[4:]: r[k] == "1" for k in r if k.startswith("lit_")}
            ammo = int(r["ammo"]) if r.get("ammo") not in (None, "") else -1
            frames.append(Frame(float(r["t"]), lit, int(r["flash"]), float(r.get("audio") or 0), ammo))
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


def predicted_spans(presses: list[Press], key: str, end_t: float) -> list[tuple[float, float, list[Press]]]:
    """按输入显示层的点亮规则（tools/input_overlay/overlay_state.py），由记录推出某个格子应当亮着的时间段。

    规则：按住期间亮着；每次按下之后至少亮 MIN_LIT_S（滚轮没有松开，每次亮 WHEEL_LIT_S）。重叠的时间段合成一段
    （间隔很短、录像里可能分辨不出的相邻段，留给 _classify 按录像决定）。返回 [(开始, 结束, 这一段里的按下)]，
    第一个按下开启这一段。
    """
    raw: list[tuple[float, float, Press]] = []
    evs = [p for p in presses if p.key == key]
    for i, p in enumerate(evs):
        if p.event == "wheel":
            raw.append((p.t, p.t + WHEEL_LIT_S, p))
        elif p.event == "down":
            up = next((q.t for q in evs[i + 1:] if q.event == "up"), math.inf)
            raw.append((p.t, max(up, p.t + MIN_LIT_S), p))
    spans: list[tuple[float, float, list[Press]]] = []
    for a, b, p in sorted(raw, key=lambda x: x[0]):
        if spans and a <= spans[-1][1]:
            s0, s1, ps = spans[-1]
            spans[-1] = (s0, max(s1, b), ps + [p])
        else:
            spans.append((a, b, [p]))
    return [(a, min(b, end_t), ps) for a, b, ps in spans]


def _classify(frames: list[Frame], fps: float, presses: list[Press]) -> tuple[int, int, list[str]]:
    """把「由记录推出的点亮时间段」与「录像里看到的点亮时间段」逐段对应，返回 (对上的段数, 矛盾数, 矛盾说明)。

    presses 要包含录像开始前的全部事件（第 0 帧时是否亮着取决于它们）。
    - 录像里的段：第 0 帧就亮着的一段（从第 0 帧开始），以及之后每次从灭到亮的一段
    - 推出的段开始于第 0 帧附近（≤ 1 帧 + MATCH_EARLY_S）时，可以对应「第 0 帧就亮着」的那段；否则对应
      开始时刻相差 [−MATCH_EARLY_S, +MATCH_LATE_S] 内的一次亮起
    - 推出的段在录像里没有对应的亮起，但紧跟在上一段之后（间隔 ≤ MERGE_GAP_S）且录像里上一段一直亮着没断：
      按录像看是合成了一段，把它并进上一段
    - 结束：推出的结束在录像结束前，录像里的结束必须在 [−MATCH_EARLY_S, +MATCH_LATE_S] 内；推出的段持续到录像
      结束，录像里也必须亮到不早于（推出的结束 − MATCH_EARLY_S）
    对上的段：第一个按下为 shown，拥有这次亮起；其余按下为 merged。推出的段录像里没有 → missing；
    录像里的段推不出来 → 记录缺了按下。
    """
    n = len(frames)
    end_t = n / fps
    owned, bad, notes = 0, 0, []
    for p in presses:
        p.onset, p.status = None, ""

    def seen_end_t(e: int) -> float:
        return e / fps if e < n else math.inf

    for k in OVERLAY_KEYS:
        seen = [(i, lit_until(frames, k, i)) for i in onsets(frames, k)]
        if frames[0].lit[k]:
            seen.insert(0, (0, lit_until(frames, k, 0)))
        taken: set[int] = set()
        cur = None   # 当前对上的段：[录像亮起帧, 录像熄灭帧, 推出的结束, 按下列表]

        def finish(c) -> None:
            nonlocal bad
            i, e, pend, _ = c
            se = seen_end_t(e)
            if pend < end_t - MATCH_LATE_S:
                ok = -MATCH_EARLY_S <= se - pend <= MATCH_LATE_S
            else:
                ok = se >= min(pend, end_t) - MATCH_EARLY_S
            if not ok:
                bad += 1
                notes.append(f"{frames[i].t:.2f}s 的 {k}：按记录应亮到 {min(pend, end_t):.2f}s，"
                             f"录像里亮到 {min(se, end_t):.2f}s")

        for a, b, ps in predicted_spans(presses, k, math.inf):
            if b <= 0.0:
                for p in ps:
                    p.status = "merged"   # 整段都在录像开始之前
                continue
            if a <= 1.0 / fps + MATCH_EARLY_S:
                cand = [(i, e) for i, e in seen if i not in taken and (i == 0 or frames[i].t - a <= MATCH_LATE_S)]
            else:
                cand = [(i, e) for i, e in seen
                        if i not in taken and i > 0 and -MATCH_EARLY_S <= frames[i].t - a <= MATCH_LATE_S]
            if cand:
                if cur is not None:
                    finish(cur)
                i, e = min(cand, key=lambda x: abs(frames[x[0]].t - max(a, 0.0)))
                taken.add(i)
                cur = [i, e, b, ps]
                ps[0].onset, ps[0].status = i, "shown"
                for p in ps[1:]:
                    p.status = "merged"
                owned += 1
                continue
            if cur is not None and a - cur[2] <= MERGE_GAP_S and seen_end_t(cur[1]) >= a:
                cur[2] = max(cur[2], b)
                cur[3] += ps
                for p in ps:
                    p.status = "merged"
                continue
            for p in ps:
                p.status = "missing"
            bad += 1
            notes.append(f"按键记录里 {a:.2f}s 的 {k} 应当亮起，录像里没有")
        if cur is not None:
            finish(cur)
        for i, _ in seen:
            if i not in taken:
                bad += 1
                notes.append(f"{frames[i].t:.2f}s 的 {k} 亮起在按键记录里推不出来")
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
    """录像第 0 帧 = obs_start + offset。在 ±ALIGN_SEARCH_S 内逐个试 offset，取物理模型矛盾最少的。

    矛盾最少的候选必须连成一个区间（否则有两种相距较远的对齐同样可信，拒绝）。这只说明最优候选是连续的，
    不说明偏移被唯一确定：区间宽度就是对齐的不确定性，记在 offset_lo / offset_hi 里。取区间中点，
    再按「亮起 − 按下」的中位数细调（细调后矛盾不能变多）。"""
    end_t = len(frames) / fps
    steps = int(round(ALIGN_SEARCH_S / ALIGN_STEP_S))
    scored = []
    for j in range(-steps, steps + 1):
        off = j * ALIGN_STEP_S
        ps = [Press(t - obs_start - off, k, e) for t, k, e in log if t - obs_start - off <= end_t]
        owned, bad, _ = _classify(frames, fps, ps)
        scored.append((bad, -owned, j))
    best = min(scored)[:2]
    js = sorted(j for b, o, j in scored if (b, o) == best)
    if js[-1] - js[0] != len(js) - 1:
        return Timeline(0.0, 0, problems=["有两种相距较远的对齐同样可信，无法确定录像起点"])
    offset = (js[0] + js[-1]) / 2 * ALIGN_STEP_S
    # 细调：让「亮起 − 按下」的中位数为 0；细调后矛盾不能变多
    ps = [Press(t - obs_start - offset, k, e) for t, k, e in log if t - obs_start - offset <= end_t]
    _classify(frames, fps, ps)
    res = [frames[p.onset].t - p.t for p in ps if p.onset is not None]
    if res:
        fine = offset - statistics.median(res)
        ps2 = [Press(t - obs_start - fine, k, e) for t, k, e in log if t - obs_start - fine <= end_t]
        if _classify(frames, fps, ps2)[:2] == (-best[1], best[0]):
            offset = fine
    tl = Timeline(offset, 0, offset_lo=js[0] * ALIGN_STEP_S, offset_hi=js[-1] * ALIGN_STEP_S)
    # 录像开始之前的事件也保留：第 0 帧时各键（包括左键）是否按着，由完整记录决定
    tl.presses = [Press(t - obs_start - offset, k, e) for t, k, e in log if t - obs_start - offset <= end_t]
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


def find_ammo_change(frames: list[Frame], start: int, end: int, flash: int) -> tuple[int | None, str]:
    """(start, end) 之间弹药数字第一次变白的帧，必须落在 [flash − AMMO_MAX_EARLY, flash] 内。

    从切枪到火光之后 AMMO_CHECK_AFTER 帧之间必须**恰好一次**变白：多一次说明画面里有别的白色干扰，无法确定
    哪一次是开枪，作废。已知局限：白色干扰与真实的数字变化无缝相连时只有一个上升沿，分不出来，靠人工逐帧抽查兜底。"""
    if frames[start].ammo < 0:
        return None, "特征文件里没有弹药数字（ammo 列），请用新版 features.py 重新提取"
    on = [g for g in range(max(start + 1, 1), end)
          if frames[g].ammo >= AMMO_MIN and frames[g - 1].ammo < AMMO_MIN]
    if not on:
        return None, "火光前后没有看到弹药数字变化，无法确认开枪"
    near = [x for x in on if x <= flash + AMMO_CHECK_AFTER]
    if len(near) > 1:
        return None, f"切枪到火光后 {AMMO_CHECK_AFTER} 帧之间弹药数字变白了 {len(near)} 次（第 {near[0]}、{near[1]} 帧），无法确定哪一次是开枪"
    g = on[0]
    if not flash - AMMO_MAX_EARLY <= g <= flash:
        return None, f"弹药数字变化（第 {g} 帧）与火光（第 {flash} 帧）对不上"
    return g, ""


# ---------- 分析 ----------

def analyze(frames: list[Frame], fps: float, item: str, timescale: float,
            initial: tuple[str | None, str | None], tl: Timeline) -> list[Cycle]:
    trigger, want_from, want_to = ITEMS[item]
    switches = [p for p in tl.presses if p.key in SWITCH_KEYS and is_press(p.event) and p.t >= 0.0]
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
        if p.onset == 0:
            c.reason = "这次按下的格子在第 0 帧就亮着，看不到亮起的时刻，起点不可靠"
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
        g, why = find_ammo_change(frames, s, end, f)
        if g is None:
            c.reason = why
            continue
        c.shot_frame = g
        hold = left_held_since(tl.presses, frames[g].t)
        if hold is None:
            c.reason = "开火时左键没有按着"
            continue
        if hold <= p.t:
            c.reason = "开火时的这次按住在切枪之前就开始了"
            continue
        if not left_shown_held(frames, fps, hold, frames[g].t):
            c.reason = "按键记录说开火时左键按着，但录像里左键格子没有一直亮着（记录可能缺了松开）"
            continue
        # 按住时刻来自记录、火光来自录像，两者的差依赖对齐偏移：按候选区间里最不利的一端算
        lead = frames[g].t - hold - (tl.offset - tl.offset_lo)
        if lead < MIN_LEAD_S:
            c.reason = f"这次按住左键（按对齐最不利的一端）只比开枪早 {lead * 1000:.0f} ms，可能按晚了"
            continue
        prev_t = switches[idx - 1].t if idx > 0 else 0.0
        lost = [q for q in tl.presses if q.status == "missing" and prev_t <= q.t <= frames[g].t]
        if lost:
            c.reason = f"按键记录里 {lost[0].t:.2f}s 的 {lost[0].key} 在录像里没有显示，输入显示层可能卡顿"
            continue
        c.duration_s = (g - s) / fps * timescale
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


SAMPLES_HEADER = ["item", "video", "start_frame", "flash_frame", "shot_frame", "duration_s", "valid", "reason"]


def append_samples(path: str, rows: list[list]) -> None:
    """把逐样本结果追加到 CSV。文件已存在时表头必须与 SAMPLES_HEADER 完全一致，否则拒绝（不同版本的列不能混写）。"""
    header = None
    try:
        with open(path, newline="", encoding="utf-8") as f:
            header = next(csv.reader(f), None)
    except FileNotFoundError:
        pass
    if header is not None and header != SAMPLES_HEADER:
        raise ValueError(f"{path} 的表头与当前版本不一致（{','.join(header)}），请换一个新文件")
    needs_newline = False
    if header is not None:
        with open(path, "rb") as f:
            f.seek(0, 2)
            if f.tell() > 0:
                f.seek(-1, 2)
                needs_newline = f.read(1) not in (b"\n", b"\r")
    with open(path, "a", newline="", encoding="utf-8") as f:
        if needs_newline:
            f.write("\r\n")   # csv 模块默认的行结束符
        w = csv.writer(f)
        if header is None:
            w.writerow(SAMPLES_HEADER)
        w.writerows(rows)


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
        merged = sum(1 for p in tl.presses if p.status == "merged" and p.t >= 0.0)
        missing = sum(1 for p in tl.presses if p.status == "missing" and p.t >= 0.0)
        print(f"{name}：录像起点 = OBS 开录时刻 {tl.offset * 1000:+.0f} ms"
              f"（候选区间 {tl.offset_lo * 1000:+.0f} ~ {tl.offset_hi * 1000:+.0f} ms，"
              f"宽 {(tl.offset_hi - tl.offset_lo) * 1000:.0f} ms；{tl.pairs} 段对上）；"
              f"合并显示的按下 {merged} 次，漏显示 {missing} 次")
        for prob in tl.problems:
            print(f"  整段作废：{prob}")
        for c in analyze(frames, fps, a.item, a.timescale, parse_initial(a.initial[idx]), tl):
            tag = "有效" if c.valid else "作废"
            dur = f"{c.duration_s * 1000:7.1f} ms" if c.valid else " " * 10
            flash = f"{frames[c.flash_frame].t:8.3f}s" if c.flash_frame is not None else "       —"
            early = (f"（弹药数字早 {c.flash_frame - c.shot_frame} 帧）"
                     if c.shot_frame is not None and c.shot_frame != c.flash_frame else "")
            print(f"{name:10s} 按键 {c.press_t:8.3f}s  火光 {flash}  {dur}  {tag} {c.reason}{early}")
            rows.append([a.item, name, c.start_frame if c.start_frame is not None else "",
                         c.flash_frame if c.flash_frame is not None else "",
                         c.shot_frame if c.shot_frame is not None else "",
                         f"{c.duration_s:.4f}" if c.valid else "", int(c.valid), c.reason])
            all_cycles.append(c)
    if a.samples_out:
        try:
            append_samples(a.samples_out, rows)
        except ValueError as e:
            sys.exit(str(e))
    s = summarize(all_cycles)
    if s["samples"]:
        print(f"{a.item}：有效 {s['samples']} 次，中位数 {s['median_s'] * 1000:.1f} ms，"
              f"最大偏差 {s['max_dev_s'] * 1000:.1f} ms（范围 {s['min_s'] * 1000:.1f}–{s['max_s'] * 1000:.1f} ms）")
    else:
        print(f"{a.item}：没有有效样本")
        sys.exit(1)


if __name__ == "__main__":
    main()
