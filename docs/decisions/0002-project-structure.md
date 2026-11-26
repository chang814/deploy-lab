# 0002 · v0.1 工程结构、测试与 CI

- 状态：提议（待 GPT 审查、人类批准）
- 日期：2026-11-26
- 关联：Issue #22；前置决策 [0001 Godot 4](0001-engine-godot4.md)；P0-4 报告 `spikes/raw-input/REPORT.md`

## 背景

Phase 0 的 spike 表明：在已测条件下，Godot 4.7.2 的 `screen_relative` **每轮 X/Y 累计值**与 Windows 原始鼠标计数一致（报告没有证明逐事件一致，见 `spikes/raw-input/REPORT.md`）。v0.1 要开始写正式代码，需要先定下：工程放在哪、目录怎么分、多 agent 怎么并行写而不互相踩、测试和 CI 怎么跑。

已有约束：
- `PROJECT_RULES.md` 约定手感常量放在 `data/`；`GEMINI.md` 约定核心代码在 `src/`、测试在 `tests/`（Gemini 不改这两个目录）
- 地图设计文档约定分区数据在 `data/map/zones/`，分区名已在 `data/map/zone_names.zh-CN.json`
- Godot 的 `res://` 只能访问工程目录以内的文件

## 选项

| 选项 | 优点 | 缺点 |
|---|---|---|
| A. 工程放在 `game/` 子目录 | 文档与工程分离，Godot 只扫描工程目录 | 需要把 `data/` 迁进 `game/` 并更新已有约定，或增加构建时复制步骤；两者都有持续的同步维护成本 |
| **B. 仓库根目录就是 Godot 工程** | `res://data/...` 与现有约定一致；路径最短 | 根目录多出 `project.godot`；需要让 Godot 忽略 `docs/`、`spikes/` 等目录 |
| C. 每个功能一个独立工程 | 隔离彻底 | 共享代码困难，不适合游戏本体；适合 spike 这类一次性验证（现状就是这样） |

## 决定

### 1. 仓库根目录就是 Godot 工程（选项 B）

在不需要被 Godot 扫描的目录里各放一个**空的** `.gdignore` 文件（它是放在目标目录内的标记文件，不是写忽略列表的配置文件）：`docs/`、`tools/`、`.worktrees/`、`.github/`、`spikes/`。

说明：Godot 4.7.2 本身会跳过包含另一份 `project.godot` 的子目录（spike 工程正是如此），`spikes/` 的 `.gdignore` 只是让意图更明确。`.worktrees/` 必须忽略，否则编辑器会扫描到其他任务的整份代码副本。

### 2. 目录结构

```
project.godot
src/
  core/      纯逻辑，不依赖场景节点（继承 RefCounted 或只有 static 函数），全部可单元测试
             例：look_math.gd（从 spike 转正）
  input/     把 Godot 输入事件转换成 core 需要的数据（例：鼠标位移 → 视角增量）
  player/    角色、相机、移动
  weapons/   切枪状态机等（v0.2）
  maps/      灰盒生成器（地图 M1）
  ui/        界面
scenes/      .tscn 场景文件
data/        所有可调参数与数据（JSON），游戏用 res://data/... 读取
  look/      视角参数（从 spike 的 look_defaults.json 转正）
  map/       分区尺寸、分区名
  feel/      手感测量数据（P0-5 / #4 产出）
tests/
  unit/      单元测试，每个 src 文件对应一个 test_*.gd
  run_all.gd 测试入口：自动发现 tests/unit/ 下的测试并汇总结果
tools/       Python 工具（cfg 导入器等，带自己的测试）
docs/  spikes/  .github/
```

### 3. 依赖方向（防止代码缠在一起）

`core` ← `input` ← `player` / `weapons` / `maps` ← `ui` / `scenes`

- `core` 不引用任何其他目录，也不引用场景节点，**也不自己读文件**：参数由上层（输入层或装配场景）从 `data/` 读取后以参数传入，这样 core 在测试里可以直接喂数据
- 纯状态机（例如 v0.2 的切枪状态机）放在 `core`；把它接到节点、动画上的适配代码放在 `weapons` 等目录
- 下层不引用上层；横向模块（`player` 与 `weapons`）之间通过信号通信，不直接互相调用
- 手感参数一律从 `data/` 读取，代码里只允许物理常数（如 `CM_PER_INCH`）

这条规则也服务于多 agent 并行：不同 agent 认领不同目录下的 Issue，冲突面最小。

### 4. 命名与代码规范

- 文件名 `snake_case.gd`；需要全局引用的类加 `class_name`（PascalCase），其余用 `preload`
- 沿用 `PROJECT_RULES.md`：静态类型、单位后缀（`_deg`、`_s`、`_m`…）
- **精度规则（P0-4 的教训）**：需要 float64 的累计量用标量 `float` 或 `PackedFloat64Array`，不用 `Vector2`/`Vector3`（它们是 32 位）

### 5. 测试

- 自写一个轻量测试入口 `tests/run_all.gd`（沿用 spike 的 `extends SceneTree` 写法），暂不引入第三方测试框架；以后测试量大了再评估 GUT 等框架（需检查许可证）
- 测试文件统一接口：每个 `tests/unit/test_*.gd` 提供 `func run() -> Dictionary`（返回通过数、失败数、失败信息），**不自己调用 `quit()`**；spike 的测试转正时按此接口改写
- 运行：`godot --headless --path . -s res://tests/run_all.gd`。以下任一情况都算失败、退出码非 0：有断言失败、**一个测试都没发现**、某个测试文件加载失败、整体超时
- Python 工具用标准库 `unittest`

**平台边界：**
- 纯逻辑测试（`src/core`、比对脚本等）与平台无关，在 Linux CI 上运行
- Windows 专用的代码（例如 Raw Input 计数器）的测试用 `unittest.skipUnless(sys.platform == "win32")` 标记，并在 CI 的 Windows 任务里运行
- 真实鼠标、独占全屏、显示缩放、回报率等只能**实机验收**（#21），headless 测试通过不能替代

### 6. CI（GitHub Actions）

每个 PR 和推送到 `main` 时自动运行：
1. **Linux 任务**：下载 Godot 4.7.2 官方 Linux 版（版本号写在工作流里固定，升级引擎时单独提 PR）；执行 `godot --headless --path . --import`，再运行 `tests/run_all.gd`；运行与平台无关的 Python 测试；检查 `CHANGELOG.md` 没有残留的合并冲突标记
2. **Windows 任务**：运行 Windows 专用的 Python 测试

CI 通过是合并的必要条件之一（与交叉审查、人类批准并列）。下载地址、缓存方式在实现 CI 的 PR 中确认。

### 7. 数据文件的导出

`data/` 下的 JSON 不是 Godot 资源，导出时默认**不会**被打包，编辑器和测试里一切正常、成品却会缺参数。因此：
- 第一次创建导出预设时，在「资源 › 非资源文件筛选」中加入 `*.json`，并把 `tests/*` 加入排除
- `export_presets.cfg` 不含密钥时纳入版本管理（届时从 `.gitignore` 中移除），保证每个人和 CI 的导出设置一致
- 发布检查清单增加一项：在导出后的成品中确认能读到 `data/` 下的参数（例如启动时校验并在缺失时报错）

### 8. spike 代码转正

spike 本身保留在 `spikes/raw-input/` 作为历史证据，不再修改。转正时**复制**需要的部分到正式目录，并按上面的规则调整：
- `look_math.gd` → `src/core/look_math.gd`；参数文件 → `data/look/defaults.json`
- 对应测试 → `tests/unit/test_look_math.gd`
- `guide_state.gd`、比对工具属于测试设施，不进入游戏代码

## 与其他文档的关系

- 地图设计文档 §4.2 暂定的 `game/maps/practice/` 由本决定替代：灰盒生成器放在 `src/maps/`，场景放在 `scenes/`，分区数据仍在 `data/map/`

## 后果

- v0.1 的第一个 PR 是「工程骨架 + 测试入口 + CI」，之后的功能 PR 都在这个骨架上进行
- 根目录多了 `project.godot` 和 `.godot/`（后者已在 `.gitignore` 中）
- 打开编辑器时会生成 `.uid` 等文件，按 Godot 建议提交到仓库
- 如果以后需要 GDExtension（见 P0-4 报告的未覆盖项与 #21），放在 `addons/`，并新写一份决策记录
