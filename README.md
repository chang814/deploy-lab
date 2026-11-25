# mcs

> 一款以「切枪 / 切刀手感」与「灵敏度 1:1 对齐」为核心的 FPS 手感练习工具。
> 状态：**Phase 0 · 立项与调研**（v0.0.x）

## 这是什么

- 还原主流战术射击游戏的 **切枪、拔刀、检视手感**（时长、节奏、动画曲线）
- **灵敏度与 CS2 完全一致**（yaw 0.022°/count + FOV 对齐），可从本地 CS2 配置只读导入，练完无缝切回
- 多种刀型的手感库（原创模型，数据驱动）

## 这不是什么

- 不是 CS2 的复刻：不包含、不分发任何 Valve 的模型、动画、音效、贴图
- 不读取、不注入、不修改 CS2 进程（无 VAC 风险）

## 文档

| 文档 | 内容 |
|---|---|
| [立项书](docs/00-charter.md) | 目标、范围、红线、验收指标 |
| [路线图](docs/01-roadmap.md) | 阶段与版本计划 |
| [多 agent 工作流](docs/02-workflow.md) | Claude / GPT / Gemini 分工与协作流程 |
| [手感测量方案](docs/03-feel-measurement.md) | 如何黑盒测出切枪/检视时长 |
| [灵敏度规格](docs/04-sensitivity-spec.md) | 灵敏度与 FOV 换算公式及验收用例 |
| [共享文件夹协作协议](docs/05-shared-folder-protocol.md) | Claude 与 Codex 共用一个文件夹时的规则 |
| [Codex 协作提示词](docs/prompts/codex-kickoff.md) | 启动 Codex 时粘贴的提示词 |
| [项目规范](PROJECT_RULES.md) | 所有人（含 AI）共同遵守的规则 |
| [更新日志](CHANGELOG.md) | 版本记录 |

## 技术栈

Godot 4（GDScript）· Git + GitHub（Issues / PR / Releases）· 语义化版本 · 约定式提交
