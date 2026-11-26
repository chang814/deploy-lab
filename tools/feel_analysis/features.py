"""从录像中逐帧提取分析所需的特征，写成 CSV 缓存。

每帧三类特征：
1. 输入显示层（tools/input_overlay）每个按键格子是否点亮：取格子中心一小块的平均颜色，绿明显多于红即为点亮
2. 枪口火光指标 flash：画面中部（去掉顶部小地图、输入显示层与底部 HUD，缩小 2 倍）中「高饱和橙色」像素的个数。
   实测：开枪那一帧从 0 跳到几百到几千（Glock 约 650、AK 约 1800–2200），拔枪时手套与枪身的高光、Dust2 的沙色墙面都保持 0。
   早先用「接近白热」的亮度判据，会被拔 Glock 时的高光误触发，Glock 开火时反而下降，已弃用
3. 音频 audio：每帧时长内的音量（RMS），用来确认真的开了枪

用法：
    python -I features.py <录像> <输出 CSV> [--overlay-x 49 --overlay-y 51 --cell-step 64.75]

只读取录像文件，不接触游戏进程。依赖 ffmpeg / ffprobe 与 numpy。
"""

import argparse
import csv
import json
import subprocess
import sys

import numpy as np

KEYS = ["1", "2", "3", "Q", "F", "wheel", "L", "R"]

# 默认值对应 1724x1080 录像、输入显示层在默认位置（左上角 12,12）
DEFAULT_CELL_X0 = 49.0      # 第一个格子中心的 x（视频像素）
DEFAULT_CELL_STEP = 64.75   # 相邻格子中心的间距
DEFAULT_CELL_Y = 51         # 格子中心的 y
PATCH = 8                   # 取格子中心 ±PATCH 像素的方块

# 火光区域（相对画面宽高的比例，对应 1724x1080 下 x 300–1724、y 150–970）与高饱和橙色判据
FLASH_REGION = (300 / 1724, 150 / 1080, 1.0, 970 / 1080)   # 左、上、右、下
FLASH_R_MIN, FLASH_RB_DIFF_MIN, FLASH_G_MIN = 235, 150, 90


def probe(video: str) -> tuple[int, int, float]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,avg_frame_rate",
         "-of", "json", video], capture_output=True, check=True, text=True).stdout
    s = json.loads(out)["streams"][0]
    num, den = s["avg_frame_rate"].split("/")
    return int(s["width"]), int(s["height"]), float(num) / float(den)


def _frames(video: str, vf: str, w: int, h: int):
    """用 ffmpeg 输出 rgb24 原始帧，逐帧产出 (h, w, 3) 的 numpy 数组。"""
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", video, "-vf", vf, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         stdout=subprocess.PIPE)
    n = w * h * 3
    try:
        while True:
            buf = p.stdout.read(n)
            if len(buf) < n:
                break
            yield np.frombuffer(buf, dtype=np.uint8).reshape(h, w, 3)
    finally:
        p.stdout.close()
        if p.wait() != 0:
            raise RuntimeError(f"ffmpeg 读取失败：{video}")


def overlay_lit(video: str, x0: float, step: float, y: int) -> list[list[bool]]:
    """每帧每个按键格子是否点亮。"""
    width = int(x0 + step * (len(KEYS) - 1) + PATCH + 2)
    top = y - PATCH
    out = []
    for fr in _frames(video, f"crop={width}:{2 * PATCH}:0:{top}", width, 2 * PATCH):
        row = []
        for i in range(len(KEYS)):
            cx = int(round(x0 + step * i))
            patch = fr[:, cx - PATCH:cx + PATCH, :].astype(np.int32)
            g_minus_r = float((patch[:, :, 1] - patch[:, :, 0]).mean())
            row.append(g_minus_r > 40.0)
        out.append(row)
    return out


def saturated_orange(fr: np.ndarray) -> int:
    """一帧中「高饱和橙色」像素的个数：红很高、红远大于蓝、且有一定绿色（排除纯红）。"""
    r = fr[:, :, 0].astype(np.int16)
    g = fr[:, :, 1].astype(np.int16)
    b = fr[:, :, 2].astype(np.int16)
    return int(((r >= FLASH_R_MIN) & (r - b >= FLASH_RB_DIFF_MIN) & (g >= FLASH_G_MIN)).sum())


def flash_counts(video: str, w: int, h: int) -> list[int]:
    """每帧火光区域（缩小 2 倍）中高饱和橙色像素的个数。"""
    x0, y0 = int(w * FLASH_REGION[0]), int(h * FLASH_REGION[1])
    cw, ch = int(w * FLASH_REGION[2]) - x0, int(h * FLASH_REGION[3]) - y0
    sw, sh = cw // 2, ch // 2
    return [saturated_orange(fr) for fr in _frames(video, f"crop={cw}:{ch}:{x0}:{y0},scale={sw}:{sh}:flags=area", sw, sh)]


def audio_rms(video: str, fps: float, n_frames: int) -> list[float]:
    """每个视频帧时长内的音频 RMS（单声道，48 kHz）。没有音轨时全为 0。

    假设音轨从 0 秒开始，与视频对齐（OBS 录像如此）；两者之间的固定延迟由分析时的搜索窗口吸收。
    """
    p = subprocess.run(["ffmpeg", "-v", "error", "-i", video, "-vn", "-ac", "1", "-ar", "48000", "-f", "s16le", "-"],
                       capture_output=True)
    if p.returncode != 0 or not p.stdout:
        return [0.0] * n_frames
    x = np.frombuffer(p.stdout, dtype=np.int16).astype(np.float64)
    spf = 48000.0 / fps
    out = []
    for i in range(n_frames):
        a, b = int(round(i * spf)), int(round((i + 1) * spf))
        seg = x[a:b]
        out.append(float(np.sqrt((seg ** 2).mean())) if len(seg) else 0.0)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="逐帧提取按键点亮与枪口火光特征")
    ap.add_argument("video")
    ap.add_argument("out_csv")
    ap.add_argument("--overlay-x", type=float, default=DEFAULT_CELL_X0)
    ap.add_argument("--overlay-y", type=int, default=DEFAULT_CELL_Y)
    ap.add_argument("--cell-step", type=float, default=DEFAULT_CELL_STEP)
    a = ap.parse_args()

    w, h, fps = probe(a.video)
    lit = overlay_lit(a.video, a.overlay_x, a.cell_step, a.overlay_y)
    flash = flash_counts(a.video, w, h)
    n = min(len(lit), len(flash))
    if n == 0:
        sys.exit("没有读到任何帧")
    audio = audio_rms(a.video, fps, n)
    with open(a.out_csv, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["frame", "t", "fps"] + [f"lit_{k}" for k in KEYS] + ["flash", "audio"])
        for i in range(n):
            wr.writerow([i, f"{i / fps:.4f}", f"{fps:.4f}"] + [int(x) for x in lit[i]] + [flash[i], f"{audio[i]:.0f}"])
    print(f"已写入 {a.out_csv}：{n} 帧，{fps:g} fps")


if __name__ == "__main__":
    main()
