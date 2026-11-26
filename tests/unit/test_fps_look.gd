extends "res://tests/test_case.gd"
## FpsLook 与主场景的测试（不进入场景树，直接调用 setup / look_by）。


func run_tests() -> void:
	_test_main_scene()
	_test_look_math_wiring()
	_test_ready_in_tree()
	_test_input_events()
	_test_non_default_config()


func _motion(x: float, y: float) -> InputEventMouseMotion:
	var m: InputEventMouseMotion = InputEventMouseMotion.new()
	m.screen_relative = Vector2(x, y)
	m.relative = Vector2(x * 3.0, y * 3.0)   # 故意与 screen_relative 不同：确认用的是 screen_relative
	return m


func _setup_default(player: FpsLook) -> void:
	player.setup(
		LookConfig.from_json_text(
			'{"m_yaw_deg": 0.022, "m_pitch_deg": 0.022, "pitch_min_deg": -89, "pitch_max_deg": 89, "base_hfov_4x3_deg": 90}'
		),
		PlayerSettings.from_json_text('{"sensitivity": 2}')
	)


func _test_ready_in_tree() -> void:
	# 走 _ready() 的真实路径：读真实配置文件、关闭输入累积、锁定鼠标；_exit_tree() 恢复。
	# 测试入口在主循环启动前运行、拿不到场景树，所以直接调用这两个回调
	var root: Node = _make()
	Input.use_accumulated_input = true
	var player: FpsLook = root.get_node("Player/Look") as FpsLook
	var modes: Array[int] = []
	player.apply_mouse_mode = func(mode: Input.MouseMode) -> void: modes.append(mode)
	player.read_cs2_sensitivity = func(_c: Cs2Cfg) -> float: return NAN   # 不依赖本机是否装了 CS2
	player._ready()
	ok("_ready 调用了 MOUSE_MODE_CAPTURED", modes == [Input.MOUSE_MODE_CAPTURED])
	ok("_ready 后已加载配置", player.look != null and player.settings != null)
	ok("_ready 关闭了输入累积", not Input.use_accumulated_input)
	ok("_ready 后处于锁定状态", player.captured)
	near("_ready 后 FOV", (root.get_node("Player/Look/Camera3D") as Camera3D).fov, 73.739795291688, 1e-4)
	player._exit_tree()
	ok("离开场景树后恢复输入累积", Input.use_accumulated_input)
	ok("离开场景树后解除锁定", not player.captured)
	ok("离开时调用了 MOUSE_MODE_VISIBLE", modes.back() == Input.MOUSE_MODE_VISIBLE)
	root.free()


func _test_input_events() -> void:
	var root: Node = _make()
	var player: FpsLook = root.get_node("Player/Look") as FpsLook
	_setup_default(player)
	var modes: Array[int] = []
	player.apply_mouse_mode = func(mode: Input.MouseMode) -> void: modes.append(mode)
	player.set_captured(true)
	ok("锁定时调用了 MOUSE_MODE_CAPTURED", modes == [Input.MOUSE_MODE_CAPTURED])
	# 鼠标向右 100、向上 50（screen_relative.y 为负）→ yaw +4.4°，pitch +2.2°
	player._unhandled_input(_motion(100.0, -50.0))
	near("事件 → yaw 向右", player.yaw_deg, 4.4, 1e-9)
	near("事件 → pitch 抬头", player.pitch_deg, 2.2, 1e-9)
	# Esc 释放后，鼠标移动不再转动视角
	var esc: InputEventKey = InputEventKey.new()
	esc.keycode = KEY_ESCAPE
	esc.pressed = true
	player._unhandled_input(esc)
	ok("Esc 后解除锁定", not player.captured)
	ok("Esc 时调用了 MOUSE_MODE_VISIBLE", modes.back() == Input.MOUSE_MODE_VISIBLE)
	player._unhandled_input(_motion(1000.0, 1000.0))
	near("解除锁定时忽略移动（yaw）", player.yaw_deg, 4.4, 1e-9)
	near("解除锁定时忽略移动（pitch）", player.pitch_deg, 2.2, 1e-9)
	# 点击重新锁定，再次响应移动
	var click: InputEventMouseButton = InputEventMouseButton.new()
	click.button_index = MOUSE_BUTTON_LEFT
	click.pressed = true
	player._unhandled_input(click)
	ok("点击后重新锁定", player.captured)
	ok("点击时调用了 MOUSE_MODE_CAPTURED", modes.back() == Input.MOUSE_MODE_CAPTURED)
	ok("一共切换了 3 次鼠标模式", modes.size() == 3)
	player._unhandled_input(_motion(-100.0, 0.0))
	near("重新锁定后响应移动", player.yaw_deg, 0.0, 1e-9)
	# 游戏中按 Esc 只暂停、不退出；暂停时再按 Esc 才退出
	var quits: Array[int] = []
	player.request_quit = func() -> void: quits.append(1)
	player._unhandled_input(esc)
	ok("游戏中按 Esc 不退出", quits.is_empty() and not player.captured)
	var held: InputEventKey = InputEventKey.new()
	held.keycode = KEY_ESCAPE
	held.pressed = true
	held.echo = true
	player._unhandled_input(held)
	ok("按住 Esc 的自动重复不会直接退出", quits.is_empty())
	player._unhandled_input(esc)
	ok("暂停时再按 Esc 退出", quits.size() == 1)
	player.set_captured(false)
	root.free()


func _test_non_default_config() -> void:
	# 非默认 FOV 与不同轴增益：防止把默认值写死或把两个轴的参数接反
	var root: Node = _make()
	var player: FpsLook = root.get_node("Player/Look") as FpsLook
	player.setup(
		LookConfig.from_json_text(
			'{"m_yaw_deg": 0.03, "m_pitch_deg": 0.01, "pitch_min_deg": -10, "pitch_max_deg": 20, "base_hfov_4x3_deg": 100}'
		),
		PlayerSettings.from_json_text('{"sensitivity": 1.5}')
	)
	near("FOV 跟随配置（4:3 水平 100°）", (root.get_node("Player/Look/Camera3D") as Camera3D).fov,
		LookMath.vfov_from_hfov(100.0, 4.0 / 3.0), 1e-4)
	player.look_by(100.0, -100.0)
	near("yaw 用 m_yaw", player.yaw_deg, 100.0 * 1.5 * 0.03, 1e-9)
	near("pitch 用 m_pitch", player.pitch_deg, 100.0 * 1.5 * 0.01, 1e-9)
	player.look_by(0.0, -100000.0)
	near("pitch 上限跟随配置", player.pitch_deg, 20.0, 0.0)
	player.look_by(0.0, 100000.0)
	near("pitch 下限跟随配置", player.pitch_deg, -10.0, 0.0)
	root.free()


func _make() -> Node:
	var packed: PackedScene = load("res://scenes/main.tscn")
	return packed.instantiate()


func _test_main_scene() -> void:
	var root: Node = _make()
	var player: FpsLook = root.get_node("Player/Look") as FpsLook
	ok("主场景里有 Player/Look（FpsLook）", player != null)
	ok("Player 下有 Camera3D", root.get_node_or_null("Player/Look/Camera3D") is Camera3D)
	ok("有准星", root.get_node_or_null("HUD/Crosshair") is Control)
	ok("地面有碰撞", (root.get_node("Room/Floor") as CSGBox3D).use_collision)
	var cfg: LookConfig = LookConfig.load_file()
	var ps: PlayerSettings = PlayerSettings.load_file()
	player.setup(cfg, ps)
	var cam: Camera3D = root.get_node("Player/Look/Camera3D") as Camera3D
	ok("相机保持垂直 FOV", cam.keep_aspect == Camera3D.KEEP_HEIGHT)
	# 规格：4:3 下水平 90° → 垂直 73.739795…°（Camera3D.fov 是 32 位，误差放宽到 1e-4）
	near("垂直 FOV", cam.fov, 73.739795291688, 1e-4)
	root.free()


func _test_look_math_wiring() -> void:
	var root: Node = _make()
	var player: FpsLook = root.get_node("Player/Look") as FpsLook
	var cfg: LookConfig = LookConfig.from_json_text(
		'{"m_yaw_deg": 0.022, "m_pitch_deg": 0.022, "pitch_min_deg": -89, "pitch_max_deg": 89, "base_hfov_4x3_deg": 90}'
	)
	var ps: PlayerSettings = PlayerSettings.from_json_text('{"sensitivity": 2}')
	player.setup(cfg, ps)
	# 向右 1000 count：yaw = 1000 × 2 × 0.022 = 44°；Godot 绕 Y 轴取负
	player.look_by(1000.0, 0.0)
	near("yaw 累计", player.yaw_deg, 44.0, 1e-9)
	near("节点 Y 旋转为 -44°", player.rotation_degrees.y, -44.0, 1e-4)
	# 鼠标向上（counts_y 为负）→ 抬头为正
	player.look_by(0.0, -100.0)
	near("pitch 抬头 4.4°", player.pitch_deg, 4.4, 1e-9)
	var cam: Camera3D = root.get_node("Player/Look/Camera3D") as Camera3D
	near("相机 X 旋转 4.4°", cam.rotation_degrees.x, 4.4, 1e-4)
	# pitch 被夹住
	player.look_by(0.0, -100000.0)
	near("pitch 上限 89°", player.pitch_deg, 89.0, 0.0)
	# yaw 转很多圈后，节点旋转仍落在一圈以内，累计值保留
	player.look_by(1000.0 * 100.0, 0.0)
	ok("节点旋转在 (-360, 0]", player.rotation_degrees.y > -360.0 and player.rotation_degrees.y <= 0.0)
	near("yaw 累计不丢", player.yaw_deg, 44.0 + 4400.0, 1e-6)
	root.free()
