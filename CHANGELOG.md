# 更新日志

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

每个版本下只保留一组「新增 / 变更 / 修复」小节；新条目加到对应小节的末尾，不要另起同名小节。

## [Unreleased]
### 新增
- 共享文件夹协作协议（worktree 隔离、单写入者、GitHub 交接）
- Codex 协作提示词 `docs/prompts/codex-kickoff.md`
- MIT 许可证
- P0-4 原始鼠标输入验证工程 `spikes/raw-input/`：按轮计数、360° 标柱场景、CSV 记录、实测步骤
- 独立基准 `tools/rawinput_counter.py`：直接读取 Windows Raw Input，与 Godot 按同一次点击分轮对比；边界位移、读取失败、绝对坐标都会把该轮标为作废（8 条测试）
- 视角换算模块 `look_math.gd`（含输入适配层 `look_step`）与 62 条单元测试；视角参数放在 `data/look_defaults.json`
- 原创练习地图设计文档 `docs/map/00-design.md`（M0）：中心大厅 + 6 个训练分区、尺度规范、数据驱动灰盒约定、原创性自查清单
- Gemini（Antigravity）启动提示词模板 `docs/prompts/gemini-kickoff.md`
- P0-4 比对脚本 `spikes/raw-input/tools/compare_runs.py`：按（会话, 轮号, 第几次记录）对齐 Godot 与 Raw Input 基准，生成报告数据与初步判定（15 条测试）
- 原创练习地图分区中文显示名 `data/map/zone_names.zh-CN.json`（Z0–Z6 共 7 个训练分区）

### 变更
- 项目更名为 mcs（仓库 chang814/mcs，本地主文件夹 `D:\桌面\mcs`）
- 审定灵敏度与 FOV 规格（Issue #2，GPT 审定、Claude 审查）：修正 16:10 FOV 舍入，补充复算结果、开镜/pitch 待测量方案及单元测试用例表
- 路线图新增「地图线」：原创练习地图 M0–M3；立项书范围加入原创练习地图，红线明确不复刻现有地图的布局或外观；v0.1 加入基础移动与碰撞，v0.2 加入最小靶场
- 工作流：调度分为方式 A（Claude 调度 codex exec）与方式 B（人类在工具中启动），记录并行原则
- 共享文件夹协议第 5 节：人类确认主文件夹的改动属于预期后，agent 可保持原样继续工作

## [0.0.1] - 2026-11-25
### 新增
- 项目骨架：立项书、路线图、多 agent 工作流草案、手感测量方案、灵敏度规格草案
- 共享项目规范 `PROJECT_RULES.md` 与三家 agent 的说明文件（`CLAUDE.md` / `AGENTS.md` / `GEMINI.md`）
- Issue 与 PR 模板
