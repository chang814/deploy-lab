# 共享文件夹协作协议（Claude ⇄ Codex）

项目主文件夹：`D:\桌面\deploy-lab`。Claude Code 和 Codex 都在这台电脑上、对着同一个文件夹工作。
两个 agent 同时在一个文件夹里切分支、改文件会互相覆盖，所以遵守下面的规则。

## 1. 主文件夹只读，改动都在 worktree 里做

- 主文件夹**始终停在 `main` 分支**，用来阅读和运行。任何 agent 都不在主文件夹里直接改文件或切分支。
- 每个任务在自己的 worktree 里做（worktree = 同一个仓库的另一个工作目录，有自己的分支和暂存区）。

**新任务：**

```powershell
git fetch origin
git worktree add .worktrees/<分支名> -b <分支名> origin/main
Set-Location .worktrees/<分支名>
```

**恢复已有分支的任务：**

```powershell
git fetch origin
git worktree list                                  # 先确认这个分支没有被其他 worktree 占用
git worktree add .worktrees/<分支名> <分支名>        # 本地已有该分支时
Set-Location .worktrees/<分支名>
```

- **`Set-Location` 之后的所有编辑、测试、提交、推送、提 PR，都必须在该 worktree 目录里执行。** 每次执行写操作前用 `git rev-parse --show-toplevel` 确认自己所在的目录。
- 禁止使用 `git worktree add -B`、`--force` 或 `git branch -f` 绕过冲突保护；遇到冲突就停下来报告。
- `.worktrees/` 已在 `.gitignore` 中，不会被提交。分支名含 `/` 会形成多层目录，这是正常的。
- 任务合并后由作者清理：`git worktree remove .worktrees/<分支名>`。

## 2. 一个任务只有一个写入者

**唯一负责人：** Issue 上的 `owner:*` 标签决定谁是负责人，只有负责人可以认领和写入。

**认领前检查（任何一项不满足就停下，告诉人类）：**
1. Issue 下没有其他人的有效认领留言
2. `git worktree list` 中没有该任务的 worktree
3. `git branch -a` 中没有该任务的分支（有的话按「恢复」流程，并先确认上一个会话已结束）

**认领：** 在 Issue 下留言 `认领：<agent>，分支 <分支名>，worktree .worktrees/<分支名>`。

**一个 worktree 同一时间只能有一个会话。** 新会话要接手已有 worktree 前，必须先由人类确认之前的会话已经结束。

**交接：** 负责人留言 `交接给 <agent>`，人类确认并修改 `owner:*` 标签后，新负责人才能写入。

**审查只读：** 审查者不改作者的 worktree。需要跑测试时，在自己的临时 worktree 中检出 PR 分支运行（`git worktree add .worktrees/review-<PR号> --detach origin/<分支名>`），用完删除。意见写进 PR 评论。

## 3. 交接都留在 GitHub 上

| 场景 | 写在哪里 |
|---|---|
| 认领任务、进度、卡点 | Issue 评论 |
| 审查意见 | PR 评论（按 `AGENTS.md` 中的审查格式） |
| 需要人类决定的问题 | Issue 评论，同时在对话中告诉人类 |

聊天窗口里的内容对另一个 agent 不可见。**没写到 GitHub 上的，就等于没交接。**

## 4. 常用命令

```powershell
gh issue list --label owner:gpt          # 查看分给自己的任务
gh issue view <号> --comments            # 查看任务和认领情况
gh issue comment <号> --body "..."      # 留言
gh pr create --fill --base main          # 提 PR（在 worktree 中执行）
gh pr diff <号>                          # 审查时查看改动
gh pr review <号> --comment --body "..." # 提交审查意见
```

## 5. 同步与冲突

- 发现主文件夹不在 `main`，或有未提交的改动：**停下**，告诉人类，不要自行清理。
- 两个任务需要改同一个文件：先合并一个，另一个在自己的 worktree 中执行：

```powershell
git fetch origin
git rebase origin/main
```

  一定要先 `fetch`，再变基到 `origin/main`（本地 `main` 可能是旧的）。
- 主文件夹由人类或 Claude 在 PR 合并后更新：`git pull --ff-only`。
