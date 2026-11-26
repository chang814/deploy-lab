extends "res://tests/test_case.gd"
## FpsLook 与主场景的测试（不进入场景树，直接调用 setup / look_by）。


func run_tests() -> void:
	_test_main_scene()
	_test_look_math_wiring()


func _make() -> Node:
	var packed: PackedScene = load("res://scenes/main.tscn")
	return packed.instantiate()


func _test_main_scene() -> void:
	var root: Node = _make()
	var player: FpsLook = root.get_node("Player") as FpsLook
	ok("主场景里有 Player（FpsLook）", player != null)
	ok("Player 下有 Camera3D", root.get_node_or_null("Player/Camera3D") is Camera3D)
	ok("有准星", root.get_node_or_null("HUD/Crosshair") is Control)
	ok("地面有碰撞", (root.get_node("Room/Floor") as CSGBox3D).use_collision)
	var cfg: LookConfig = LookConfig.load_file()
	var ps: PlayerSettings = PlayerSettings.load_file()
	player.setup(cfg, ps)
	var cam: Camera3D = root.get_node("Player/Camera3D") as Camera3D
	ok("相机保持垂直 FOV", cam.keep_aspect == Camera3D.KEEP_HEIGHT)
	# 规格：4:3 下水平 90° → 垂直 73.739795…°（Camera3D.fov 是 32 位，误差放宽到 1e-4）
	near("垂直 FOV", cam.fov, 73.739795291688, 1e-4)
	root.free()


func _test_look_math_wiring() -> void:
	var root: Node = _make()
	var player: FpsLook = root.get_node("Player") as FpsLook
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
	var cam: Camera3D = root.get_node("Player/Camera3D") as Camera3D
	near("相机 X 旋转 4.4°", cam.rotation_degrees.x, 4.4, 1e-4)
	# pitch 被夹住
	player.look_by(0.0, -100000.0)
	near("pitch 上限 89°", player.pitch_deg, 89.0, 0.0)
	# yaw 转很多圈后，节点旋转仍落在一圈以内，累计值保留
	player.look_by(1000.0 * 100.0, 0.0)
	ok("节点旋转在 (-360, 0]", player.rotation_degrees.y > -360.0 and player.rotation_degrees.y <= 0.0)
	near("yaw 累计不丢", player.yaw_deg, 44.0 + 4400.0, 1e-6)
	root.free()
