"""切枪「按键 → 第一发」时长分析（P0-5，指引见 docs/measurement/p0-5-guide.md）。

输入：features.py 产出的逐帧特征 CSV，以及输入显示层的按键记录 input_log.csv。对每一次「切枪键」按下：
- 起点 s：输入显示层对应格子从灭变亮的第一帧
- 终点 f：之后第一帧枪口火光。条件：火光指标 flash 连续 MIN_FLASH_FRAMES 帧不低于 FLASH_MIN，
  且在火光之后 AV_MIN_LAG–AV_MAX_LAG 帧内**开始**出现枪声（音量从低于到不低于 AUDIO_SHOT_MIN）。
  实测 OBS 录像里声音比画面晚 3–5 帧；窗口不超过下一次切枪。只看音频不准，所以时刻取画面
- 时长 = (f - s) / fps × timescale

逐次检查是否有效（任何一条不满足就作废，并写明原因）：
1. 切枪前手里的武器与该项要求一致，切过去的武器也一致（按录像里的按键顺序推算）
2. 切枪键按下时左键没有按着
3. 在下一次切枪之前找到了经枪声确认的火光
4. 开火时左键是按着的，且**这一次连续按住**开始于切枪之后、比火光至少早 MIN_LEAD_FRAMES 帧
   （只看最早一次按左键不够：先轻点一下又松开、很晚才再按住，会被前一次掩盖）
5. 与按键记录交叉核对：这次切枪键亮起期间，记录里恰好只按了一次（输入显示层每次按键至少亮 0.1 秒，
   两次快速连按会合成一次亮起，Q 的方向就会推错）；从录像开始到这一发火光之间，记录里的每一次切枪相关按键
   都在录像里亮过（否则有按键漏显示，武器推算不可靠）

按键记录是全系统的（在控制台输入命令也会按到数字键），所以只用它做「核对」，不用它推断手里的武器。
录像开始时手里拿什么，录像本身看不出来，每段录像的第一次切枪默认作废；人工看过录像后用 --initial 声明。

只处理有枪口火光的项目。挥刀（D）、检视（F、G）、拔刀（K1）需要另外的判据，不在这里。
"""

import argparse
import csv
import datetime
import statistics
import sys
from dataclasses import dataclass

SELECT_KEYS = {"1": "ak", "2": "glock", "3": "knife"}
WEAPONS = set(SELECT_KEYS.values())
SWITCH_KEYS = ("1", "2", "3", "Q", "wheel")
LOG_KEY_NAMES = {"1": "1", "2": "2", "3": "3", "Q": "Q", "滚轮": "wheel"}

# 每个测量项：触发键、切之前手里的武器、切之后的武器
ITEMS: dict[str, tuple[str, str, str]] = {
    "A": ("1", "knife", "ak"),
    "B": ("2", "ak", "glock"),
    "C": ("1", "glock", "ak"),
    "E1": ("Q", "glock", "ak"),
    "E2": ("Q", "ak", "glock"),
}

MIN_LEAD_FRAMES = 12        # 这次按住左键至少要比火光早这么多帧（60 fps 下 0.2 s 真实时间）
FLASH_MIN = 100             # 火光帧的最低指标（实测开枪 650–2200，非开枪帧为 0 或个位数）
MIN_FLASH_FRAMES = 3        # 火光至少连续这么多帧（慢动作下真实火光持续多帧，单帧的橙色更可能是别的特效）
AUDIO_SHOT_MIN = 2500       # 枪声的音量下限（实测：枪声 3800–14500，拔枪等声音不超过约 1000）
AV_MIN_LAG, AV_MAX_LAG = 1, 8   # 枪声开始相对火光的延迟窗口（帧），实测 3–5
LOG_MATCH_TOL_S = 0.12      # 按键记录与录像中按键亮起的对应容差（秒）


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


def lit_until(frames: list[Frame], key: str, start: int) -> int:
    """从 start 开始连续点亮到哪一帧为止（返回第一个熄灭的帧号）。"""
    e = start
    while e < len(frames) and frames[e].lit[key]:
        e += 1
    return e


def key_events(frames: list[Frame]) -> list[tuple[int, str]]:
    """按时间排序的所有切枪相关按键：1、2、3、Q、wheel。"""
    return sorted((i, k) for k in SWITCH_KEYS for i in onsets(frames, k))


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


def audio_onsets(frames: list[Frame], start: int, end: int) -> list[int]:
    """(start, end) 之间枪声开始的帧：音量从低于阈值变为不低于阈值。"""
    return [f for f in range(max(start, 1), end)
            if frames[f].audio >= AUDIO_SHOT_MIN and frames[f - 1].audio < AUDIO_SHOT_MIN]


def find_flash(frames: list[Frame], start: int, end: int) -> int | None:
    """(start, end) 之间第一帧经枪声确认的火光；音画配对不越过 end。"""
    shots = audio_onsets(frames, start, end)
    for f in range(start + 1, end):
        if frames[f].flash < FLASH_MIN or frames[f - 1].flash >= FLASH_MIN:
            continue  # 只看火光开始的那一帧
        run = f
        while run < end and frames[run].flash >= FLASH_MIN:
            run += 1
        if run - f < MIN_FLASH_FRAMES:
            continue
        if any(f + AV_MIN_LAG <= a <= f + AV_MAX_LAG for a in shots):
            return f
    return None


def has_gunshot(frames: list[Frame], start: int, end: int) -> bool:
    return bool(audio_onsets(frames, start, end))


def held_left_since(frames: list[Frame], f: int) -> int | None:
    """开火帧 f 时左键所在的那一次连续按住，从哪一帧开始；开火时左键没按着则返回 None。"""
    if not frames[f].lit["L"]:
        return None
    s = f
    while s > 0 and frames[s - 1].lit["L"]:
        s -= 1
    return s


# ---------- 与按键记录交叉核对 ----------

def read_key_log(path: str) -> list[tuple[float, str]]:
    """input_log.csv → [(unix 时间, 键名)]，只取切枪相关键的按下。"""
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("key") in LOG_KEY_NAMES and r.get("event") in ("down", "wheel"):
                out.append((float(r["t_unix"]), LOG_KEY_NAMES[r["key"]]))
    return sorted(out)


def align_log(frames: list[Frame], log: list[tuple[float, str]], guess_start_unix: float,
              search_s: float = 2.0) -> tuple[float | None, int]:
    """估计「录像第 0 帧」对应的 unix 时间。返回 (录像起点, 参与估计的配对数)。

    guess_start_unix 来自 OBS 文件名（只精确到秒）；在其附近，用同一个键的「记录时间 − 录像亮起时间」
    取众数再取中位数。
    """
    diffs = []
    for k in SWITCH_KEYS:
        lt = [t for t, kk in log if kk == k]
        for i in onsets(frames, k):
            for t in lt:
                d = t - frames[i].t
                if abs(d - guess_start_unix) <= search_s:
                    diffs.append(d)
    if not diffs:
        return None, 0
    bins: dict[int, int] = {}
    for d in diffs:
        b = round(d / 0.02)
        bins[b] = bins.get(b, 0) + 1
    mode = max(bins, key=lambda b: bins[b]) * 0.02
    near = [d for d in diffs if abs(d - mode) <= 0.05]
    return statistics.median(near), len(near)


def log_in_video(log: list[tuple[float, str]], start_unix: float, n_frames: int, fps: float) -> list[tuple[float, str]]:
    """把按键记录换算成录像时间，只保留录像时间范围内的。"""
    end = n_frames / fps
    return [(t - start_unix, k) for t, k in log if 0.0 <= t - start_unix <= end]


def log_problems(frames: list[Frame], vlog: list[tuple[float, str]], trigger: str, s: int, f: int) -> str:
    """交叉核对一次切枪；没有问题返回空字符串。vlog 为已换算成录像时间的按键记录。"""
    e = lit_until(frames, trigger, s)
    t0, t1 = frames[s].t - LOG_MATCH_TOL_S, frames[min(e, len(frames) - 1)].t + LOG_MATCH_TOL_S
    n = sum(1 for t, k in vlog if k == trigger and t0 <= t <= t1)
    if n != 1:
        return f"这次 {trigger} 亮起期间，按键记录里有 {n} 次按下（应为 1 次）"
    shown = {k: [frames[i].t for i in onsets(frames, k)] for k in SWITCH_KEYS}
    for t, k in vlog:
        if t > frames[f].t:
            break
        if not any(-LOG_MATCH_TOL_S <= v - t <= LOG_MATCH_TOL_S for v in shown[k]):
            return f"按键记录里 {t:.2f}s 的 {k} 在录像里没有亮起，武器推算不可靠"
    return ""


def analyze(frames: list[Frame], fps: float, item: str, timescale: float,
            initial: tuple[str | None, str | None] = (None, None),
            vlog: list[tuple[float, str]] | None = None) -> list[Cycle]:
    trigger, want_from, want_to = ITEMS[item]
    events = key_events(frames)
    states = track_weapons(events, initial)
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
            c.reason = ("有枪声，但没有找到与之配对的火光" if has_gunshot(frames, s, end)
                        else "下一次切枪之前没有开枪（可能左键松得太早）")
            continue
        c.flash_frame = f
        hold = held_left_since(frames, f)
        if hold is None:
            c.reason = "开火时左键没有按着"
            continue
        if hold <= s:
            c.reason = "开火时的这次按住在切枪之前就开始了"
            continue
        if f - hold < MIN_LEAD_FRAMES:
            c.reason = f"这次按住左键只比火光早 {f - hold} 帧，可能按晚了"
            continue
        if vlog is None:
            c.reason = "没有提供按键记录，无法核对连按与漏显示"
            continue
        problem = log_problems(frames, vlog, trigger, s, f)
        if problem:
            c.reason = problem
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
    ap.add_argument("--key-log", required=True, help="输入显示层的 input_log.csv，用于核对连按与漏显示")
    ap.add_argument("--starts", nargs="+", required=True,
                    help="每段录像的开始时间（OBS 文件名，'YYYY-MM-DD HH-MM-SS'），与特征文件一一对应")
    ap.add_argument("--timescale", type=float, default=0.1)
    ap.add_argument("--initial", nargs="*", default=[],
                    help="人工看过录像后，声明每段录像开始时的「手里,上一把」，例如 knife,ak；'-' 表示不知道")
    ap.add_argument("--samples-out", help="把逐样本结果（帧号、时长、作废原因）写入这个 CSV")
    a = ap.parse_args()
    if len(a.starts) != len(a.features_csv) or (a.initial and len(a.initial) != len(a.features_csv)):
        sys.exit("--starts 与 --initial 的个数必须与特征文件个数相同")
    log = read_key_log(a.key_log)
    rows = []
    all_cycles = []
    for idx, path in enumerate(a.features_csv):
        frames, fps = read_features(path)
        initial = parse_initial(a.initial[idx]) if a.initial else (None, None)
        guess = datetime.datetime.strptime(a.starts[idx], "%Y-%m-%d %H-%M-%S").timestamp()
        start_unix, pairs = align_log(frames, log, guess)
        name = path.replace("\\", "/").split("/")[-1]
        if start_unix is None or pairs < 3:
            print(f"{name}：按键记录与录像对不上（配对 {pairs} 个），这段录像的样本全部作废")
            vlog = None
        else:
            vlog = log_in_video(log, start_unix, len(frames), fps)
            print(f"{name}：录像起点 = 文件名时间 {start_unix - guess:+.3f}s（{pairs} 个配对）")
        for c in analyze(frames, fps, a.item, a.timescale, initial, vlog):
            tag = "有效" if c.valid else "作废"
            dur = f"{c.duration_s * 1000:7.1f} ms" if c.valid else " " * 10
            flash = f"{frames[c.flash_frame].t:8.3f}s" if c.flash_frame is not None else "       —"
            print(f"{name:10s} 按键 {frames[c.start_frame].t:8.3f}s  火光 {flash}  {dur}  {tag} {c.reason}")
            rows.append([a.item, name, c.start_frame, c.flash_frame if c.flash_frame is not None else "",
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
