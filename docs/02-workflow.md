# 多 agent 工作流（v0 草案）

> 这是一份会持续修改的文档。每个版本结束后，根据复盘结果更新它。

## 角色

| 角色 | 执行者 | 擅长 / 负责 | 不负责 |
|---|---|---|---|
| 产品负责人 / 验收人 | 人类 | 拍板、优先级、**主观手感测试**、账号与发布操作 | — |
| 技术负责人 / 集成 | Claude（Claude Code） | 架构、视角与动画手感调校、视觉审美、任务拆分、合并前把关 | 单独决定产品方向 |
| 严谨实现 / 审查 | GPT（Codex CLI） | 数学与换算、输入管线、状态机、单元测试、**交叉代码审查** | 美术方向 |
| 文案 / 调研 | Gemini（Antigravity） | README、更新日志、Release 说明、游戏内文本、长文档调研总结 | 核心代码 |

## 核心原则

1. **一家写，另一家审。** 任何合入 `main` 的代码 PR 必须由「非作者」的模型审查一次，再由人类确认合并。
2. **GitHub 是唯一事实来源。** 任务 = Issue，改动 = PR，讨论留在 Issue/PR 里，不留在某个聊天窗口里。
3. **共享同一份规范。** 三家的说明文件（`CLAUDE.md` / `AGENTS.md` / `GEMINI.md`）只写各自角色差异，通用规则统一引用 `PROJECT_RULES.md`。
4. **能测的不靠感觉。** 灵敏度、时长等指标必须有自动化测试或测量数据；只有「像不像」交给人类主观判断。

## 一个任务的生命周期

```
Issue（人类或 Claude 创建，打角色标签 owner:claude / owner:gpt / owner:gemini）
  → 分支 task/<issue号>（在 .worktrees/ 中，见 05-shared-folder-protocol.md）
  → 作者 agent 实现 + 自测
  → PR（模板里写：做了什么 / 怎么验证 / 风险）
  → 交叉审查（另一家模型，输出结构化审查意见）
  → 作者修改
  → 人类验收 → Squash 合并
  → 里程碑结束：Gemini 起草 CHANGELOG / Release 说明 → Claude 校对 → 打 tag → GitHub Release
```

## 调度方式

有两种方式，按任务选择：

| 方式 | 怎么做 | 适用 |
|---|---|---|
| **A. Claude 调度** | Claude 在命令行调用 `codex exec`：审查用 `--sandbox read-only`；写作用 `--sandbox workspace-write -C <worktree>`，由沙箱参数限制 Codex 只能写该 worktree，提示词中也要求它不联网、不提交。交接规则见下文 | GPT 的审查和实现任务（默认） |
| **B. 人类启动** | 人类在对应工具里打开项目，粘贴 `docs/prompts/` 下的提示词，agent 自己按协议认领、提交、提 PR | Gemini（经 Antigravity，见 `docs/prompts/gemini-kickoff.md`）；人类想直接观察时的 Codex（见 `docs/prompts/codex-kickoff.md`） |

**方式 A 的交接规则（Codex 写作时）：**
1. 由 Claude 创建 worktree 并在 Issue 下留言「认领：gpt（由 claude 用 codex exec 调度），worktree …」。这个 worktree 只属于这一次调度
2. `codex exec` 是同步运行的：Codex 进程运行期间，Claude 不读写、不暂存这个 worktree
3. Codex 进程退出后，Claude 才检查改动、提交（记为 `Agent: gpt (dispatched by claude via codex exec)`）、推送、提 PR，并把 Codex 的汇报贴进 PR
4. 审查改为由 Claude 进行；需要修改时，再调度一次 Codex 在同一个 worktree 中修改，重复 2–3

- Gemini CLI 的个人 Google 账号登录已被停用（2026-11），所以 Gemini 目前只能用方式 B。
- **并行：** 只要各自在不同的 `task/<号>` worktree 里，多个 agent 可以同时工作。人类也可以另开 Codex 会话认领独立的 Issue 与 Claude 并行。分配原则：同一时间同一组文件只有一个写入者；有依赖关系的任务不并行。

## 每版本复盘模板（docs/retro/vX.Y.md）

- 本版本每家各做了哪些任务？
- 交叉审查抓到了哪些真问题？漏了哪些？
- 哪类任务分给谁效果最好 / 最差？
- 协作开销（来回次数、返工）是否值得？
- 下个版本的分工调整
