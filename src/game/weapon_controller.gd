class_name WeaponController
extends Node3D
## 武器控制（v0.2）：挂在相机下。读输入 → 驱动 WeaponState（按物理 tick 推进）→ 表现（模型、拔出动画、
## 后坐、枪口火光、命中射线、弹孔）。暂停（鼠标未锁定）时不响应输入。
##
## 输入：1 / 2 / 3 选槽位，Q 切到上一把，滚轮切换，左键开火（按住），R 换弹。

const HIP_POS: Vector3 = Vector3(0.19, -0.2, -0.42)   # 模型在相机空间里的位置（表现参数，不是手感时长）
const HIP_YAW_DEG: float = 10.0                        # 枪口略朝画面中心，露出枪身右侧
const VM_SCALE: float = 0.78                           # 模型缩放

@export var look_path: NodePath = ^"../.."

var state: WeaponState = WeaponState.new()
var cfg: WeaponConfig = null
var shots: int = 0
var hits: int = 0
var last_hit_target: String = ""
var _look: FpsLook = null
var _models: Dictionary = {}
var _shown: String = ""
var _kick: float = 0.0
var _flash_left_s: float = 0.0
var _flash: OmniLight3D = null
var _trigger: bool = false
## 两个物理 tick 之间收到过「按下」/「松开」：保留边沿，避免快速点击丢失
var _press_queued: bool = false
var _release_seen: bool = false


func _ready() -> void:
	var c: WeaponConfig = WeaponConfig.load_file()
	if not c.is_valid():
		push_error(c.error)
		return
	setup(c)


func setup(c: WeaponConfig) -> void:
	cfg = c
	_look = get_node_or_null(look_path) as FpsLook
	var physics_hz: int = int(ProjectSettings.get_setting("physics/common/physics_ticks_per_second"))
	if physics_hz != int(c.tick_rate_hz):
		push_warning("weapons.json 的 tick_rate_hz (%s) 与物理频率 (%d) 不一致，武器计时会失真" % [c.tick_rate_hz, physics_hz])
	state.setup(c.weapons, c.tick_rate_hz, String(c.weapons[0]["id"]))
	for w: Dictionary in c.weapons:
		var m: Node3D = Viewmodels.build(String(w["id"]))
		m.visible = false
		add_child(m)
		_models[w["id"]] = m
	_flash = OmniLight3D.new()
	_flash.light_color = Color(1.0, 0.7, 0.35)
	_flash.light_energy = 0.0
	_flash.omni_range = 4.0
	add_child(_flash)
	_show(state.current)


func _active() -> bool:
	return _look != null and _look.captured


func _unhandled_input(event: InputEvent) -> void:
	if cfg == null or not _active():
		return
	if event is InputEventKey and event.pressed and not event.is_echo():
		match (event as InputEventKey).physical_keycode:
			KEY_1: state.request_slot(1)
			KEY_2: state.request_slot(2)
			KEY_3: state.request_slot(3)
			KEY_Q: state.request_quick_switch()
			KEY_R: state.request_reload()
	elif event is InputEventMouseButton:
		var mb: InputEventMouseButton = event
		match mb.button_index:
			MOUSE_BUTTON_LEFT:
				_trigger = mb.pressed
				if mb.pressed:
					_press_queued = true
				else:
					_release_seen = true
			MOUSE_BUTTON_WHEEL_DOWN:
				if mb.pressed:
					state.request_wheel(1)
			MOUSE_BUTTON_WHEEL_UP:
				if mb.pressed:
					state.request_wheel(-1)


func _physics_process(_dt_s: float) -> void:
	physics_step()


## 一个物理 tick：把这段时间里的扳机边沿交给状态机，推进一个 tick。返回是否开火（测试可直接调用）。
func physics_step() -> bool:
	if cfg == null:
		return false
	if not _active():
		_trigger = false
		_press_queued = false
	if _release_seen:
		state.release_trigger()
	var fired: bool = state.tick(_trigger or _press_queued)
	_press_queued = false
	_release_seen = false
	if fired:
		_on_fire()
	return fired


func _process(dt_s: float) -> void:
	if cfg == null:
		return
	if _shown != state.current:
		_show(state.current)
	var m: Node3D = _models[_shown]
	# 拔出动画：从画面下方升起，ease-out，用时 = 拔出时长
	var drop: float = 0.0
	if state.state == WeaponState.State.DRAWING:
		var draw_s: float = float(state.weapons[_shown]["draw_s"])
		var t: float = clampf(1.0 - (state.ready_at_s - state.now_s) / maxf(draw_s, 1e-6), 0.0, 1.0)
		drop = cfg.viewmodel["draw_drop_m"] * pow(1.0 - t, 3.0)
	elif state.state == WeaponState.State.RELOADING:
		drop = cfg.viewmodel["draw_drop_m"] * 0.35
	_kick = move_toward(_kick, 0.0, cfg.viewmodel["kick_recover_mps"] * dt_s)
	m.scale = Vector3.ONE * VM_SCALE
	m.position = HIP_POS + Vector3(0, -drop, _kick)
	m.rotation_degrees = Vector3(_kick * cfg.viewmodel["kick_pitch_deg_per_m"], HIP_YAW_DEG, 0)
	_flash_left_s = maxf(_flash_left_s - dt_s, 0.0)
	_flash.light_energy = 6.0 if _flash_left_s > 0.0 else 0.0


func _show(id: String) -> void:
	for k: String in _models:
		(_models[k] as Node3D).visible = k == id
	_shown = id
	var muzzle: Node3D = (_models[id] as Node3D).get_node_or_null("Muzzle") as Node3D
	if muzzle != null and _flash != null:
		_flash.position = HIP_POS + muzzle.position * VM_SCALE


func _on_fire() -> void:
	shots += 1
	_kick = cfg.viewmodel["kick_m"]
	if int(state.weapons[state.current]["magazine"]) > 0:
		_flash_left_s = cfg.viewmodel["flash_s"]
	var cam: Camera3D = get_parent() as Camera3D
	if cam == null or not is_inside_tree():
		return
	var from: Vector3 = cam.global_position
	var to: Vector3 = from - cam.global_transform.basis.z * float(state.weapons[state.current]["range_m"])
	var q: PhysicsRayQueryParameters3D = PhysicsRayQueryParameters3D.create(from, to)
	var owner_body: CollisionObject3D = _look.get_parent() as CollisionObject3D if _look != null else null
	if owner_body != null:
		q.exclude = [owner_body.get_rid()]
	var hit: Dictionary = get_world_3d().direct_space_state.intersect_ray(q)
	if hit.is_empty():
		return
	var collider: Object = hit["collider"]
	if collider != null and collider.has_method("on_hit"):
		hits += 1
		last_hit_target = (collider as Node).name
		collider.call("on_hit")
	else:
		_spawn_mark(hit["position"], hit["normal"])


func _spawn_mark(pos: Vector3, normal: Vector3) -> void:
	var mark: MeshInstance3D = MeshInstance3D.new()
	var q: QuadMesh = QuadMesh.new()
	q.size = Vector2(0.05, 0.05)
	mark.mesh = q
	var mat: StandardMaterial3D = StandardMaterial3D.new()
	mat.albedo_color = Color(0.05, 0.05, 0.05)
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mark.material_override = mat
	get_tree().current_scene.add_child(mark)
	mark.global_position = pos + normal * 0.002
	var up: Vector3 = Vector3.UP if absf(normal.dot(Vector3.UP)) < 0.99 else Vector3.FORWARD
	mark.look_at(pos + normal, up)
	mark.rotate_object_local(Vector3.UP, PI)
	get_tree().create_timer(10.0).timeout.connect(mark.queue_free)
