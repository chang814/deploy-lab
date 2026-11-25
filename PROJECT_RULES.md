# 项目规范（所有贡献者共同遵守，包括 AI agent）

## 红线
1. 不得添加任何 Valve / CS2 的模型、动画、音效、贴图、地图或从游戏文件中提取的文件；不得复刻任何现有地图的布局或外观（任一都不行，包括换皮或近似还原）。
2. 不得编写读取、注入、hook CS2 进程的代码；只允许读取 CS2 的 cfg 文本文件，且只读。
3. 第三方素材必须登记在 `assets/CREDITS.md`（来源、作者、许可证）。

## Git
- 分支：`main` 受保护，只通过 PR 合入。对应 Issue 的分支一律命名为 `task/<Issue号>`（同时作为认领锁，见 `docs/05-shared-folder-protocol.md`）；改动类型由提交前缀体现。
- 提交信息使用 [约定式提交](https://www.conventionalcommits.org/zh-hans/)：`feat:` `fix:` `docs:` `test:` `refactor:` `chore:` `perf:`。
- 提交信息末尾注明执行者：`Agent: claude | gpt | gemini | human`。
- 合并方式：Squash merge。

## 版本
- 语义化版本；每个里程碑结束打 tag `vX.Y.Z` 并发布 GitHub Release。
- `CHANGELOG.md` 遵循 Keep a Changelog 格式，未发布的改动写在 `[Unreleased]` 下。

## 代码（Godot 4 / GDScript）
- 静态类型：所有变量与函数参数写类型注解。
- 时间、角度一律注明单位（变量名后缀 `_s`、`_ms`、`_deg`、`_rad`）。
- 手感相关常量不得写死在代码里，放在数据文件（`data/`）中。
- 涉及换算或时序的逻辑必须有单元测试。

## 文档
- 中文为主；代码标识符和提交前缀用英文。
- 决策记录写进 `docs/decisions/NNNN-<title>.md`（背景 / 选项 / 决定 / 后果）。
