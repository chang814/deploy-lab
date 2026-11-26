class_name PlayerMove
extends CharacterBody3D
## 玩家身体：WASD 移动、Shift 慢走、空格跳跃、与灰盒几何体碰撞（v0.1，移动手感暂不对齐 CS2）。
## 朝向取子节点 Look（FpsLook）的 yaw；暂停（鼠标未锁定）时不响应移动输入，但仍受重力与摩擦。
## 每步的速度计算在 step() 里，不依赖场景树，测试可直接调用。

@export var look_path: NodePath = ^"Look"

var cfg: MoveConfig = null
var _look: FpsLook = null
var _jump_queued: bool = false
## 相机平滑：物理每秒只更新 tick_rate 次，渲染帧在两次物理更新之间按比例插值身体位置，避免高刷新率下画面一顿一顿
var _eye_offset_m: float = 0.0
var _prev_pos: Vector3 = Vector3.ZERO
var _curr_pos: Vector3 = Vector3.ZERO


func _ready() -> void:
	var c: MoveConfig = MoveConfig.load_file()
	if not c.is_valid():
		push_error(c.error)
		return
	setup(c)


func setup(c: MoveConfig) -> void:
	cfg = c
	_look = get_node(look_path) as FpsLook
	_eye_offset_m = c.get_f("eye_height_m") - c.get_f("body_height_m") / 2.0
	_look.position.y = _eye_offset_m
	_prev_pos = position
	_curr_pos = position
	# 碰撞体尺寸也来自配置（复制一份形状，避免改到场景里共享的资源）
	var body: CollisionShape3D = get_node_or_null(^"Body") as CollisionShape3D
	if body != null:
		var capsule: CapsuleShape3D = CapsuleShape3D.new()
		capsule.radius = c.get_f("body_radius_m")
		capsule.height = c.get_f("body_height_m")
		body.shape = capsule


## 一步的速度计算。input：x = 右，y = 前（各 -1..1）；walk：慢走；jump：本步请求起跳。
func step(v: Vector3, input: Vector2, walk: bool, jump: bool, on_floor: bool, yaw_deg: float, dt_s: float) -> Vector3:
	var dir: Vector3 = MoveMath.wish_dir(input, yaw_deg)
	var speed: float = cfg.get_f("run_speed_mps") * (cfg.get_f("walk_multiplier") if walk else 1.0)
	if dir == Vector3.ZERO:
		speed = 0.0
	if on_floor:
		if jump:
			# 起跳这一步不施加摩擦（与 Source 一致），保留水平速度
			v.y = cfg.get_f("jump_speed_mps")
			return MoveMath.air_accelerate(v, dir, speed, cfg.get_f("air_accelerate_per_s"),
				cfg.get_f("air_speed_cap_mps"), dt_s)
		v = MoveMath.friction(v, cfg.get_f("friction_per_s"), cfg.get_f("stop_speed_mps"), dt_s)
		v = MoveMath.accelerate(v, dir, speed, cfg.get_f("accelerate_per_s"), dt_s)
		v.y = 0.0
		return v
	v = MoveMath.air_accelerate(v, dir, speed, cfg.get_f("air_accelerate_per_s"), cfg.get_f("air_speed_cap_mps"), dt_s)
	v.y -= cfg.get_f("gravity_mps2") * dt_s
	return v


## 按键是否按着。测试换成假的键盘状态
var key_down: Callable = func(key: Key) -> bool:
	return Input.is_physical_key_pressed(key)


## WASD → 输入向量（x = 右，y = 前）。
func read_move_input() -> Vector2:
	return Vector2(
		float(key_down.call(KEY_D)) - float(key_down.call(KEY_A)),
		float(key_down.call(KEY_W)) - float(key_down.call(KEY_S))
	)


## 是否有待处理的起跳请求（测试用）。
func jump_queued() -> bool:
	return _jump_queued


func _unhandled_input(event: InputEvent) -> void:
	# 空格要「按下」才起跳（与 CS2 默认一致：按住不会连跳）
	if event is InputEventKey and event.pressed and not event.is_echo() \
			and (event as InputEventKey).physical_keycode == KEY_SPACE:
		_jump_queued = true


func _physics_process(dt_s: float) -> void:
	if cfg == null:
		return
	velocity = physics_tick(velocity, is_on_floor(), dt_s)
	# move_and_slide 需要物理世界，测试入口里没有；由试玩确认（PR #40 已知局限）
	_prev_pos = global_position
	move_and_slide()
	_curr_pos = global_position


func _process(_dt_s: float) -> void:
	if cfg == null or _look == null:
		return
	var f: float = Engine.get_physics_interpolation_fraction()
	_look.global_position = _prev_pos.lerp(_curr_pos, f) + Vector3(0.0, _eye_offset_m, 0.0)


## 一个物理帧的输入处理 + 速度计算（不含 move_and_slide）。起跳请求在这里被消费，只生效一次。
func physics_tick(v: Vector3, on_floor: bool, dt_s: float) -> Vector3:
	var active: bool = _look != null and _look.captured
	var input: Vector2 = read_move_input() if active else Vector2.ZERO
	var walk: bool = active and key_down.call(KEY_SHIFT)
	var jump: bool = active and _jump_queued
	_jump_queued = false
	return step(v, input, walk, jump, on_floor, _look.yaw_deg if _look != null else 0.0, dt_s)
