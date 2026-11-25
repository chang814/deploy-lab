# 共享文件夹协作协议（Claude ⇄ Codex）

项目主文件夹：`D:\桌面\mcs`。Claude Code 和 Codex 都在这台电脑上、对着同一个文件夹工作。
两个 agent 同时在一个文件夹里切分支、改文件会互相覆盖，所以遵守下面的规则。

## 1. 主文件夹只读，改动都在 worktree 里做

- 主文件夹**始终停在 `main` 分支**，用来阅读和运行。任何 agent 都不在主文件夹里直接改文件或切分支。
- 每个任务在自己的 worktree 里做（worktree = 同一个仓库的另一个工作目录，有自己的分支和暂存区）。

**分支名固定为 `task/<Issue号>`**（例：Issue #2 → `task/2`，worktree 在 `.worktrees/task/2`）。名字由 Issue 号唯一决定，这是第 2 节「锁」的基础。

**新任务：**

```powershell
git fetch origin
git worktree add .worktrees/task/<号> -b task/<号> origin/main
Set-Location .worktrees/task/<号>
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
- 任务合并后由作者清理，**先回到主文件夹再删除**：
  ```powershell
  Set-Location D:\桌面\mcs
  git worktree remove .worktrees/task/<号>
  ```

## 2. 一个任务只有一个写入者

**唯一负责人：** Issue 上的 `owner:*` 标签决定谁是负责人，只有负责人可以认领和写入。

**锁 = 成功创建 `task/<号>` 分支。** `git worktree add ... -b task/<号>` 是原子操作：分支已存在或路径已被占用时，第二个执行者一定失败。因此：
1. 先 `gh issue view <号> --comments` 确认没有有效认领，再执行第 1 节「新任务」命令
2. **命令成功 = 认领成功**，随后在 Issue 下留言 `认领：<agent>，会话 <启动时间>，worktree .worktrees/task/<号>`
3. **命令失败（分支或路径已存在）= 别人已持有锁**，立即停下告诉人类，不得改名重试、不得换分支名绕过

远端的锁：若 `origin/task/<号>` 已存在而本地没有，同样视为已被认领，停下询问人类。

**人类侧规则：** 同一个 agent 同一时间只开一个会话处理同一个 Issue。

**一个 worktree 同一时间只能有一个会话。** 新会话要接手已有 worktree 前，必须先由人类确认之前的会话已经结束。

**交接：** 负责人留言 `交接给 <agent>`，人类确认并修改 `owner:*` 标签后，新负责人才能写入。

**方式 A 的例外（Claude 调度 Codex，见 `docs/02-workflow.md`）：** 对 `owner:gpt` 的 Issue，Claude 可以作为 GPT 的**代理**来认领、提交和推送，此时不需要人类确认交接，前提是：
- 认领留言写明「认领：gpt（由 claude 用 codex exec 调度）」，表示负责人仍然是 GPT，Claude 只是执行人
- Codex 只通过 Claude 发起的 `codex exec` 写入这个 worktree；`codex exec` 运行期间 Claude 不碰这个 worktree，进程退出后 Claude 才提交
- 同一个 Issue 不得同时有人类另开的 Codex 会话（方式 B）在写；如果人类想改用方式 B 接手，先按上面的「交接」规则走

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
  - **例外仅适用于：主文件夹仍在 `main` 分支，只是有未提交改动，且人类已确认这些改动属于预期**（例如人类在主文件夹打开 Godot 编辑器或运行工程做测试，编辑器自动改写了文件）。此时 agent 可以**保持主文件夹原样**，继续在自己的 worktree 中工作：新 worktree 基于 `origin/main`，不受主文件夹未提交改动的影响。主文件夹不在 `main` 时没有例外，必须停下。
  - 任何 agent 都不得清理、提交或修改主文件夹里的这些改动。保留还是丢弃由人类决定。
  - 如果人类决定把这类改动纳入项目（例如 Godot 编辑器对 `project.godot` 的正常整理），由负责相关 Issue 的 agent 在**自己认领的 worktree 中复现同样的改动**，再走正常的 PR 和审查流程；不得直接在主文件夹提交。
  - 主文件夹有未提交改动时，`git pull --ff-only` 可能失败。此时由人类处理，agent 不要强行覆盖。
- 两个任务需要改同一个文件：先合并一个，另一个在自己的 worktree 中执行：

```powershell
git fetch origin
git rebase origin/main
```

  一定要先 `fetch`，再变基到 `origin/main`（本地 `main` 可能是旧的）。
- 主文件夹由人类或 Claude 在 PR 合并后更新：`git pull --ff-only`。
