"""P0-5 人工逐帧抽查的辅助工具：为每个有效样本拼一张对照图，并找出「换枪」帧。

用法：python -I spotcheck.py 录像目录 samples.csv 输出目录

对每个有效样本（samples.csv 里 valid=1 的行）：
- 第 1 行：叠加层 s−1 | s（切枪键格子应在 s 才亮）
- 第 2 行：换枪帧 swap−1 | swap（武器区域逐帧平均像素差第一次超过 SWAP_DIFF 的帧，即旧武器消失、新武器开始拔出）
- 第 3 行：画面中部 f−1 | f（火光应在 f 才出现）
另存一张 ammo.png：每个样本 f−2 … f+1 的弹药数字（开枪那一帧数字减一并变白），用来核对火光帧是否晚了。

帧号与 features.py 一致：顺序解码、按解码序号取帧（不用 -ss 跳转，跳转在这类录像上会差一帧）。
这是给人看的辅助工具，结论以人工目视为准；不参与自动判定。
"""

import argparse
import csv
import subprocess
import sys
from collections import defaultdict

import numpy as np
from PIL import Image, ImageDraw

W, H = 1724, 1080
SWAP_DIFF = 10.0                              # 换枪时武器区域的平均像素差（实测约 32，平时 < 3）
WEAPON = (slice(540, 1080), slice(900, 1724))
OVERLAY = (slice(0, 110), slice(0, 560))
CENTER = (slice(300, 1080), slice(700, 1724))
AMMO = (slice(990, 1050), slice(1080, 1220))


def decode(video: str, wanted: list[int]) -> dict[int, np.ndarray]:
    ranges: list[list[int]] = []
    for n in sorted(set(wanted)):
        if ranges and n == ranges[-1][1] + 1:
            ranges[-1][1] = n
        else:
            ranges.append([n, n])
    bs = chr(92)   # 滤镜表达式里的逗号要转义
    expr = "+".join(f"between(n{bs},{a}{bs},{b})" for a, b in ranges)
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", video, "-vf", f"select={expr}", "-fps_mode", "passthrough",
                          "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
    out = {}
    try:
        for n in sorted(set(wanted)):
            buf = p.stdout.read(W * H * 3)
            if len(buf) != W * H * 3:
                raise SystemExit(f"{video} 第 {n} 帧读不到")
            out[n] = np.frombuffer(buf, np.uint8).reshape(H, W, 3)
    finally:
        p.stdout.close()
        if p.wait(timeout=60) != 0:
            raise SystemExit(f"ffmpeg 解码 {video} 失败（退出码 {p.returncode}）")
    return out


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="P0-5 逐帧抽查对照图")
    ap.add_argument("video_dir")
    ap.add_argument("samples_csv")
    ap.add_argument("out_dir")
    a = ap.parse_args()
    with open(a.samples_csv, encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r["valid"] == "1"]
    by_video: dict[str, list[tuple[int, dict]]] = defaultdict(list)
    for i, r in enumerate(rows):
        by_video[r["video"].removesuffix(".csv")].append((i + 1, r))
    lines, ammo = [], []
    for video, items in by_video.items():
        want = []
        for _, r in items:
            s, f = int(r["start_frame"]), int(r["flash_frame"])
            want += list(range(s - 8, s + 32)) + list(range(f - 2, f + 2))
        fr = decode(f"{a.video_dir}/{video}.mp4", want)
        for idx, r in items:
            s, f = int(r["start_frame"]), int(r["flash_frame"])
            diffs = [float(np.abs(fr[n + 1][WEAPON].astype(int) - fr[n][WEAPON].astype(int)).mean())
                     for n in range(s - 8, s + 31)]
            jumps = [s - 8 + k + 1 for k, d in enumerate(diffs) if d > SWAP_DIFF]
            sw = jumps[0] if jumps else None
            top = np.concatenate([fr[s - 1][OVERLAY], fr[s][OVERLAY]], axis=1)
            mid = (np.concatenate([fr[sw - 1][CENTER], fr[sw][CENTER]], axis=1) if sw is not None
                   else np.zeros((780, 2048, 3), np.uint8))
            bot = np.concatenate([fr[f - 1][CENTER], fr[f][CENTER]], axis=1)
            mid = np.array(Image.fromarray(mid).resize((1024, 390)))
            bot = np.array(Image.fromarray(bot).resize((1024, 390)))
            cv = np.zeros((930, 1120, 3), np.uint8)
            cv[:110] = top
            cv[130:520, :1024] = mid
            cv[540:930, :1024] = bot
            im = Image.fromarray(cv)
            ImageDraw.Draw(im).text((5, 113), f"{idx:02d} {r['item']} {video} s={s} swap={sw} f={f}", fill=(255, 255, 0))
            im.save(f"{a.out_dir}/{idx:02d}_{r['item']}_{video}.png")
            ammo.append((idx, np.concatenate([fr[n][AMMO] for n in (f - 2, f - 1, f, f + 1)], axis=1)))
            pre = max(diffs[:sw - (s - 8) - 1]) if sw is not None and sw > s - 7 else None   # s−8 … swap−1 之间
            lines.append((idx, r["item"], video, s, sw, f, len(jumps), pre))
    lines.sort()
    print("序号 项 录像 s swap f 大跳变次数 swap−s f−swap 换枪前最大逐帧差")
    for idx, item, video, s, sw, f, nj, pre in lines:
        print(idx, item, video, s, sw, f, nj, None if sw is None else sw - s, None if sw is None else f - sw,
              None if pre is None else f"{pre:.1f}")
    ammo.sort(key=lambda x: x[0])
    sheet = Image.new("RGB", (620, 60 * len(ammo)))
    dr = ImageDraw.Draw(sheet)
    for k, (idx, strip) in enumerate(ammo):
        sheet.paste(Image.fromarray(strip), (60, k * 60))
        dr.text((5, k * 60 + 22), f"{idx:02d}", fill=(255, 255, 0))
    sheet.save(f"{a.out_dir}/ammo.png")


if __name__ == "__main__":
    main()
