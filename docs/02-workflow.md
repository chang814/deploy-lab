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

1. **一家写，另一家审。** 任何合入 `main` 的 PR 都必须经过「非作者」模型的审查。谁可以按下合并，见下文「合并权限」。
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
  → 作者修改（必要时多轮）
  → 按「合并权限」：Claude 自主合并，或等待人类批准 → Squash 合并
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

## 合并权限

产品负责人决定（2026-11-26）：**降低人类批准合并的频率，由 Claude 自主合并更多 PR，以更多的审查作为交换。**

### 1. 必须由人类批准的 PR（任何一条命中即是）

| 类别 | 例子 |
|---|---|
| 红线相关 | 修改 `PROJECT_RULES.md` 红线；引入第三方素材或依赖（许可证）；任何接触 CS2 文件或进程的代码 |
| 产品方向与范围 | 立项书（`docs/00-charter.md`）；路线图的里程碑、范围或顺序；手感目标与验收指标；产品命名 |
| 发布 | 打 tag、发布 GitHub Release、改版本号 |
| 决定性结论 | 对「能不能用 / 要不要换方案」下结论的报告（例如 spike 报告的最终判定） |
| 流程规则本身 | 本节「合并权限」、`docs/05-shared-folder-protocol.md`、`PROJECT_RULES.md`、三家 agent 的说明文件 |
| 不可撤销或影响外部 | 删除数据、改仓库设置或权限、改 CI 的密钥与权限 |
| 被要求的 | 人类给 PR 或 Issue 打了 `needs-human` 标签；作者或审查者在评论中写明「需要人类决定」 |
| 审查僵持 | 作者与审查者三轮后仍未达成「通过」 |

### 2. Claude 可以自主合并的 PR

不属于上表的 PR，满足对应条件后由 Claude 合并：

| 类型 | 合并前必须满足 |
|---|---|
| **文档类**（只改 `docs/`、提示词、注释、CHANGELOG、README 中的说明性内容） | ① 至少一轮非作者审查，最后一轮结论为「通过」；② CI 通过 |
| **代码类**（`src/`、`tests/`、`tools/`、`data/`、`scenes/`、CI 配置等） | ① 非作者审查**直到某一轮结论为「通过」**：「修改后通过」不算，修改后必须再审一轮确认；② **最新一次提交**的 CI 全部通过；③ 下面「加审」条件命中时，加一次独立审查 |

**加审（代码类）：** 改动涉及 `src/core/`、输入管线、测试入口 `tests/run_all.gd`、CI 配置，或新增/修改超过约 300 行时，在常规审查通过后，**再开一个全新的 Codex 会话**，换一个角度只做一件事：寻找会让测试或 CI「误判通过」的漏洞，以及常规审查没覆盖的边界情况。两个会话都结论为「通过」才能合并。

**不能自审：** 作者不能当自己的审查者。Claude 写的由 GPT 审；GPT 写的（方式 A）由 Claude 审，同时满足加审条件时，加审仍由一个全新的 Codex 会话完成；Gemini 写的由 GPT 审。

### 3. 人类如何保持知情

- Claude 每次自主合并时，在 PR 下留言写明依据（例如「自主合并：代码类，GPT 第 2 轮通过，CI 绿」），并打上 `merged-by:claude` 标签
- Claude 在对话中定期汇总这段时间自主合并了哪些 PR
- 人类可以随时：给任意 PR 或 Issue 打 `needs-human` 标签，收回这一次的自主合并权；或要求回滚某次合并（回滚也走 PR，不强推 `main`）

## 每版本复盘模板（docs/retro/vX.Y.md）

- 本版本每家各做了哪些任务？
- 交叉审查抓到了哪些真问题？漏了哪些？
- 哪类任务分给谁效果最好 / 最差？
- 协作开销（来回次数、返工）是否值得？
- 下个版本的分工调整
