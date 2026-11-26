extends "res://tests/test_case.gd"
## MoveMath、MoveConfig、PlayerMove.step 的测试。

const DT: float = 1.0 / 64.0


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
	var v: Vector3 = MoveMath.friction(Vector3(6.0, 1.0, 0.0), 5.2, 2.032, DT)
	near("摩擦减速", v.x, 6.0 - 6.0 * 5.2 * DT, 1e-5)
	near("摩擦不动 y", v.y, 1.0, 0.0)
	var slow: Vector3 = MoveMath.friction(Vector3(0.05, 0.0, 0.0), 5.2, 2.032, DT)
	near("低速按 stop_speed 停下", slow.x, 0.0, 0.0)


func _test_accelerate() -> void:
	var v: Vector3 = Vector3.ZERO
	for i: int in 200:
		v = MoveMath.accelerate(v, Vector3(1, 0, 0), 6.35, 5.5, DT)
	near("加速到目标速度为止", v.x, 6.35, 1e-4)
	var once: Vector3 = MoveMath.accelerate(Vector3.ZERO, Vector3(1, 0, 0), 6.35, 5.5, DT)
	near("单步加速量", once.x, 5.5 * 6.35 * DT, 1e-6)
	var fast: Vector3 = MoveMath.accelerate(Vector3(10, 0, 0), Vector3(1, 0, 0), 6.35, 5.5, DT)
	near("已超速时不加速", fast.x, 10.0, 0.0)


func _test_air_accelerate() -> void:
	# 空中沿前进方向已有速度时，目标被限制在 air_cap，不再加速
	var v: Vector3 = MoveMath.air_accelerate(Vector3(5, 0, 0), Vector3(1, 0, 0), 6.35, 12.0, 0.762, DT)
	near("空中同向不加速", v.x, 5.0, 0.0)
	# 侧向可以加速（扫射转向），但单步不超过 air_cap
	var side: Vector3 = MoveMath.air_accelerate(Vector3(5, 0, 0), Vector3(0, 0, 1), 6.35, 12.0, 0.762, DT)
	ok("空中侧向加速", side.z > 0.0 and side.z <= 0.762 + 1e-6)


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
		v = p.step(v, Vector2(0, 1), false, false, true, 0.0, DT)
	near("跑步速度", Vector2(v.x, v.z).length(), p.cfg.get_f("run_speed_mps"), 1e-3)
	ok("向前 = -Z", v.z < 0.0 and absf(v.x) < 1e-4)
	# 慢走
	var w: Vector3 = Vector3.ZERO
	for i: int in 300:
		w = p.step(w, Vector2(0, 1), true, false, true, 0.0, DT)
	near("慢走速度", Vector2(w.x, w.z).length(), p.cfg.get_f("run_speed_mps") * p.cfg.get_f("walk_multiplier"), 1e-3)
	# 松手后停下
	for i: int in 300:
		v = p.step(v, Vector2.ZERO, false, false, true, 0.0, DT)
	near("松手停下", Vector2(v.x, v.z).length(), 0.0, 1e-6)
	# 起跳：竖直速度 = jump_speed；空中受重力
	var j: Vector3 = p.step(Vector3.ZERO, Vector2.ZERO, false, true, true, 0.0, DT)
	near("起跳速度", j.y, p.cfg.get_f("jump_speed_mps"), 1e-6)
	var air: Vector3 = p.step(j, Vector2.ZERO, false, false, false, 0.0, DT)
	near("空中重力", air.y, j.y - p.cfg.get_f("gravity_mps2") * DT, 1e-6)
	# 跳跃高度 ≈ v² / 2g
	near("跳跃高度约 1.45 m", pow(p.cfg.get_f("jump_speed_mps"), 2) / (2.0 * p.cfg.get_f("gravity_mps2")), 1.448, 0.01)
	root.free()
