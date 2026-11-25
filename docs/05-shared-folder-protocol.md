# 共享文件夹协作协议（Claude ⇄ Codex）

项目主文件夹：`D:\桌面\deploy-lab`。Claude Code 和 Codex 都在这台电脑上、对着同一个文件夹工作。
两个 agent 同时在一个文件夹里切分支、改文件会互相覆盖，所以遵守下面的规则。

## 1. 主文件夹只读，改动都在 worktree 里做

- 主文件夹**始终停在 `main` 分支**，用来阅读、审查、运行。任何 agent 都不在主文件夹里直接改文件或切分支。
- 每个任务在自己的 worktree 里做（worktree = 同一个仓库的另一个工作目录，有自己的分支）：

```powershell
git fetch origin
git worktree add .worktrees/<分支名> -b <分支名> origin/main
```

- `.worktrees/` 已在 `.gitignore` 中，不会被提交。
- 任务合并后清理：`git worktree remove .worktrees/<分支名>`。

## 2. 一个任务只有一个写入者

- 动手前先在对应 Issue 下留言认领：`认领：<agent>，分支 <分支名>`。
- 审查别人的任务时**只读**：可以读文件、运行测试，不改对方的 worktree；意见写进 PR 评论。
- 作者根据意见在自己的 worktree 里修改。

## 3. 交接都留在 GitHub 上

| 场景 | 写在哪里 |
|---|---|
| 认领任务、进度、卡点 | Issue 评论 |
| 审查意见 | PR 评论（按 `AGENTS.md` 中的审查格式） |
| 需要人类决定的问题 | Issue 评论，并标注 `@` 项目所有者 |

聊天窗口里的内容对另一个 agent 不可见。**没写到 GitHub 上的，就等于没交接。**

## 4. 常用命令

```powershell
gh issue list --label owner:gpt          # 查看分给自己的任务
gh issue comment <号> --body "..."      # 留言
gh pr create --fill --base main          # 提 PR（在 worktree 中执行）
gh pr diff <号>                          # 审查时查看改动
gh pr review <号> --comment --body "..." # 提交审查意见
```

## 5. 冲突处理

- 发现主文件夹不在 `main`，或有未提交的改动：**停下**，在对话中告诉人类，不要自行清理。
- 两个任务需要改同一个文件：先合并一个，另一个再从最新的 `main` 变基。
