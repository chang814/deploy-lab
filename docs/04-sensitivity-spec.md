# 灵敏度与 FOV 规格（草案，待 GPT 审定 · P0-3）

## 1. 视角旋转

CS2 中，每个原始鼠标计数（count）对应的旋转角度：

```
yaw_per_count   = sensitivity × m_yaw    （m_yaw 默认 0.022°）
pitch_per_count = sensitivity × m_pitch  （m_pitch 默认 0.022°）
```

- 不使用任何鼠标加速、平滑或基于帧率的缩放
- 输入必须是**原始计数**（Windows Raw Input），不能是经过系统指针速度/加速处理后的像素位移
- 子计数精度不能丢失：每帧累加的角度用 float64 保存

### 360° 距离（验收基准）

```
counts_per_360 = 360 / (sensitivity × 0.022)
cm_per_360     = counts_per_360 / DPI × 2.54
```

| DPI | sens | counts/360° | cm/360° |
|---|---|---|---|
| 800 | 1.0 | 16363.64 | 51.95 |
| 400 | 2.0 | 8181.82 | 51.95 |
| 800 | 2.5 | 6545.45 | 20.78 |
| 1600 | 0.8 | 20454.55 | 32.47 |

## 2. 视野（FOV）

CS2 的 `fov_cs_debug` 默认为 90，定义为 **4:3 下的水平 FOV**，宽屏时保持垂直 FOV 不变，向两侧扩展：

```
vfov = 2 × atan( tan(90°/2) × 3/4 ) = 73.7398°
hfov(aspect) = 2 × atan( tan(vfov/2) × aspect )
  16:9  → 106.2602°
  16:10 → 100.3888°
  4:3   → 90°
```

Godot 实现：`Camera3D.keep_aspect = KEEP_HEIGHT`，`fov = 73.7398`。

Viewmodel（第一人称武器）使用独立相机，默认 `viewmodel_fov 68`（同样按 4:3 水平定义换算）。

## 3. 从 CS2 导入（只读）

- 读取路径：`<Steam>/userdata/<id>/730/local/cfg/` 下的用户配置文件（具体文件名待调研确认）
- 只读取：`sensitivity`、`m_yaw`、`m_pitch`、`zoom_sensitivity_ratio`、`viewmodel_fov`、`viewmodel_offset_*`
- 绝不写入 CS2 的任何文件

## 4. 待确认问题（交给 GPT 审定）

- [ ] 开镜灵敏度（`zoom_sensitivity_ratio`）与各狙击镜 FOV 的换算
- [ ] pitch 上下限（±89°）
- [ ] Godot 在 `MOUSE_MODE_CAPTURED` 下的 `InputEventMouseMotion.relative` 是否等于原始计数（由 P0-4 spike 验证）
