# 同类项目与相关技术方案调研（P0-2）

- 关联任务：[Issue #1](https://github.com/chang814/mcs/issues/1)
- 调研日期：2026-11-26（所有仓库最近更新时间与源码行号均于当日通过 GitHub REST API / Codeberg API 对默认分支最新提交实测核对）
- 内部对照基准：[`PROJECT_RULES.md`](../../PROJECT_RULES.md)、[`docs/00-charter.md`](../00-charter.md)、[`docs/04-sensitivity-spec.md`](../04-sensitivity-spec.md)、[`spikes/raw-input/REPORT.md`](../../spikes/raw-input/REPORT.md)

> **红线与收录原则声明：**
> 1. 遵循 [`PROJECT_RULES.md`](../../PROJECT_RULES.md) 红线 1，本文**不收录任何包含 Valve 提取资产（模型、动画、音效、贴图）或复刻商业游戏现有地图的项目作为可借鉴对象**。社区中存在部分直接导入商业战术射击游戏真实地图或提取武器资产的开源练枪仓库（例如基于商业游戏地图几何体构建的浏览器练枪项目），此类项目触及本项目版权与原创红线，仅在此提示风险，一律不纳入借鉴范围。
> 2. 遵循 MIT 许可证合规要求，凡采用 `GPL` 系列或带附加限制条款许可证的对象，均在「许可证」栏明确标出兼容性结论，**只参考公开算法思路或架构设计，绝不拷贝任何代码**。
> 3. 未经一手源码或当前客户端实测确认的事项统一标注为**「未确认」**。

---

## A. 开源的 FPS 练枪 / 瞄准训练工具（4 个对象）

### A1. LibreAim
- **名称：** LibreAim
- **链接：**
  - 主仓库（Codeberg，项目已迁移至此）：https://codeberg.org/Nokorpo/LibreAim
  - 旧镜像（GitHub）：https://github.com/Nokorpo/LibreAim
- **技术栈：** Godot 4.4（GDScript，Forward+ 渲染管线；见 [`project.godot`](https://github.com/Nokorpo/LibreAim/blob/main/project.godot) 中 `config/features=PackedStringArray("4.4", "Forward Plus")`）
- **许可证：** `GPL-3.0`（GNU General Public License v3.0，见 [`LICENSE`](https://github.com/Nokorpo/LibreAim/blob/main/LICENSE)）——**与本项目 MIT 不兼容，只能参考思路不能拷代码**。
- **最近更新时间：** Codeberg 主仓库 `2026-11-03`（通过 Codeberg API `https://codeberg.org/api/v1/repos/Nokorpo/LibreAim` 核实 `updated_at`）；GitHub 旧仓库最近推送 `2025-08-27`（通过 GitHub API `repos/Nokorpo/LibreAim` 核实 `pushed_at`）。
- **可借鉴点：**
  - **外部配置驱动的场景（Scenario）结构：** 将追踪（tracking）、横移（horizontal）、随机点射（random）等训练科目拆分为独立的 `.cfg` 数据文件（见 [`assets/default_data/custom_resources/scenarios/`](https://github.com/Nokorpo/LibreAim/tree/main/assets/default_data/custom_resources/scenarios)），支持用户自定义扩展，思路契合 `mcs` 数据驱动靶场与成绩统计（G5）。
  - **内置完赛结算与趋势图：** 包含结算面板与历史得分折线图模块（[`end_game_ui.gd`](https://github.com/Nokorpo/LibreAim/blob/main/scenes/game_world/end_game_ui/end_game_ui.gd)、[`progress_chart.gd`](https://github.com/Nokorpo/LibreAim/blob/main/scenes/game_world/end_game_ui/progress_chart.gd)），功能体量轻巧。
  - **默认关闭垂直同步：** [`project.godot`](https://github.com/Nokorpo/LibreAim/blob/main/project.godot) 默认设置 `window/vsync/vsync_mode=0`，降低练枪输入延迟。
- **不适用之处：**
  - **许可证不兼容：** `GPL-3.0` 具有传染性，任何源码与资源均不可拷入 `mcs`。
  - **FOV 轴向语义错误（关键缺陷）：** [`settings.cfg`](https://github.com/Nokorpo/LibreAim/blob/main/assets/default_data/data/settings.cfg) 默认写入 `fov=103`（模仿 Valorant 16:9 水平 FOV），但 [`player_manager.gd`](https://github.com/Nokorpo/LibreAim/blob/main/scenes/game_world/player/player_manager.gd) 第 24 行直接执行 `_camera.fov = SaveManager.settings.get_data("video", "fov")`。由于 Godot 4 `Camera3D` 默认 `keep_aspect = KEEP_HEIGHT`（`fov` 属性表示**垂直**视野角），直接赋值 `103` 会把垂直 FOV 设为 103°，导致 16:9 下实际水平 FOV 高达约 `130.36°`，画面严重广角畸变。
  - **视角旋转实现不符合 `mcs` 精度规范：** [`player_manager.gd`](https://github.com/Nokorpo/LibreAim/blob/main/scenes/game_world/player/player_manager.gd) 第 28–31 行使用 `event.relative` 直接调用 `rotate_y` / `_camera.rotate_x` 修改 32 位浮点渲染变换，未用 `float64` 独立累积逻辑角度；且 [`settings_controls.gd`](https://github.com/Nokorpo/LibreAim/blob/main/scenes/main_menu/settings/settings_controls.gd) 第 4–9 行将 `"Counter Strike 2": 0.022` 写死为单一乘数，不支持独立 `m_yaw` / `m_pitch` 或开镜灵敏度。
  - **无武器 viewmodel 与切枪/检视系统：** 纯射线打靶（`RayCast3D`），不含第一人称武器模型或切换状态机。

### A2. OpenAimTrainer
- **名称：** OpenAimTrainer（`erkkon/OpenAimTrainer`）
- **链接：** https://github.com/erkkon/OpenAimTrainer
- **技术栈：** Godot 4.5（GDScript，Forward+；见 [`project.godot`](https://github.com/erkkon/OpenAimTrainer/blob/main/project.godot) 中 `config/features=PackedStringArray("4.5", "Forward Plus")`）
- **许可证：** `Apache-2.0`（Apache License 2.0，见 [`LICENSE`](https://github.com/erkkon/OpenAimTrainer/blob/main/LICENSE)；与 MIT 兼容，但合并分发时须保留 Apache-2.0 声明与 NOTICE 要求）。
- **最近更新时间：** `2025-12-21`（GitHub API `repos/erkkon/OpenAimTrainer` 的 `pushed_at`）。
- **可借鉴点：**
  - **参数化十字准星与导入导出界面：** 提供准星内线、外框、中心点尺寸与颜色的实时预览和持久化存储（[`Crosshair.gd`](https://github.com/erkkon/OpenAimTrainer/blob/main/scripts/ui/Crosshair.gd)、[`Options.gd`](https://github.com/erkkon/OpenAimTrainer/blob/main/scripts/ui/Options.gd)），适合 `mcs` 设置界面参考交互结构。
  - **主菜单模式动态预览：** 使用独立预览组件展示训练模式（[`ModePreview3D.gd`](https://github.com/erkkon/OpenAimTrainer/blob/main/scripts/ui/ModePreview3D.gd)）。
- **不适用之处：**
  - **灵敏度换算含未说明的经验常数：** 在 [`CharacterBody3D.gd`](https://github.com/erkkon/OpenAimTrainer/blob/main/scripts/characters/CharacterBody3D.gd) 第 10 行写有硬编码值 `conversion_sensitivity = 0.0707589285714285`，且对 Web 导出额外乘以 `0.67857142857142857143`（第 50–51 行），无数学推导说明，不符合 `mcs` G1 零误差计数级对齐要求。
  - **架构耦合与线程用法不规范：** 在角色脚本中手动开启常驻 `Thread` 处理开火逻辑（[`CharacterBody3D.gd`](https://github.com/erkkon/OpenAimTrainer/blob/main/scripts/characters/CharacterBody3D.gd) 第 37–67 行），且缺乏 viewmodel 和切枪机制。

### A3. Redblock Online (`redblock-client`)
- **名称：** Redblock Online Client（`Redblock-Online/redblock-client`）
- **链接：** https://github.com/Redblock-Online/redblock-client
- **技术栈：** TypeScript、Three.js、Next.js（浏览器端 WebGL 3D 渲染；见 [`app/`](https://github.com/Redblock-Online/redblock-client/tree/master/app) 与 [`documentation/`](https://github.com/Redblock-Online/redblock-client/tree/master/documentation)）
- **许可证：** `Redblock Community License (RCL) v1.0`（见 [`LICENSE.md`](https://github.com/Redblock-Online/redblock-client/blob/master/LICENSE.md)）——虽声明基于 MIT 修改，但附加了商标限制与**禁止运营相同功能公共托管服务的条款（Section B）**，不属于标准无附加限制的开源许可证；**仅参考公开文档思路，不拷贝代码**。
- **最近更新时间：** `2026-10-31`（GitHub API `repos/Redblock-Online/redblock-client` 的 `pushed_at`）。
- **可借鉴点：**
  - **清晰的世界相机 + 武器相机双 FOV 架构文档：** 其 [`docs/DUAL_FOV_SYSTEM.md`](https://github.com/Redblock-Online/redblock-client/blob/master/docs/DUAL_FOV_SYSTEM.md) 详细记录了为什么要将世界相机（可调 FOV，远裁剪面 1000）与第一人称武器相机（独立固定较低 FOV、更近的近裁剪面 0.05、独立渲染通道防穿模）拆开并在每帧同步位姿，与 [`docs/04-sensitivity-spec.md`](../04-sensitivity-spec.md) 第 2 节「Viewmodel 使用独立相机」完全同构。
  - **靶标生成器数据抽象：** [`docs/TARGET_GENERATION_SYSTEM.md`](https://github.com/Redblock-Online/redblock-client/blob/master/docs/TARGET_GENERATION_SYSTEM.md) 将靶位生成规则（区域、数量、重生策略）与地图几何体解耦，可为 `mcs` 原创练习地图 Z1–Z6 的靶机生成器提供设计参考。
- **不适用之处：**
  - **技术栈与运行环境不同：** 基于浏览器 Pointer Lock API 与 Three.js，受浏览器事件调度与合成器延迟制约，不适合 `mcs` 的原生桌面高帧率低延迟需求。
  - **自定义许可证附加条款：** RCL v1.0 含公共服务限制，不可直接复用源码。

### A4. TRAINGÜN (`trainGun`)
- **名称：** TRAINGÜN（`lby-1/trainGun`）
- **链接：** https://github.com/lby-1/trainGun
- **技术栈：** 原生 JavaScript（ES Modules）+ WebGL / HTML5 Canvas（零外部运行时依赖；见 [`README.md`](https://github.com/lby-1/trainGun/blob/main/README.md) 与 [`js/`](https://github.com/lby-1/trainGun/tree/main/js)）
- **许可证：** `MIT`（MIT License，见 [`LICENSE`](https://github.com/lby-1/trainGun/blob/main/LICENSE)）。
- **最近更新时间：** `2026-02-11`（GitHub API `repos/lby-1/trainGun` 的 `pushed_at`）。
- **可借鉴点：**
  - **面向玩家的六类训练科目划分与训练编排（Routine）：** 内置追踪（[`tracking.js`](https://github.com/lby-1/trainGun/blob/main/js/modes/tracking.js)）、甩枪（[`flicking.js`](https://github.com/lby-1/trainGun/blob/main/js/modes/flicking.js)）、多目标切换（[`switching.js`](https://github.com/lby-1/trainGun/blob/main/js/modes/switching.js)）、反应（[`reflex.js`](https://github.com/lby-1/trainGun/blob/main/js/modes/reflex.js)）、人形爆头/补枪（[`humanoid.js`](https://github.com/lby-1/trainGun/blob/main/js/modes/humanoid.js)）及训练计划编排（[`routine.js`](https://github.com/lby-1/trainGun/blob/main/js/routine.js)）和统计面板（[`stats.js`](https://github.com/lby-1/trainGun/blob/main/js/stats.js)），产品层面的科目组织直观简洁。
- **不适用之处：**
  - **灵敏度映射存在中间值四舍五入与近似简化：** [`js/sensitivity.js`](https://github.com/lby-1/trainGun/blob/main/js/sensitivity.js) 第 15–22 行虽正确使用 CS2 系数 `0.022` 计算 `cm360 = (2.54 * 360) / (dpi * sensitivity * 0.022)`，但在第 91 行先对 `cm360` 做了两位小数四舍五入（`Math.round(cm360 * 100) / 100`），随后将鼠标 `movementX` 线性映射为画布位移而非严格的三维透视相机角度旋转，违背 [`docs/04-sensitivity-spec.md`](../04-sensitivity-spec.md) 第 1 节「不得先舍入中间值、直接用 count × 每 count 角度驱动旋转」的要求。

---

## B. Godot 4 的第一人称控制器 / 武器 viewmodel / 切枪实现（4 个对象）

### B1. `majikayogames/SimpleFPSController`
- **名称：** SimpleFPSController（Majikayo Games）
- **链接：** https://github.com/majikayogames/SimpleFPSController
- **技术栈：** Godot 4.3（GDScript + Godot Spatial Shader；见 [`project.godot`](https://github.com/majikayogames/SimpleFPSController/blob/main/project.godot) 中 `config/features=PackedStringArray("4.3", "Forward Plus")`）
- **许可证：** `CC0-1.0`（Creative Commons Zero v1.0 Universal，见 [`LICENSE`](https://github.com/majikayogames/SimpleFPSController/blob/main/LICENSE)，完全公有领域，与 MIT 完全兼容；若采用随附素材仍须按 [`PROJECT_RULES.md`](../../PROJECT_RULES.md) 登记在 `assets/CREDITS.md`）。
- **最近更新时间：** `2026-02-07`（GitHub API `repos/majikayogames/SimpleFPSController` 的 `pushed_at`）。
- **可借鉴点：**
  - **适配 Godot 4.3+ Reverse-Z 的单相机 Viewmodel 防穿模与独立 FOV 着色器：** [`weapon_clip_and_fov_shader.gdshader`](https://github.com/majikayogames/SimpleFPSController/blob/main/FPSController/weapon_manager/weapon_clip_and_fov_shader.gdshader) 第 28–42 行在顶点着色器中用 `uniform float viewmodel_fov` 重写 `PROJECTION_MATRIX[1][1]` 与 `PROJECTION_MATRIX[0][0]`，并通过 `POSITION.z = mix(POSITION.z, POSITION.w, 0.9)`（第 42 行）适配 Godot 4.3 引入的反向深度缓冲（Reverse-Z），无需额外 `SubViewport` 开销即可防止武器穿墙并独立控制武器视野角，同时在 [`weapon_manager.gd`](https://github.com/majikayogames/SimpleFPSController/blob/main/FPSController/weapon_manager/weapon_manager.gd) 第 71 行自动关闭 viewmodel 阴影投射避免自阴影伪影。
  - **动画被打断时的取消回调机制（`cancelled_callback`）：** [`weapon_manager.gd`](https://github.com/majikayogames/SimpleFPSController/blob/main/FPSController/weapon_manager/weapon_manager.gd) 第 125–140 行在 `play_anim(name, finished_callback, cancelled_callback)` 中显式跟踪上一个未播完的动画并在新动作抢占时触发 `cancelled_callback`，包含近战刀类资源扩展（[`melee_weapon_resource.gd`](https://github.com/majikayogames/SimpleFPSController/blob/main/FPSController/weapon_manager/melee_weapon_resource.gd)），对 `mcs` 实现「检视随时可被开火/切枪打断」很有参考价值。
- **不适用之处：**
  - **着色器重写材质具有侵入性：** `apply_clip_and_fov_shader_to_view_model`（[`weapon_manager.gd`](https://github.com/majikayogames/SimpleFPSController/blob/main/FPSController/weapon_manager/weapon_manager.gd) 第 63–89 行）在运行时遍历网格把 `BaseMaterial3D` 替换为自定义 `ShaderMaterial`，若后续刀模型使用复杂自定义表面着色器需额外维护两套材质；相比之下独立 `SubViewport` 方案对材质完全透明。
  - **视角输入与角度范围不符合 CS2 规格：** [`FPSController.gd`](https://github.com/majikayogames/SimpleFPSController/blob/main/FPSController/FPSController.gd) 第 92–98 行直接使用弧度乘数 `look_sensitivity = 0.006` 乘 `event.relative` 并限制在 `±90°`（而非 `±89°` 暂定值），且着色器中 `viewmodel_fov` 按垂直角 `1.0 / tan(0.5 * viewmodel_fov)` 计算，未验证是否符合 CS2 的 4:3 基准投影规则。

### B2. `Jeh3no/Godot-simple-FPS-weapon-system`
- **名称：** Simple FPS Weapon System（Jeheno）
- **链接：** https://github.com/Jeh3no/Godot-simple-FPS-weapon-system
- **技术栈：** Godot 4（GDScript 插件化结构 `addons/JehenoSimpleFPSWeaponSystem/`；见仓库目录树与 [`README.md`](https://github.com/Jeh3no/Godot-simple-FPS-weapon-system/blob/main/README.md)）
- **许可证：** `MIT`（MIT License，见 [`LICENSE`](https://github.com/Jeh3no/Godot-simple-FPS-weapon-system/blob/main/LICENSE)）。
- **最近更新时间：** `2026-11-02`（GitHub API `repos/Jeh3no/Godot-simple-FPS-weapon-system` 的 `pushed_at`）。
- **可借鉴点：**
  - **职责清晰的武器子系统拆分：** 将武器管理（[`weapon_manager_script.gd`](https://github.com/Jeh3no/Godot-simple-FPS-weapon-system/blob/main/addons/JehenoSimpleFPSWeaponSystem/Weapons/Scripts/weapon_manager_script.gd)）、射击、换弹、弹药、程序化动画（[`animation_manager_script.gd`](https://github.com/Jeh3no/Godot-simple-FPS-weapon-system/blob/main/addons/JehenoSimpleFPSWeaponSystem/Weapons/Scripts/animation_manager_script.gd)）与靶场标靶（[`shooting_range_target_script.gd`](https://github.com/Jeh3no/Godot-simple-FPS-weapon-system/blob/main/addons/JehenoSimpleFPSWeaponSystem/Targets/Scripts/shooting_range_target_script.gd)）解耦为独立组件，外加 `ViewportCamera` 双相机同步（[`viewport_camera_script.gd`](https://github.com/Jeh3no/Godot-simple-FPS-weapon-system/blob/main/addons/JehenoSimpleFPSWeaponSystem/Weapons/Scripts/Camera/viewport_camera_script.gd)）。
  - **双阶段收枪/拔枪流程拆分：** `exit_weapon` 与 `enter_weapon` 分离收起当前武器与拔出目标武器两个阶段（[`weapon_manager_script.gd`](https://github.com/Jeh3no/Godot-simple-FPS-weapon-system/blob/main/addons/JehenoSimpleFPSWeaponSystem/Weapons/Scripts/weapon_manager_script.gd) 第 62–96 行）。
- **不适用之处：**
  - **切枪计时与快切打断存在关键缺陷（对 `mcs` G2 尤为重要）：** `exit_weapon` 第 65 行直接将 `can_change_weapons = false` 锁死，并用 `await get_tree().create_timer(current_weapon.resources.unequip_time).timeout`（第 72 行）串联协程等待收枪结束！这意味着**在切枪动画播放期间玩家无法再次按 Q 快切或滚轮切回上一把武器**（而 CS2 允许在切枪任意时刻立刻切换目标槽位并重置拔出计时）；同时 `SceneTreeTimer` 受帧间隔抖动影响，难以保证精确的确定性状态机测试。`mcs` 必须用纯数值时钟推进的可重入切枪状态机替代 `await` 协程。
  - **Viewport 相机在 `_physics_process` 中同步：** [`viewport_camera_script.gd`](https://github.com/Jeh3no/Godot-simple-FPS-weapon-system/blob/main/addons/JehenoSimpleFPSWeaponSystem/Weapons/Scripts/Camera/viewport_camera_script.gd) 第 8–9 行在 `_physics_process` 同步 `global_transform`，当渲染帧率高于物理帧率（如 240Hz 屏幕对 60Hz 物理帧）时会导致 viewmodel 相对世界相机滞后抖动，应在渲染帧（`_process`）或直接作为相机子节点同步。

### B3. `chafmere/Godot4-FPS-Template`
- **名称：** Godot 4 FPS Template（Chafmere）
- **链接：** https://github.com/chafmere/Godot4-FPS-Template
- **技术栈：** Godot 4.6（GDScript，Forward+；见 [`project.godot`](https://github.com/chafmere/Godot4-FPS-Template/blob/main/project.godot) 中 `config/features=PackedStringArray("4.6", "Forward Plus")`）
- **许可证：** `MIT`（MIT License，见 [`LICENSE`](https://github.com/chafmere/Godot4-FPS-Template/blob/main/LICENSE)）。
- **最近更新时间：** `2026-02-01`（GitHub API `repos/chafmere/Godot4-FPS-Template` 的 `pushed_at`）。
- **可借鉴点：**
  - **资源化的武器定义（`WeaponResource`）：** [`weapon_resource.gd`](https://github.com/chafmere/Godot4-FPS-Template/blob/main/Player_Controller/scripts/Weapon_State_Machine/weapon_resource.gd) 将武器名称、各类动作动画名（取出、射击、换弹、切换、近战挥击）、弹匣属性与弹道散布配置（[`spray_profile.gd`](https://github.com/chafmere/Godot4-FPS-Template/blob/main/Player_Controller/Spawnable_Objects/SprayProfiles/spray_profile.gd)）集中声明为自定义 `Resource`。
  - **数字键槽位与滚轮切换输入入口：** [`Weapon_State_Machine.gd`](https://github.com/chafmere/Godot4-FPS-Template/blob/main/Player_Controller/scripts/Weapon_State_Machine/Weapon_State_Machine.gd) 第 42–58 行区分数字键直接选槽位与 `WeaponUp`/`WeaponDown` 滚轮切换，并支持 `ShapeCast3D` 近战判定。
- **不适用之处：**
  - **可开火时机耦合在 `AnimationPlayer.animation_finished` 信号上：** [`Weapon_State_Machine.gd`](https://github.com/chafmere/Godot4-FPS-Template/blob/main/Player_Controller/scripts/Weapon_State_Machine/Weapon_State_Machine.gd) 第 30 行依赖动画播放器完成信号驱动状态切换。对于 `mcs` 先用灰盒/占位模型把「切枪可开火时间点误差 ≤ 1 帧@144Hz（≈7 ms）」做对、后续再替换精细美术模型的路线（[`docs/00-charter.md`](../00-charter.md) 第 5 节），**绝对不能让美术动画资源长度反向决定逻辑可开火时刻**，而应由 `data/` 中的秒/毫秒级精确时序表驱动逻辑状态，动画播放速率去适配逻辑时长。

### B4. `ratmarrow/GoldGdt`
- **名称：** GoldGdt（GoldSrc Character Controller for Godot 4）
- **链接：** https://github.com/ratmarrow/GoldGdt
- **技术栈：** Godot 4（GDScript 插件 `addons/GoldGdt/`；见 [`plugin.cfg`](https://github.com/ratmarrow/GoldGdt/blob/main/addons/GoldGdt/plugin.cfg)）
- **许可证：** `MIT`（MIT License，见 [`LICENSE`](https://github.com/ratmarrow/GoldGdt/blob/main/LICENSE)）。
- **最近更新时间：** `2025-06-24`（GitHub API `repos/ratmarrow/GoldGdt` 的 `pushed_at`）。
- **可借鉴点：**
  - **Hammer 单位到米制的数据化角色尺度：** [`PlayerParameters.gd`](https://github.com/ratmarrow/GoldGdt/blob/main/addons/GoldGdt/src/PlayerParameters.gd) 按 `1 Hammer unit = 0.0254 m` 显式注释并导出了移动加速度、地面摩擦、空中加速（airaccelerate）、台阶高度 `STEP_HEIGHT = 0.457 m (18 u)`、站立碰撞盒 `Vector3(0.813, 1.829, 0.813) ([32, 72, 32] u)` 等常量，与 `mcs` 地图设计文档的 0.0254 m 换算基准一致（注：具体 CS2 角色移动参数仍须按 P0-5 实测核对，不可直接照搬 GoldSrc 数值）。
  - **高刷新率物理帧与渲染帧分离插值：** [`GoldGdt_Camera.gd`](https://github.com/ratmarrow/GoldGdt/blob/main/addons/GoldGdt/src/GoldGdt_Camera.gd) 第 19–53 行把相机设为 `top_level`，在 `_physics_process` 记录前后物理帧位置 `t_prev` / `t_curr`，在 `_process` 用 `Engine.get_physics_interpolation_fraction()`（第 44 行）仅对相机平移做线性插值，而**旋转保持每渲染帧即时响应无插值延迟**（第 50 行 `global_rotation = target.global_rotation`），兼顾移动丝滑度与零鼠标旋转延迟。
  - **显式关闭输入聚合：** [`GoldGdt_Controls.gd`](https://github.com/ratmarrow/GoldGdt/blob/main/addons/GoldGdt/src/GoldGdt_Controls.gd) 第 18 行调用 `Input.set_use_accumulated_input(false)`，使每个原始鼠标事件逐次送达 `_input`，这直接关联 [`docs/04-sensitivity-spec.md`](../04-sensitivity-spec.md) 第 4.2 节中「逐事件截断 vs 按帧累计后截断」的实现选择。
- **不适用之处：**
  - **鼠标输入处理存在比例与同帧重复缩放问题：** [`GoldGdt_Controls.gd`](https://github.com/ratmarrow/GoldGdt/blob/main/addons/GoldGdt/src/GoldGdt_Controls.gd) 第 55–67 行在 `_gather_mouse_input` 中将 `event.xformed_by(viewport_transform).relative` 累加到 `mouse_input`（直到 `_process` 才清零），若同一渲染帧内关闭输入聚合后到达多个鼠标事件，前序事件会被重复乘以 `MOUSE_SENSITIVITY * 0.0001`；且其传入 `rotate_object_local` 的单位实为弧度却命名为 `degrees_per_unit = 0.0001`（第 60 行），与 CS2 的 `0.022°/count` 体系不兼容。

---

## C. 灵敏度与 FOV 换算工具或文档（3 个对象 + 规格对照表）

### C1. `KovaaK/SensitivityMatcher`
- **名称：** Sensitivity Matcher（KovaaK）
- **链接：** https://github.com/KovaaK/SensitivityMatcher
- **技术栈：** AutoIt（调用 Win32 `user32.dll` Raw Input 与 `mouse_event` API；见 [`Header.au3`](https://github.com/KovaaK/SensitivityMatcher/blob/master/ReleaseAssets/bin/Header.au3) 与 [`MiscFunctions.au3`](https://github.com/KovaaK/SensitivityMatcher/blob/master/ReleaseAssets/bin/MiscFunctions.au3)）
- **许可证：** `GPL-3.0`（GNU General Public License v3.0，见 [`LICENSE`](https://github.com/KovaaK/SensitivityMatcher/blob/master/LICENSE)）——**与本项目 MIT 不兼容，只能参考思路不能拷代码**。
- **最近更新时间：** `2022-10-27`（GitHub API `repos/KovaaK/SensitivityMatcher` 的 `pushed_at`）。
- **对 CS2 `m_yaw` / FOV / 开镜灵敏度的处理及与 `04-sensitivity-spec.md` 一致性：**
  - **`m_yaw` 与 360° 计数：** 在 [`SensitivityMatcher.au3`](https://github.com/KovaaK/SensitivityMatcher/blob/master/ReleaseAssets/bin/SensitivityMatcher.au3) 第 3 行定义 `Global Const $yawQuake = 0.022`（在 [`MiscFunctions.au3`](https://github.com/KovaaK/SensitivityMatcher/blob/master/ReleaseAssets/bin/MiscFunctions.au3) 第 72 行下拉列表标为 `"Quake/Source"`），用 `Yaw * Sens` 算单计数角度增量、`360 / Increment` 算整圈计数，并维护浮点余量累加器 `$gResidual` 防止单步整数发送截断误差——**未开镜水平旋转数学关系与 [`docs/04-sensitivity-spec.md`](../04-sensitivity-spec.md) 第 1 节完全一致**。
  - **FOV 与开镜灵敏度：** **未处理**。该工具仅针对水平 360° 整圈物理计数校准，不包含 FOV 换算或 `zoom_sensitivity_ratio` 计算。
- **可借鉴点：**
  - 清晰展示了「整数鼠标 count 无法整除 360°（如 `800 DPI, sens 1.0 → 16363.636... counts`）时，多圈循环累积检验微小残差」的验证思路（`$gCycle` 多圈复测）。
- **不适用之处：**
  - **触及进程输入注入红线（严禁对 CS2 使用）：** [`MiscFunctions.au3`](https://github.com/KovaaK/SensitivityMatcher/blob/master/ReleaseAssets/bin/MiscFunctions.au3) 第 84–92 行通过 `DllCall("user32.dll", "none", "mouse_event", ...)` 向目标窗口注入模拟鼠标移动。按 [`PROJECT_RULES.md`](../../PROJECT_RULES.md) 红线 2 与 [`docs/04-sensitivity-spec.md`](../04-sensitivity-spec.md) 第 4.1 节，**严禁向 CS2 注入任何模拟输入**（`mcs` 仅可在自身独立进程或被动读取物理鼠标 Raw Input 的基准工具中做验证）。
  - **许可证为 `GPL-3.0`**，与 MIT 不兼容。

### C2. `DenisSergeevitch/game-sensitivity-coach`
- **名称：** game-sensitivity-coach
- **链接：** https://github.com/DenisSergeevitch/game-sensitivity-coach
- **技术栈：** Python 3.8+（无第三方依赖标准库实现 + 单元测试；见 [`scripts/convert_sensitivity.py`](https://github.com/DenisSergeevitch/game-sensitivity-coach/blob/main/scripts/convert_sensitivity.py)、[`scripts/discover_settings.py`](https://github.com/DenisSergeevitch/game-sensitivity-coach/blob/main/scripts/discover_settings.py)）
- **许可证：** `MIT`（MIT License，见 [`LICENSE`](https://github.com/DenisSergeevitch/game-sensitivity-coach/blob/main/LICENSE)）。
- **最近更新时间：** `2026-09-06`（GitHub API `repos/DenisSergeevitch/game-sensitivity-coach` 的 `pushed_at`）。
- **对 CS2 `m_yaw` / FOV / 开镜灵敏度的处理及与 `04-sensitivity-spec.md` 一致性：**
  - **刻意不硬编码未验证的游戏常数：** [`convert_sensitivity.py`](https://github.com/DenisSergeevitch/game-sensitivity-coach/blob/main/scripts/convert_sensitivity.py) 第 1 行明确声明 `"Convert verified game calibrations; no built-in game constants"`，要求调用方显式传入校准斜率 `slope`（对 CS2 即 `m_yaw = 0.022`）并强制标注证据等级 `evidence: "measured" | "documented" | "assumed"`（第 30–31 行），未实测的先验必须标为 `assumed`——**这一认识论原则与 [`docs/04-sensitivity-spec.md`](../04-sensitivity-spec.md) 严格区分「冻结公式」与「待测量先验」的做法高度一致**。
  - **360° 距离公式：** [`conversion.md`](https://github.com/DenisSergeevitch/game-sensitivity-coach/blob/main/references/conversion.md) 第 10–11 行定义 `g(s) = slope * native_setting + offset`（°/count）、`cm_per_360 = 914.4 / (DPI * g(s))`（其中 `914.4 = 360 × 2.54`），与 `04-sensitivity-spec.md` 第 1 节在 `offset = 0` 时完全等价。
  - **FOV 与开镜（Scoped / ADS）换算：** [`conversion.md`](https://github.com/DenisSergeevitch/game-sensitivity-coach/blob/main/references/conversion.md) 第 22–33 行与 [`convert_sensitivity.py`](https://github.com/DenisSergeevitch/game-sensitivity-coach/blob/main/scripts/convert_sensitivity.py) 第 70–84 行实现了屏幕比例匹配（Monitor Distance）：通用式为 `atan(r * tan(target_FOV/2)) / atan(r * tan(source_FOV/2))`（强制要求使用同一轴的实际渲染 FOV）；当屏幕半径比例 `r = 0`（准星中心微小位移极限，见 `conversion.md` 第 33 行）时退化为 `tan(target_FOV/2) / tan(source_FOV/2)`——**该极限式恰好就是 [`docs/04-sensitivity-spec.md`](../04-sensitivity-spec.md) 第 4.1 节列出的候选二 `K_tan`**。但该工具用于跨游戏计算目标灵敏度，并未验证 CS2 内部 `zoom_sensitivity_ratio` 究竟采用 `K_angle = F_zoom / 90°` 还是 `K_tan`（在 `mcs` 中仍属**待测量**）。
- **可借鉴点：**
  - **只读配置文件发现的安全边界防护：** [`discover_settings.py`](https://github.com/DenisSergeevitch/game-sensitivity-coach/blob/main/scripts/discover_settings.py) 展示了纯文件系统的只读配置扫描规范：使用 `SHGetFolderPathW` 解析重定向用户目录、跳过符号链接/重解析点（第 37 行 `def reparse(path):`）、限制遍历深度与最大文件数，不接触任何游戏进程内存，非常适合 `mcs` 开发 CS2 本地 cfg 只读导入器（G4）时参考安全边界。
  - **显式输出舍入误差与假设清单：** 换算结果同时保留未舍入精确值、目标位数舍入值及 `rounding_gain_error_percent`（[`convert_sensitivity.py`](https://github.com/DenisSergeevitch/game-sensitivity-coach/blob/main/scripts/convert_sensitivity.py) 第 109–111 行）。
- **不适用之处：**
  - 其内置目录提示表（`HINTS`）仅包含 *THE FINALS*、*Battlefield 6*、*Holdfast*，**未内置 Steam `userdata/<id>/730/local/cfg/` 的 CS2 路径与 Valve `.vcfg` / `.cfg` 解析器**（注：公开社区资料普遍指出 CS2 用户灵敏度保存在 `<Steam>/userdata/<id>/730/local/cfg/cs2_user_convars_0_slot0.vcfg`，但当前客户端确切文件名、多槽位优先级与键值语法在本调研中未做本机实测，标为**未确认**）。

### C3. `SlayerApothecaryMoon/sensitivity-converter-aim-trainer`
- **名称：** Sensitivity Converter & Aim Trainer（`SlayerApothecaryMoon`）
- **链接：** https://github.com/SlayerApothecaryMoon/sensitivity-converter-aim-trainer
- **技术栈：** Rust（Tauri 2 桌面后端）+ 原生 JavaScript 前端（见 [`src-tauri/src/`](https://github.com/SlayerApothecaryMoon/sensitivity-converter-aim-trainer/tree/main/src-tauri/src)）
- **许可证：** `MIT`（MIT License，见 [`LICENSE`](https://github.com/SlayerApothecaryMoon/sensitivity-converter-aim-trainer/blob/main/LICENSE)）。
- **最近更新时间：** `2026-11-09`（GitHub API `repos/SlayerApothecaryMoon/sensitivity-converter-aim-trainer` 的 `pushed_at`）。
- **对 CS2 `m_yaw` / FOV / 开镜灵敏度的处理及与 `04-sensitivity-spec.md` 一致性：**
  - **`m_yaw` 处理：** [`src-tauri/src/games.rs`](https://github.com/SlayerApothecaryMoon/sensitivity-converter-aim-trainer/blob/main/src-tauri/src/games.rs) 第 124–126 行定义 CS2 条目：`yaw: 0.022`、`unit: SensUnit::Multiplier`，[`convert.rs`](https://github.com/SlayerApothecaryMoon/sensitivity-converter-aim-trainer/blob/main/src-tauri/src/convert.rs) 第 71–81 行计算 `deg_per_count = yaw * sens`、`counts_per_360 = 360.0 / deg_per_count`、`cm_per_360 = counts_per_360 / dpi * 2.54`。默认 `m_yaw = 0.022` 时与 `04-sensitivity-spec.md` 完全一致，但**不支持自定义 `m_yaw`（如 4:3 拉伸玩家改用 `0.0165`）或独立 `m_pitch`**。
  - **FOV 投影处理：** [`games.rs`](https://github.com/SlayerApothecaryMoon/sensitivity-converter-aim-trainer/blob/main/src-tauri/src/games.rs) 第 14–21 行专门定义 `FovKind::Hor4x3`（注释：`"Horizontal FOV measured at a 4:3 reference aspect (Source / IW style)"`），CS2 设为 `default_fov: 90.0`，通过 `vfov_from_hfov(90.0, 4.0/3.0)` 先算固定垂直 FOV（约 `73.74°`），再用 `hfov_from_vfov(vfov, aspect)` 扩展到宽屏（第 177–181 行单元测试 `cs2_fov_is_106_at_16_9` 断言 16:9 下为 `106.26°`）——**FOV 数学模型与 [`docs/04-sensitivity-spec.md`](../04-sensitivity-spec.md) 第 2 节 100% 一致**。
  - **开镜灵敏度处理：** [`convert.rs`](https://github.com/SlayerApothecaryMoon/sensitivity-converter-aim-trainer/blob/main/src-tauri/src/convert.rs) 第 95–104 行仅实现跨游戏不同 FOV 间的垂直屏幕距离匹配 `monitor_ratio`（`percent <= 1e-6` 时返回 `tan(vfov_to/2) / tan(vfov_from/2)`），**未实现 CS2 游戏内 `zoom_sensitivity_ratio` 换算**。（注：社区流传的 AWP 一倍镜 `zoom_sensitivity_ratio ≈ 0.818933` 正是由假设 CS2 内部按 `K_angle = 40° / 90°` 缩放、而玩家希望达成 `r -> 0` 焦距匹配 `K_tan = tan(20°) / tan(45°)` 反推得到 `ratio = tan(20°) * (90 / 40) ≈ 0.81893327`；这一社区推导恰恰印证了 `04-sensitivity-spec.md` 第 4.1 节将 `K_angle = F_zoom / 90°` 列为待证伪首选假设的合理性，但 CS2 实际内部公式仍须以游戏内黑盒实测为准）。
- **可借鉴点：**
  - 用紧凑枚举 `FovKind`（`Hor4x3` / `Hor16x9` / `Vertical`）统一表达不同游戏的 FOV 标称基准并附带往返（round-trip）单元测试（[`games.rs`](https://github.com/SlayerApothecaryMoon/sensitivity-converter-aim-trainer/blob/main/src-tauri/src/games.rs) 第 164–196 行）。
- **不适用之处：**
  - **灵敏度上下限与小数位限制过严：** [`games.rs`](https://github.com/SlayerApothecaryMoon/sensitivity-converter-aim-trainer/blob/main/src-tauri/src/games.rs) 第 126 行将 CS2 限制为 `sens_max: 8.0, decimals: 3`，而 CS2 配置文件与控制台实际支持更高精度小数及大于 8 的灵敏度，`mcs` 不应做三位小数截断。
  - **包含进程名匹配字段（`process: "cs2.exe"`）：** `mcs` 严格遵守不接触、不扫描 CS2 进程的规范，不采用进程检测方案。

### 附：C 类工具对 CS2 参数处理与 `docs/04-sensitivity-spec.md` 对照汇总

| 维度 | `docs/04-sensitivity-spec.md`（本项目规格） | A1 `LibreAim` | C1 `SensitivityMatcher` | C2 `game-sensitivity-coach` | C3 `SlayerApothecaryMoon` |
|---|---|---|---|---|---|
| 默认水平增益 | `0.022°/count`（待游戏内核对） | `0.022`（一致） | `0.022`（一致） | 不内置常数，外部传入校准值 | `0.022`（一致） |
| 自定义 `m_yaw` / 独立 `m_pitch` | 支持，`yaw` 与 `pitch` 独立乘系数 | 不支持（写死 `0.022`） | 支持手填任意 `yaw`，无 `pitch` | 支持任意校准斜率 | 不支持（写死 `0.022`） |
| 角度累积精度 | `float64` 累积逻辑角度，不读回渲染变换 | 32 位节点变换直接累加（不一致） | 维护浮点余量累加器 `$gResidual` | Python `float`（IEEE 754 `float64`） | Rust `f64` |
| 未开镜 FOV 规则 | `4:3 hfov = 90° → vfov ≈ 73.7398°`（Hor+） | **错误**（把 `103` 直接赋给垂直 FOV） | 不涉及 | 要求传入同轴实际渲染 FOV | `Hor4x3(90°)` → `vfov ≈ 73.74°`（一致） |
| CS2 开镜灵敏度 | 区分 `K_angle = F_zoom/90°` 与 `K_tan` 候选，**待黑盒实测** | 未实现 | 未实现 | 实现通用 `atan/tan` 屏幕距离比，未测 CS2 内部公式 | 实现跨游戏 `MDV`，未实现 CS2 开镜参数 |

---

## D. 程序化武器动画 / 检视动画的做法（3 个对象）

### D1. Ming-Lun "Allen" Chou —《Game Math: Precise Control over Numeric Springing》与 `TheAllenChou/numeric-springing`
- **名称：** Game Math: Precise Control over Numeric Springing（数值弹簧精确控制）及配套示例库
- **链接：**
  - 技术文章：https://allenchou.net/2015/04/game-math-precise-control-over-numeric-springing/
  - 配套源码库：https://github.com/TheAllenChou/numeric-springing（含三维旋转弹簧 [`QuaternionSpring.cs`](https://github.com/TheAllenChou/numeric-springing/blob/master/3d-rotation-spring/Assets/QuaternionSpring.cs)）
- **技术栈：** 数学推导 + C# / ActionScript（纯代数更新公式，15 行内可无损写成静态类型 GDScript）
- **许可证：** 代码库 `MIT`（MIT License，见 [`LICENSE`](https://github.com/TheAllenChou/numeric-springing/blob/master/LICENSE)）；博客文章文本版权归作者所有（仅参考公开数学公式与 `MIT` 仓库算法）。
- **最近更新时间：** 文章发布于 `2015-04-08`；`numeric-springing` 仓库最近更新 `2020-04-18`（GitHub API `repos/TheAllenChou/numeric-springing` 的 `pushed_at`）。
- **可借鉴点：**
  - **面向手感调校的直观参数化（频率 + 阻尼比）：** 摒弃难以调参的抽象刚度 $k$ 和阻尼系数 $c$，改用角频率 $\omega = 2\pi f$（控制节奏快慢，单位 Hz）与阻尼比 $\zeta$（$\zeta < 1$ 轻微过冲回弹、$\zeta = 1$ 临界阻尼最快无过冲收敛、$\zeta > 1$ 过阻尼粘滞），极其适合写在 `mcs` 的 `data/` 武器手感 JSON 中供人工微调。
  - **帧率无关的隐式/半隐式数值稳定性：** [`QuaternionSpring.cs`](https://github.com/TheAllenChou/numeric-springing/blob/master/3d-rotation-spring/Assets/QuaternionSpring.cs) 第 42–57 行使用行列式逆 `detInv = 1.0 / (f + h * h * omega * omega)` 同步求解位置 `x` 与速度 `v`，即使在低帧率或帧时间突变时也绝不发散爆炸，在 60Hz–500Hz 下保持一致的物理收敛曲线。可用于拔刀到位的轻微过冲回弹、视角转动惯性滞后（sway）以及检视被打断时的平滑回正。
- **不适用之处：**
  - 纯弹簧阻尼器只适合**微动叠加层与过渡缓冲**，不能单独表达复杂的多阶段刀型检视花式翻转（如蝴蝶刀、爪子刀的多段旋转轨迹仍需关键帧曲线或分段姿态序列作为目标输入 `xt`）。

### D2. `vi4hu/godot-procedural-recoil`
- **名称：** Godot Procedural Recoil（`vi4hu/godot-procedural-recoil`）
- **链接：** https://github.com/vi4hu/godot-procedural-recoil
- **技术栈：** Godot 4（GDScript 插件 `addons/procedural-recoil/`；见 [`recoil.gd`](https://github.com/vi4hu/godot-procedural-recoil/blob/main/addons/procedural-recoil/recoil.gd)）
- **许可证：** `MIT`（MIT License，见 [`LICENSE`](https://github.com/vi4hu/godot-procedural-recoil/blob/main/LICENSE)）。
- **最近更新时间：** `2024-09-15`（GitHub API `repos/vi4hu/godot-procedural-recoil` 的 `pushed_at`）。
- **可借鉴点：**
  - **双变量冲量-恢复结构：** [`recoil.gd`](https://github.com/vi4hu/godot-procedural-recoil/blob/main/addons/procedural-recoil/recoil.gd) 第 5–6 行与第 26–27 行采用 `targetRotation`（受击发冲量瞬间抬升并以 `returnSpeed` 回归零点）与 `currentRotation`（以 `snappiness` 追随 `targetRotation`）的双层平滑模式。这种「快抬升 + 慢恢复」双速率结构非常适合在 Godot 4 中作为一个独立挂载在相机/武器容器上的纯程序化修饰节点，用来模拟轻/重击挥刀或开火时的瞬时镜头/枪身震动（kickback）。
- **不适用之处：**
  - **帧率相关的线性插值缺陷（反面教材）：** [`recoil.gd`](https://github.com/vi4hu/godot-procedural-recoil/blob/main/addons/procedural-recoil/recoil.gd) 第 26–27 行直接写 `lerp(targetRotation, Vector3.ZERO, returnSpeed * delta)`。当帧率变化时，`lerp(a, b, k * delta)` 的轨迹并非帧率无关（且当 `returnSpeed * delta > 1.0` 时会发生反向震荡越界）；在 `mcs` 中若采用一阶指数衰减，必须改写为帧率无关的 `1.0 - exp(-speed * delta)` 或采用 D1 的二阶弹簧积分。
  - 第 42 行遗留了调试输出 `print(1)`，且第 35 行用 `global_rotation.z = 0` 硬修欧拉角耦合倾斜问题，说明旋转叠加应优先围绕局部正交轴或四元数计算。

### D3. `KenneyNL/Starter-Kit-FPS`（结合 `Jeh3no` 动画管理器的程序化层与关键帧/Tween 检视分层做法）
- **名称：** Kenney Starter Kit FPS（辅以 B2 `AnimationManager` 向量叠加模式对照）
- **链接：**
  - 主对象：https://github.com/KenneyNL/Starter-Kit-FPS（核心脚本 [`objects/player.gd`](https://github.com/KenneyNL/Starter-Kit-FPS/blob/main/objects/player.gd)、[`scripts/weapon.gd`](https://github.com/KenneyNL/Starter-Kit-FPS/blob/main/scripts/weapon.gd)）
  - 对照实现：[`Jeh3no/Godot-simple-FPS-weapon-system` 的 `animation_manager_script.gd`](https://github.com/Jeh3no/Godot-simple-FPS-weapon-system/blob/main/addons/JehenoSimpleFPSWeaponSystem/Weapons/Scripts/animation_manager_script.gd)
- **技术栈：** Godot 4（GDScript + `SubViewportContainer` 独立武器层 + CC0 3D 资产）
- **许可证：** 代码为 `MIT`（MIT License，见 [`LICENSE.md`](https://github.com/KenneyNL/Starter-Kit-FPS/blob/main/LICENSE.md)），Kenney 随附模型与音效为 `CC0`（若后续用作灰盒占位素材，须登记在 `assets/CREDITS.md`）。
- **最近更新时间：** `2026-03-12`（GitHub API `repos/KenneyNL/Starter-Kit-FPS` 的 `pushed_at`）。
- **可借鉴点：**
  - **父容器程序化惯性层 + 子节点关键帧动画层（解决检视动画与移动摆动冲突的标准做法）：**
    1. 在 [`Starter-Kit-FPS/objects/player.gd`](https://github.com/KenneyNL/Starter-Kit-FPS/blob/main/objects/player.gd) 第 39–40 行与第 72–88 行中，场景树将武器放在 `$Head/Camera/SubViewportContainer/SubViewport/CameraItem/Container` 下：外层 `Container` 实时叠加玩家移动速度反推滞后（第 72 行 `basis.inverse() * applied_velocity`）与落地冲击下沉（第 88 行 `camera.position.y = -0.1`），并用 `Tween` 驱动切枪进出过渡；而武器自身的局部关键帧动画（如拔刀、检视翻转、挥刀）可在 `Container` 内部的子节点上由 `AnimationPlayer` 独立播放，两层局部变换（`Transform3D`）天然相乘叠加，互不覆盖。
    2. 对照 [`Jeh3no` 的 `animation_manager_script.gd`](https://github.com/Jeh3no/Godot-simple-FPS-weapon-system/blob/main/addons/JehenoSimpleFPSWeaponSystem/Weapons/Scripts/animation_manager_script.gd) 第 24–33 行与第 70–96、156–163 行：将侧倾（`tilt`）、鼠标滞后（`sway`）、步伐起伏（8 字形双倍频正弦波 `sin(t * f)` 与 `sin(t * f * 0.5)` 的 `bob`）分别算出偏移向量后求和赋给模型容器，且在鼠标输入小于阈值时改用确定性步进 `move_toward(..., 0.0, speed * delta)` 精确归零，防止连续 `lerp` 残留微小浮点偏移。
- **不适用之处：**
  - `Starter-Kit-FPS` 本身面向街机射击原型，其 `mouse_sensitivity = 700`（见 [`player.gd`](https://github.com/KenneyNL/Starter-Kit-FPS/blob/main/objects/player.gd) 第 14 行，后续控制逻辑配合 `delta` 缩放）违反 [`docs/04-sensitivity-spec.md`](../04-sensitivity-spec.md) 第 1 节「不得乘帧间隔」的铁律，视角控制部分不可采用。

---

## 对 `mcs` 的建议（8 条）

1. **视角输入坚持「原始计数 + `float64` 逻辑角度独立累积」，严禁照搬通用 Godot FPS 模板的写法（依据：A1、B1、B4、C2、D3）**
   开源 Godot 练枪与 FPS 模板普遍直接用 `event.relative` 调用 `Node3D.rotate_y/x` 累加 32 位变换甚至误乘 `delta`（如 D3）。`mcs` 应继续沿用已通过 P0-4 初步验证的 `screen_relative`（待 #21 补测闭环）与 `look_math.gd` 的 `float64` 逻辑角度累积；同时在 #21 / P0-5 实测同帧边界截断时，参考 B4 测试 `Input.set_use_accumulated_input(false)` 是否更贴近 CS2 的真实事件粒度。

2. **世界相机 FOV 严格使用 `KEEP_HEIGHT` + `73.7398°` 垂直基准，建立防回归测试避免「水平角误填垂直 FOV」（依据：A1、C3）**
   A1（LibreAim）将 `103` 直接赋给 Godot `Camera3D.fov` 导致严重广角失真的案例表明，Godot 默认按垂直 FOV 投影极易踩坑。`mcs` 应按 C3 的 `Hor4x3` 往返测试思路，固化 `vfov = 2 * atan(tan(90°/2) * 3/4) ≈ 73.739795°` 并在不同视口宽高比下用自动化测试校验实际投影角。

3. **Viewmodel 渲染优先采用「渲染帧同步的独立 `SubViewport` 相机」，备选 B1 的 Reverse-Z 裁剪空间着色器（依据：A3、B1、B2、D3）**
   独立 `SubViewport` + 专用 `Camera3D`（A3、B2、D3）对刀与枪的自定义材质零侵入、天然隔绝穿墙且便于按 CS2 规则单独调校 `viewmodel_fov`；但必须修正 B2 在 `_physics_process` 同步相机的缺陷，改为与世界相机同帧同步以消除高刷屏抖动。若后续性能分析需要省去双视口开销，可评估 B1 适配 Godot 4.3+ Reverse-Z 的 `weapon_clip_and_fov_shader.gdshader`。

4. **切枪与检视状态机必须由「纯数值时钟」驱动并支持任意时刻重入打断，绝不依赖 `AnimationPlayer` 完成信号或 `await` 计时器（依据：B1、B2、B3）**
   B2 用 `await create_timer` 锁死切枪、B3 用 `animation_finished` 决定状态结束，均无法还原 CS2 的「Q 快切随时重置拔出计时」与「检视瞬间可开火/切刀」，且无法保证 `≤ 1 帧@144Hz（≈7 ms）` 的计时精度。`mcs` 应将拔出可开火时长（`deploy_duration_s` 等，带单位后缀）定义为纯数据状态机，参考 B1 的取消回调机制让动画层被动跟随状态机跳转与倍速缩放。

5. **采用「父容器帧率无关二阶数值弹簧 + 子节点关键帧主动作」的双层节点结构实现刀与枪的手感（依据：B2、D1、D2、D3）**
   刀型的拔出、检视翻转等特征轨迹放在子节点关键帧动画（早期灰盒阶段可用关键帧姿态序列占位），而鼠标转动滞后（sway）、步伐 8 字摆动（bob）、落地缓冲与急停惯性放在父级容器节点上实时叠加（D3）；平滑算法统一采用 D1 的帧率无关半隐式二阶弹簧（用频率 `freq_hz` 与阻尼比 `damping_ratio` 配置在 `data/` 中），摒弃 D2 中受帧率影响的 `lerp(..., speed * delta)`，并在静止阈值内结合 B2 的 `move_toward` 消除残余漂移。

6. **运动相机插值与视角旋转解耦：平移可插值，旋转零插值（依据：B4）**
   v0.1 引入基础移动与碰撞时，若物理帧率固定而渲染帧率不封顶，可参考 B4（GoldGdt）仅对角色身体到相机锚点的平移坐标使用 `Engine.get_physics_interpolation_fraction()` 插值，而鼠标控制的 yaw/pitch 在渲染前即时更新、不做任何平滑或插值，确保 G1/G2 零额外视角延迟。

7. **CS2 本地配置导入器遵循严格的只读文件系统安全边界，不枚举进程、不硬编码三位小数截断（依据：C1、C2、C3）**
   开发 G4 配置导入时，参考 C2（`discover_settings.py`）跳过重解析点、限制扫描范围，仅只读解析本地 `<Steam>/userdata/<id>/730/local/cfg/` 下的配置文件（优先核实 `cs2_user_convars_0_slot0.vcfg` 及用户自定义 `autoexec.cfg`，具体结构上线前本机实测确认）；完整保留 `sensitivity`、`m_yaw`、`m_pitch`、`zoom_sensitivity_ratio` 原始浮点精度，避免 C3 的三位小数截断与 `cs2.exe` 进程检测，更严禁类似 C1 的任何模拟输入注入。

8. **开镜灵敏度在 P0-5 / 专项黑盒实测完成前保持可插拔公式配置（依据：C2、C3）**
   C2 与 C3 的源码表明，外部换算工具普遍只实现跨游戏 `tan` 比（`K_tan`）屏幕距离匹配，而社区 `0.818933` 经验值恰恰建立在假设 CS2 内部使用角度比 `K_angle = F_zoom / 90°` 的前提之上。在完成 `docs/04-sensitivity-spec.md` 第 4.1 节规定的游戏内黑盒证伪测量前，代码层应把开镜缩放系数 `Z` 设计为数据可注入接口，不提前写死未证实的候选公式。
