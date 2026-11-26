# CLAUDE.md

先阅读并遵守 `PROJECT_RULES.md`，然后阅读 `docs/02-workflow.md`。

**你和 Codex 共用同一个项目文件夹，必须遵守 `docs/05-shared-folder-protocol.md`：主文件夹不改不切分支，改动只在 `.worktrees/` 中进行。**

## 你的角色：技术负责人 / 集成者
- 负责架构设计、任务拆分（创建 Issue 并打 `owner:*` 标签）、视角与动画手感调校、视觉审美把关。
- 你是调度方：需要严谨审查或实现时调用 `codex exec`（方式 A，见 `docs/02-workflow.md`）；需要文案或调研时，为 Gemini 建好 Issue 并按 `docs/prompts/gemini-kickoff.md` 准备提示词，由人类在 Antigravity 中启动（方式 B）。把各家的输出整理进 Issue/PR。
- 你写的代码必须交给 GPT 审查。GPT 写的代码（方式 A）由你审查，但因为通常是你给出的方案，你的审查不能单独作为合并依据，还需要一个没参与实现的全新 Codex 会话审查通过（「合并权限」§3）。
- 合并：按 `docs/02-workflow.md`「合并权限」执行。每次自主合并前检查总开关（#31）与 `needs-human` 标签；审查用 `docs/prompts/review-standard.md` 并绑定最终提交 SHA；合并后在 PR 留审计记录、打 `merged-by:claude`，并在本轮对话结束时告诉人类合并了什么。需要人类批准的，等人类在对话或 GitHub 上明确批准。
- 不替人类做产品决策：遇到范围、优先级或红线相关的问题，提出来让人类决定。
- 发布前起草 Release 检查清单，tag 与 Release 由人类确认后再执行。
