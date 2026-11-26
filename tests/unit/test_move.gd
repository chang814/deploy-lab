extends "res://tests/test_case.gd"
## MoveMath、MoveConfig、PlayerMove.step 的测试。

const DT_S: float = 1.0 / 64.0


func run_tests() -> void:
	_test_wish_dir()
	_test_friction()
	_test_accelerate()
	_test_air_accelerate()
	_test_config()
	_test_player_step()


func _test_wish_dir() -> void:
	var f: Vector3 = MoveMath.wish_dir(Vector2(0, 1), 0.0)
	ok("yaw 0 向前 = -Z", f.is_equal_approx(Vector3(0, 0, -1)))
	var r: Vector3 = MoveMath.wish_dir(Vector2(1, 0), 0.0)
	ok("yaw 0 向右 = +X", r.is_equal_approx(Vector3(1, 0, 0)))
	var f90: Vector3 = MoveMath.wish_dir(Vector2(0, 1), 90.0)
	ok("右转 90° 后向前 = +X", f90.is_equal_approx(Vector3(1, 0, 0)))
	var diag: Vector3 = MoveMath.wish_dir(Vector2(1, 1), 0.0)
	near("斜向归一化", diag.length(), 1.0, 1e-6)
	ok("无输入 = 零", MoveMath.wish_dir(Vector2.ZERO, 30.0) == Vector3.ZERO)


func _test_friction() -> void:
	var v: Vector3 = MoveMath.friction(Vector3(6.0, 1.0, 0.0), 5.2, 2.032, DT_S)
	near("摩擦减速", v.x, 6.0 - 6.0 * 5.2 * DT_S, 1e-5)
	near("摩擦不动 y", v.y, 1.0, 0.0)
	var slow: Vector3 = MoveMath.friction(Vector3(0.05, 0.0, 0.0), 5.2, 2.032, DT_S)
	near("低速按 stop_speed 停下", slow.x, 0.0, 0.0)


func _test_accelerate() -> void:
	var v: Vector3 = Vector3.ZERO
	for i: int in 200:
		v = MoveMath.accelerate(v, Vector3(1, 0, 0), 6.35, 5.5, DT_S)
	near("加速到目标速度为止", v.x, 6.35, 1e-4)
	var once: Vector3 = MoveMath.accelerate(Vector3.ZERO, Vector3(1, 0, 0), 6.35, 5.5, DT_S)
	near("单步加速量", once.x, 5.5 * 6.35 * DT_S, 1e-6)
	var fast: Vector3 = MoveMath.accelerate(Vector3(10, 0, 0), Vector3(1, 0, 0), 6.35, 5.5, DT_S)
	near("已超速时不加速", fast.x, 10.0, 0.0)


func _test_air_accelerate() -> void:
	# 空中沿前进方向已有速度时，目标被限制在 air_cap，不再加速
	var v: Vector3 = MoveMath.air_accelerate(Vector3(5, 0, 0), Vector3(1, 0, 0), 6.35, 12.0, 0.762, DT_S)
	near("空中同向不加速", v.x, 5.0, 0.0)
	# 侧向可以加速（扫射转向），但单步不超过 air_cap
	# 侧向：加速量按原始期望速度算（12 × 6.35 / 64 = 1.19），被上限 0.762 截住
	var side: Vector3 = MoveMath.air_accelerate(Vector3(5, 0, 0), Vector3(0, 0, 1), 6.35, 12.0, 0.762, DT_S)
	near("空中侧向加速到上限", side.z, 0.762, 1e-6)
	# 未触及上限：dt 很小时加速量 = 12 × 6.35 × 0.001 = 0.0762（若误用上限 0.762 计算会得到 0.009144）
	var small: Vector3 = MoveMath.air_accelerate(Vector3.ZERO, Vector3(0, 0, 1), 6.35, 12.0, 0.762, 0.001)
	near("空中加速量按原始期望速度计算", small.z, 0.0762, 1e-9)


func _test_config() -> void:
	var c: MoveConfig = MoveConfig.load_file()
	ok("data/move/defaults.json 有效（%s）" % c.error, c.is_valid())
	ok("文件不存在无效", not MoveConfig.load_file("res://data/move/不存在.json").is_valid())
	ok("缺字段无效", not MoveConfig.from_json_text('{"run_speed_mps": 6}').is_valid())
	var bad: Dictionary = c.values.duplicate()
	bad["walk_multiplier"] = 1.5
	ok("慢走倍率 > 1 无效", not MoveConfig.from_json_text(JSON.stringify(bad)).is_valid())
	bad = c.values.duplicate()
	bad["gravity_mps2"] = -1
	ok("负数无效", not MoveConfig.from_json_text(JSON.stringify(bad)).is_valid())
	bad = c.values.duplicate()
	bad["eye_height_m"] = 5.0
	ok("眼高超过身高无效", not MoveConfig.from_json_text(JSON.stringify(bad)).is_valid())
	bad = c.values.duplicate()
	bad["body_radius_m"] = 1.0
	bad["body_height_m"] = 1.5
	bad["eye_height_m"] = 1.3
	ok("身高小于两倍半径无效", not MoveConfig.from_json_text(JSON.stringify(bad)).is_valid())


func _make_player() -> Array:
	var root: Node = (load("res://scenes/main.tscn") as PackedScene).instantiate()
	var p: PlayerMove = root.get_node("Player") as PlayerMove
	p.setup(MoveConfig.load_file())
	return [root, p]


func _test_player_step() -> void:
	var made: Array = _make_player()
	var root: Node = made[0]
	var p: PlayerMove = made[1]
	ok("主场景的 Player 是 PlayerMove", p != null)
	ok("有碰撞体", root.get_node_or_null("Player/Body") is CollisionShape3D)
	var look: Node3D = root.get_node("Player/Look") as Node3D
	near("视角在眼高（相对身体中心）", look.position.y, p.cfg.get_f("eye_height_m") - p.cfg.get_f("body_height_m") / 2.0, 1e-6)

	# 地面按住 W 跑够久 → 达到跑步速度
	var v: Vector3 = Vector3.ZERO
	for i: int in 300:
		v = p.step(v, Vector2(0, 1), false, false, true, 0.0, DT_S)
	near("跑步速度", Vector2(v.x, v.z).length(), p.cfg.get_f("run_speed_mps"), 1e-3)
	ok("向前 = -Z", v.z < 0.0 and absf(v.x) < 1e-4)
	# 慢走
	var w: Vector3 = Vector3.ZERO
	for i: int in 300:
		w = p.step(w, Vector2(0, 1), true, false, true, 0.0, DT_S)
	near("慢走速度", Vector2(w.x, w.z).length(), p.cfg.get_f("run_speed_mps") * p.cfg.get_f("walk_multiplier"), 1e-3)
	# 松手后停下
	for i: int in 300:
		v = p.step(v, Vector2.ZERO, false, false, true, 0.0, DT_S)
	near("松手停下", Vector2(v.x, v.z).length(), 0.0, 1e-6)
	# 起跳：竖直速度 = jump_speed；空中受重力
	var j: Vector3 = p.step(Vector3.ZERO, Vector2.ZERO, false, true, true, 0.0, DT_S)
	near("起跳速度", j.y, p.cfg.get_f("jump_speed_mps"), 1e-6)
	var air: Vector3 = p.step(j, Vector2.ZERO, false, false, false, 0.0, DT_S)
	near("空中重力", air.y, j.y - p.cfg.get_f("gravity_mps2") * DT_S, 1e-6)
	# 跳跃高度 ≈ v² / 2g
	near("跳跃高度约 1.45 m", pow(p.cfg.get_f("jump_speed_mps"), 2) / (2.0 * p.cfg.get_f("gravity_mps2")), 1.448, 0.01)
	_test_input_and_body(p, root)
	root.free()


func _test_input_and_body(p: PlayerMove, root: Node) -> void:
	# 按键 → 输入向量的符号（lambda 按值捕获局部变量，所以原地修改同一个字典）
	var held: Dictionary = {}
	p.key_down = func(key: Key) -> bool: return held.get(key, false)
	held.clear()
	held.merge({KEY_W: true})
	ok("W = 向前", p.read_move_input() == Vector2(0, 1))
	held.clear()
	held.merge({KEY_S: true})
	ok("S = 向后", p.read_move_input() == Vector2(0, -1))
	held.clear()
	held.merge({KEY_D: true})
	ok("D = 向右", p.read_move_input() == Vector2(1, 0))
	held.clear()
	held.merge({KEY_A: true})
	ok("A = 向左", p.read_move_input() == Vector2(-1, 0))
	held.clear()
	held.merge({KEY_W: true, KEY_S: true})
	ok("W+S 抵消", p.read_move_input() == Vector2.ZERO)
	# 空格：按下排队一次起跳；自动重复（按住）不排队
	var space: InputEventKey = InputEventKey.new()
	space.physical_keycode = KEY_SPACE
	space.pressed = true
	space.echo = true
	p._unhandled_input(space)
	ok("按住空格的自动重复不起跳", not p.jump_queued())
	space.echo = false
	p._unhandled_input(space)
	ok("按下空格排队起跳", p.jump_queued())
	# 物理帧消费起跳请求：只起跳一次，下一帧落地不会自动再跳
	(root.get_node("Player/Look") as FpsLook).captured = true
	var v1: Vector3 = p.physics_tick(Vector3.ZERO, true, DT_S)
	near("物理帧起跳", v1.y, p.cfg.get_f("jump_speed_mps"), 1e-6)
	ok("起跳请求已消费", not p.jump_queued())
	var v2: Vector3 = p.physics_tick(Vector3.ZERO, true, DT_S)
	near("下一帧在地面不再起跳", v2.y, 0.0, 0.0)
	# 物理帧用 WASD 输入：按住 W 一帧后向前有速度
	held.clear()
	held.merge({KEY_W: true})
	var v3: Vector3 = p.physics_tick(Vector3.ZERO, true, DT_S)
	ok("物理帧按 W 向前加速（-Z）", v3.z < 0.0)
	# 暂停时不响应输入
	(root.get_node("Player/Look") as FpsLook).captured = false
	var v4: Vector3 = p.physics_tick(Vector3.ZERO, true, DT_S)
	ok("暂停时忽略移动输入", v4 == Vector3.ZERO)
	held.clear()
	# 碰撞体尺寸跟随配置（非默认值）
	var vals: Dictionary = p.cfg.values.duplicate()
	vals["body_radius_m"] = 0.2
	vals["body_height_m"] = 1.5
	vals["eye_height_m"] = 1.3
	p.setup(MoveConfig.from_json_text(JSON.stringify(vals)))
	var shape: CapsuleShape3D = (root.get_node("Player/Body") as CollisionShape3D).shape as CapsuleShape3D
	near("胶囊半径跟随配置", shape.radius, 0.2, 1e-6)
	near("胶囊高度跟随配置", shape.height, 1.5, 1e-6)
	near("眼高跟随配置", (root.get_node("Player/Look") as Node3D).position.y, 1.3 - 0.75, 1e-6)
