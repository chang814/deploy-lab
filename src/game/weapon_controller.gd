class_name WeaponController
extends Node3D
## 武器控制（v0.2）：挂在相机下。读输入 → 驱动 WeaponState（按物理 tick 推进）→ 表现。
## 暂停（鼠标未锁定）时不响应输入。
##
## 输入：1 / 2 / 3 选槽位，Q 切到上一把，滚轮切换，左键开火（按住），右键刀重击，R 换弹，F 检视。
##
## 命中判定与 CS 一致：射线从屏幕中心（准星）射出。为了让画面和子弹方向对得上：
## - 枪管朝向「准星前方 converge_m 处」的那一点（参数见 data/weapons/weapons.json 的 viewmodel）（模型斜放在右下角，但枪口指向准星）
## - 每发子弹画一条从枪口飞到命中点的曳光
##
## 表现（只影响画面，不影响计时与命中）：转视角时的惯性摆动、走路晃动、弹簧式后坐回弹、
## 拔出（从下方带旋转升起）、换弹（下沉并侧倾）、刀的挥砍。

const HIP_POS: Vector3 = Vector3(0.19, -0.2, -0.42)    # 枪械模型在相机空间里的位置
const KNIFE_POS: Vector3 = Vector3(0.2, -0.2, -0.36)  # 刀的位置（右下）
const KNIFE_ROT_DEG: Vector3 = Vector3(8.0, 16.0, -12.0)   # 刀尖朝前偏向画面中心，略上扬，刃口朝下
const KNIFE_SCALE: float = 1.0
const VM_SCALE: float = 0.78

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
var _flash_light: OmniLight3D = null
var _flash_mesh: MeshInstance3D = null
var _trigger: bool = false
## 两个物理 tick 之间收到过「按下」/「松开」：保留边沿，避免快速点击丢失
var _press_queued: bool = false
var _release_seen: bool = false
var _sway: Vector2 = Vector2.ZERO          # (yaw, pitch) 度
var _last_look: Vector2 = Vector2.ZERO
var _bob_phase: float = 0.0
var _slash_left_s: float = 0.0
var _slash_dir: float = 1.0
var _alt_trigger: bool = false
var _alt_press_queued: bool = false
var _stab_left_s: float = 0.0
var _inspect_left_s: float = 0.0
## 命中标记剩余显示时间（准星处的 X，crosshair.gd 读取）
var hit_marker_left_s: float = 0.0
var _players: Array[AudioStreamPlayer] = []
var _next_player: int = 0
var _last_reload_p: float = -1.0


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
	_flash_light = OmniLight3D.new()
	_flash_light.light_color = Color(1.0, 0.7, 0.35)
	_flash_light.light_energy = 0.0
	_flash_light.omni_range = 4.0
	add_child(_flash_light)
	_flash_mesh = MeshInstance3D.new()
	var q: SphereMesh = SphereMesh.new()
	q.radius = 0.028
	q.height = 0.056
	_flash_mesh.mesh = q
	var fm: StandardMaterial3D = StandardMaterial3D.new()
	fm.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	fm.albedo_color = Color(1.0, 0.75, 0.3, 0.9)
	fm.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	_flash_mesh.material_override = fm
	_flash_mesh.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	_flash_mesh.visible = false
	add_child(_flash_mesh)
	for i: int in 8:
		var ap: AudioStreamPlayer = AudioStreamPlayer.new()
		add_child(ap)
		_players.append(ap)
	_show(state.current)


## 播放一个合成音效（轮流使用 8 个播放器，可以叠在一起）。
func play_sfx(kind: String, volume_db: float = 0.0, pitch_jitter: float = 0.04) -> void:
	if _players.is_empty() or not is_inside_tree():
		return
	var ap: AudioStreamPlayer = _players[_next_player]
	_next_player = (_next_player + 1) % _players.size()
	ap.stream = Sfx.get_stream(kind)
	ap.volume_db = volume_db + linear_to_db(maxf(cfg.viewmodel["sfx_gain"], 1e-4))
	ap.pitch_scale = 1.0 + randf_range(-pitch_jitter, pitch_jitter)
	ap.play()


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
			KEY_F: start_inspect()
	elif event is InputEventMouseButton:
		var mb: InputEventMouseButton = event
		match mb.button_index:
			MOUSE_BUTTON_LEFT:
				_trigger = mb.pressed
				if mb.pressed:
					_press_queued = true
				else:
					_release_seen = true
			MOUSE_BUTTON_RIGHT:
				_alt_trigger = mb.pressed
				if mb.pressed:
					_alt_press_queued = true
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
		_alt_trigger = false
		_alt_press_queued = false
	if _release_seen:
		state.release_trigger()
	var fired: bool = state.tick(_trigger or _press_queued, _alt_trigger or _alt_press_queued)
	_press_queued = false
	_alt_press_queued = false
	_release_seen = false
	if fired:
		_on_fire()
	return fired


## 枪械的基础姿态：位于 HIP_POS，枪管（-Z）指向准星前方 converge_m 处。
static func aim_basis(converge_m: float) -> Basis:
	var target: Vector3 = Vector3(0.0, 0.0, -converge_m)
	return Basis.looking_at((target - HIP_POS).normalized(), Vector3.UP)


func _process(dt_s: float) -> void:
	if cfg == null:
		return
	if _shown != state.current:
		_show(state.current)
	var m: Node3D = _models[_shown]
	var is_knife: bool = int(state.weapons[_shown]["magazine"]) == 0
	var vm: Dictionary = cfg.viewmodel

	# 惯性摆动：模型滞后于视角转动，然后弹回
	if _look != null:
		var now_look: Vector2 = Vector2(_look.yaw_deg, _look.pitch_deg)
		var d: Vector2 = now_look - _last_look
		_last_look = now_look
		_sway += Vector2(-d.x, d.y) * vm["sway_deg_per_deg"]
		_sway = _sway.limit_length(vm["sway_max_deg"])
	_sway = _sway.lerp(Vector2.ZERO, 1.0 - exp(-vm["sway_return_per_s"] * dt_s))

	# 走路晃动：按水平速度推进相位
	var speed_mps: float = 0.0
	var body: CharacterBody3D = _look.get_parent() as CharacterBody3D if _look != null else null
	if body != null and body.is_inside_tree() and body.is_on_floor():
		speed_mps = Vector2(body.velocity.x, body.velocity.z).length()
	_bob_phase += speed_mps * vm["bob_freq_per_m"] * TAU * dt_s
	var bob_k: float = clampf(speed_mps / 6.35, 0.0, 1.0)
	var bob: Vector3 = Vector3(sin(_bob_phase) * vm["bob_x_m"], -absf(cos(_bob_phase)) * vm["bob_y_m"], 0.0) * bob_k

	# 后坐：弹簧式回弹
	_kick = _kick * exp(-vm["kick_return_per_s"] * dt_s)

	# 拔出 / 换弹
	var anim_pos: Vector3 = Vector3.ZERO
	var anim_rot: Vector3 = Vector3.ZERO
	if state.state == WeaponState.State.DRAWING:
		var draw_s: float = float(state.weapons[_shown]["draw_s"])
		# 升起动画在拔出时长的前 draw_anim_fraction 内完成，之后端平等待可以开火（开火时刻不变）
		var t: float = clampf((1.0 - (state.ready_at_s - state.now_s) / maxf(draw_s, 1e-6)) / maxf(vm["draw_anim_fraction"], 1e-6), 0.0, 1.0)
		var k: float = pow(1.0 - t, 3.0)
		anim_pos = Vector3(0.03 * k, -cfg.viewmodel["draw_drop_m"] * k, 0.0)
		anim_rot = Vector3(-35.0 * k, 0.0, 20.0 * k)
	var parts: Dictionary = {}
	if state.state == WeaponState.State.RELOADING:
		var reload_s: float = float(state.weapons[_shown]["reload_s"])
		var p: float = clampf(1.0 - (state.reload_done_s - state.now_s) / maxf(reload_s, 1e-6), 0.0, 1.0)
		var r: Dictionary = reload_pose(p, _shown)
		anim_pos = r["gun"][0]
		anim_rot = r["gun"][1]
		parts = r
		_reload_sounds(_last_reload_p, p, _shown)
		_last_reload_p = p
	else:
		_last_reload_p = -1.0
	_apply_parts(m, parts)

	# 刀：轻击（左右交替的斜劈）、重击（蓄力后前刺）；检视（F）
	var slash_rot: Vector3 = Vector3.ZERO
	var slash_pos: Vector3 = Vector3.ZERO
	if _slash_left_s > 0.0:
		_slash_left_s = maxf(_slash_left_s - dt_s, 0.0)
		var s: float = 1.0 - _slash_left_s / maxf(vm["slash_s"], 1e-6)
		var pose: Array = slash_pose(s, _slash_dir)
		slash_pos = pose[0]
		slash_rot = pose[1]
	elif _stab_left_s > 0.0:
		_stab_left_s = maxf(_stab_left_s - dt_s, 0.0)
		var pose: Array = stab_pose(1.0 - _stab_left_s / maxf(vm["stab_s"], 1e-6))
		slash_pos = pose[0]
		slash_rot = pose[1]
	if state.state != WeaponState.State.READY:
		_inspect_left_s = 0.0
	if _inspect_left_s > 0.0:
		_inspect_left_s = maxf(_inspect_left_s - dt_s, 0.0)
		var total_s: float = vm["inspect_knife_s"] if is_knife else vm["inspect_gun_s"]
		var pose: Array = inspect_pose(1.0 - _inspect_left_s / maxf(total_s, 1e-6), is_knife)
		slash_pos += pose[0]
		slash_rot += pose[1]

	var base_pos: Vector3 = KNIFE_POS if is_knife else HIP_POS
	var base_basis: Basis = Basis.from_euler(KNIFE_ROT_DEG * PI / 180.0) if is_knife else aim_basis(vm["converge_m"])
	var offset_rot: Vector3 = (anim_rot + slash_rot + Vector3(_sway.y + _kick * cfg.viewmodel["kick_pitch_deg_per_m"], _sway.x, 0.0)) * PI / 180.0
	m.transform = Transform3D(base_basis * Basis.from_euler(offset_rot), base_pos + anim_pos + slash_pos + bob + Vector3(0.0, 0.0, _kick))
	m.scale = Vector3.ONE * (KNIFE_SCALE if is_knife else VM_SCALE)

	hit_marker_left_s = maxf(hit_marker_left_s - dt_s, 0.0)
	_flash_left_s = maxf(_flash_left_s - dt_s, 0.0)
	_flash_light.light_energy = 6.0 if _flash_left_s > 0.0 else 0.0
	_flash_mesh.visible = _flash_left_s > 0.0
	var muzzle: Node3D = m.get_node_or_null("Muzzle") as Node3D
	if muzzle != null:
		var mp: Vector3 = m.transform * muzzle.position
		_flash_light.position = mp
		_flash_mesh.position = mp


func _show(id: String) -> void:
	for k: String in _models:
		(_models[k] as Node3D).visible = k == id
	_shown = id
	_slash_left_s = 0.0
	_stab_left_s = 0.0
	_inspect_left_s = 0.0


## 换弹动作（关键帧）。返回 {"gun": [位置, 旋转], "mag": 位置偏移, "arm": 位置偏移, "bolt": 位置偏移}。
## 步枪：枪向右下倾斜 → 左手去拿弹匣、弹匣拔出掉落 → 左手带新弹匣上来插入 → 左手回护木 → 拉枪栓 → 复位。
## 手枪：弹匣从握把下方掉出 → 新弹匣插入 → 套筒复位。
static func reload_pose(p: float, id: String) -> Dictionary:
	if id == "pistol":
		var g: Array = keyframes(p, [
			[0.0, Vector3.ZERO, Vector3.ZERO],
			[0.15, Vector3(-0.02, 0.02, 0.0), Vector3(15.0, 10.0, 20.0)],
			[0.8, Vector3(-0.02, 0.02, 0.0), Vector3(15.0, 10.0, 20.0)],
			[1.0, Vector3.ZERO, Vector3.ZERO],
		])
		var mag: Vector3 = keyframes(p, [
			[0.0, Vector3.ZERO, Vector3.ZERO], [0.18, Vector3.ZERO, Vector3.ZERO],
			[0.35, Vector3(0.0, -0.35, 0.05), Vector3.ZERO], [0.45, Vector3(0.0, -0.18, 0.0), Vector3.ZERO],
			[0.62, Vector3.ZERO, Vector3.ZERO], [1.0, Vector3.ZERO, Vector3.ZERO]])[0]
		var arm: Vector3 = keyframes(p, [
			[0.0, Vector3.ZERO, Vector3.ZERO], [0.3, Vector3(0.0, -0.12, 0.04), Vector3.ZERO],
			[0.45, Vector3(0.0, -0.13, 0.0), Vector3.ZERO], [0.62, Vector3(0.0, -0.02, 0.0), Vector3.ZERO],
			[0.8, Vector3.ZERO, Vector3.ZERO], [1.0, Vector3.ZERO, Vector3.ZERO]])[0]
		var slide: Vector3 = keyframes(p, [
			[0.0, Vector3.ZERO, Vector3.ZERO], [0.68, Vector3.ZERO, Vector3.ZERO],
			[0.74, Vector3(0.0, 0.0, 0.035), Vector3.ZERO], [0.8, Vector3.ZERO, Vector3.ZERO],
			[1.0, Vector3.ZERO, Vector3.ZERO]])[0]
		return {"gun": g, "mag": mag, "arm": arm, "bolt": slide}
	var gun: Array = keyframes(p, [
		[0.0, Vector3.ZERO, Vector3.ZERO],
		[0.12, Vector3(-0.03, 0.03, 0.02), Vector3(10.0, 8.0, 30.0)],
		[0.62, Vector3(-0.03, 0.03, 0.02), Vector3(12.0, 8.0, 32.0)],
		[0.7, Vector3(0.0, 0.02, 0.02), Vector3(6.0, -6.0, -12.0)],
		[0.86, Vector3(0.0, 0.02, 0.02), Vector3(6.0, -6.0, -12.0)],
		[1.0, Vector3.ZERO, Vector3.ZERO],
	])
	var mag2: Vector3 = keyframes(p, [
		[0.0, Vector3.ZERO, Vector3.ZERO], [0.16, Vector3.ZERO, Vector3.ZERO],
		[0.22, Vector3(0.0, -0.04, 0.03), Vector3.ZERO],
		[0.34, Vector3(0.0, -0.45, 0.1), Vector3.ZERO],
		[0.36, Vector3(-0.05, -0.4, 0.15), Vector3.ZERO],
		[0.5, Vector3(0.0, -0.06, 0.02), Vector3.ZERO],
		[0.56, Vector3.ZERO, Vector3.ZERO],
		[1.0, Vector3.ZERO, Vector3.ZERO]])[0]
	var arm2: Vector3 = keyframes(p, [
		[0.0, Vector3.ZERO, Vector3.ZERO],
		[0.14, Vector3(0.0, -0.02, 0.13), Vector3.ZERO],
		[0.22, Vector3(0.0, -0.06, 0.16), Vector3.ZERO],
		[0.34, Vector3(-0.05, -0.38, 0.22), Vector3.ZERO],
		[0.5, Vector3(0.0, -0.07, 0.16), Vector3.ZERO],
		[0.56, Vector3(0.0, -0.02, 0.14), Vector3.ZERO],
		[0.66, Vector3.ZERO, Vector3.ZERO],
		[1.0, Vector3.ZERO, Vector3.ZERO]])[0]
	var bolt2: Vector3 = keyframes(p, [
		[0.0, Vector3.ZERO, Vector3.ZERO], [0.72, Vector3.ZERO, Vector3.ZERO],
		[0.78, Vector3(0.0, 0.0, 0.07), Vector3.ZERO],
		[0.82, Vector3.ZERO, Vector3.ZERO],
		[1.0, Vector3.ZERO, Vector3.ZERO]])[0]
	return {"gun": gun, "mag": mag2, "arm": arm2, "bolt": bolt2}


## 把换弹动作的部件偏移应用到模型（不在换弹时全部回到原位）。
func _apply_parts(m: Node3D, parts: Dictionary) -> void:
	for pair: Array in [["Mag", "mag"], ["LeftArm", "arm"], ["Bolt", "bolt"], ["Slide", "bolt"]]:
		var n: Node3D = m.get_node_or_null(String(pair[0])) as Node3D
		if n != null and n.has_meta("rest_position"):
			n.position = (n.get_meta("rest_position") as Vector3) + (parts.get(pair[1], Vector3.ZERO) as Vector3)


## 换弹过程中，进度越过这些点时播放卡扣声。
func _reload_sounds(prev_p: float, p: float, id: String) -> void:
	var cues: Array = [[0.2, "mag_out"], [0.55, "mag_in"], [0.77, "bolt"]]
	if id == "pistol":
		cues = [[0.22, "mag_out"], [0.6, "mag_in"], [0.74, "bolt"]]
	for c: Array in cues:
		if prev_p < float(c[0]) and p >= float(c[0]):
			play_sfx(String(c[1]), -4.0)


## 检视（F）：就绪时开始；开火、切枪、换弹都会打断。
func start_inspect() -> void:
	if cfg == null or not state.is_ready() or _slash_left_s > 0.0 or _stab_left_s > 0.0:
		return
	var is_knife: bool = int(state.weapons[state.current]["magazine"]) == 0
	_inspect_left_s = cfg.viewmodel["inspect_knife_s"] if is_knife else cfg.viewmodel["inspect_gun_s"]


## 关键帧插值：keys = [[t, 位置, 旋转(度)], …]，t 从 0 到 1 递增；段内用 smoothstep。返回 [位置, 旋转]。
static func keyframes(p: float, keys: Array) -> Array:
	p = clampf(p, 0.0, 1.0)
	for i: int in range(1, keys.size()):
		if p <= float(keys[i][0]):
			var a: Array = keys[i - 1]
			var b: Array = keys[i]
			var u: float = smoothstep(0.0, 1.0, (p - float(a[0])) / maxf(float(b[0]) - float(a[0]), 1e-6))
			return [(a[1] as Vector3).lerp(b[1], u), (a[2] as Vector3).lerp(b[2], u)]
	return [keys[-1][1], keys[-1][2]]


## 轻击：用刀刃切。dir = 1 正手从右上劈到左下，刃口（模型 -Y）转向左下（绕刀身轴 -45°）；
## dir = -1 反手翻腕，刃口转向右上（+135°），从左下划回右上。首尾回到持刀姿势。
static func slash_pose(s: float, dir: float) -> Array:
	var roll: float = -45.0 if dir > 0.0 else 135.0
	return keyframes(s, [
		[0.0, Vector3.ZERO, Vector3.ZERO],
		[0.2, Vector3(0.05 * dir, 0.05 * dir, 0.02), Vector3(8.0 * dir, -14.0 * dir, roll)],
		[0.55, Vector3(-0.12 * dir, -0.05 * dir, -0.08), Vector3(-10.0 * dir, 24.0 * dir, roll)],
		[1.0, Vector3.ZERO, Vector3.ZERO],
	])


## 重击：向后蓄力，再向前猛刺，收回。
static func stab_pose(s: float) -> Array:
	return keyframes(s, [
		[0.0, Vector3.ZERO, Vector3.ZERO],
		[0.35, Vector3(0.02, 0.04, 0.08), Vector3(-10.0, -8.0, 20.0)],
		[0.55, Vector3(-0.08, 0.04, -0.24), Vector3(-26.0, 12.0, 20.0)],
		[0.7, Vector3(-0.08, 0.04, -0.24), Vector3(-26.0, 12.0, 20.0)],
		[1.0, Vector3.ZERO, Vector3.ZERO],
	])


## 检视：刀拿到面前亮出刀面，翻到另一面，再收回；枪侧过来展示右侧，再收回。
static func inspect_pose(p: float, is_knife: bool) -> Array:
	if is_knife:
		return keyframes(p, [
			[0.0, Vector3.ZERO, Vector3.ZERO],
			[0.15, Vector3(-0.08, 0.05, -0.05), Vector3(-15.0, 60.0, -10.0)],
			[0.45, Vector3(-0.08, 0.05, -0.05), Vector3(-10.0, 72.0, -10.0)],
			[0.6, Vector3(-0.07, 0.06, -0.05), Vector3(-10.0, 72.0, 170.0)],
			[0.85, Vector3(-0.07, 0.06, -0.05), Vector3(-15.0, 68.0, 180.0)],
			[1.0, Vector3.ZERO, Vector3(0.0, 0.0, 360.0)],
		])
	return keyframes(p, [
		[0.0, Vector3.ZERO, Vector3.ZERO],
		[0.2, Vector3(-0.06, 0.04, 0.03), Vector3(5.0, 35.0, -30.0)],
		[0.75, Vector3(-0.06, 0.05, 0.03), Vector3(8.0, 40.0, -35.0)],
		[1.0, Vector3.ZERO, Vector3.ZERO],
	])


func _on_fire() -> void:
	shots += 1
	var is_knife: bool = int(state.weapons[state.current]["magazine"]) == 0
	_inspect_left_s = 0.0
	if is_knife and state.last_fire_alt:
		_stab_left_s = cfg.viewmodel["stab_s"]
		_slash_left_s = 0.0
		play_sfx("swish", -2.0, 0.08)
	elif is_knife:
		_slash_left_s = cfg.viewmodel["slash_s"]
		_stab_left_s = 0.0
		_slash_dir = -_slash_dir
		play_sfx("swish", -4.0, 0.12)
	else:
		play_sfx(state.current if state.current in ["rifle", "pistol"] else "rifle", -2.0, 0.03)
		_kick = cfg.viewmodel["kick_m"]
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
	var end: Vector3 = to if hit.is_empty() else hit["position"]
	if not is_knife:
		_spawn_tracer(end)
	if hit.is_empty():
		return
	var collider: Object = hit["collider"]
	var shot_dir: Vector3 = (to - from).normalized()
	if collider != null and collider.has_method("on_hit"):
		hits += 1
		last_hit_target = (collider as Node).name
		collider.call("on_hit", shot_dir)
		hit_marker_left_s = 0.15
		play_sfx("hit", -6.0, 0.02)
		_spawn_impact(hit["position"], hit["normal"], true)
	elif not is_knife:
		_spawn_mark(hit["position"], hit["normal"])
		_spawn_impact(hit["position"], hit["normal"], false)


## 命中特效：打在靶子上是火花（亮橙），打在墙和地面上是碎屑（灰褐）。一次性粒子，1 秒后删除。
func _spawn_impact(pos: Vector3, normal: Vector3, on_target: bool) -> void:
	var ps: CPUParticles3D = CPUParticles3D.new()
	ps.one_shot = true
	ps.explosiveness = 0.95
	ps.amount = 10 if on_target else 14
	ps.lifetime = 0.35 if on_target else 0.6
	ps.direction = normal
	ps.spread = 40.0
	ps.initial_velocity_min = 2.0 if on_target else 1.0
	ps.initial_velocity_max = 4.5 if on_target else 2.5
	ps.gravity = Vector3(0, -9.8, 0)
	ps.scale_amount_min = 0.6
	ps.scale_amount_max = 1.2
	var mesh: BoxMesh = BoxMesh.new()
	mesh.size = Vector3.ONE * (0.012 if on_target else 0.02)
	var mat: StandardMaterial3D = StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED if on_target else BaseMaterial3D.SHADING_MODE_PER_PIXEL
	mat.albedo_color = Color(1.0, 0.7, 0.3) if on_target else Color(0.55, 0.5, 0.42)
	mesh.material = mat
	ps.mesh = mesh
	get_tree().current_scene.add_child(ps)
	ps.global_position = pos + normal * 0.01
	ps.emitting = true
	get_tree().create_timer(1.0).timeout.connect(ps.queue_free)


## 曳光：从枪口到命中点的一条细亮线，很快消失。
func _spawn_tracer(end: Vector3) -> void:
	var m: Node3D = _models[_shown]
	var muzzle: Node3D = m.get_node_or_null("Muzzle") as Node3D
	if muzzle == null:
		return
	var start: Vector3 = m.global_transform * muzzle.position
	var length: float = start.distance_to(end)
	if length < 0.05:
		return
	var tracer: MeshInstance3D = MeshInstance3D.new()
	var mesh: BoxMesh = BoxMesh.new()
	mesh.size = Vector3(0.006, 0.006, length)
	tracer.mesh = mesh
	var mat: StandardMaterial3D = StandardMaterial3D.new()
	mat.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
	mat.albedo_color = Color(1.0, 0.88, 0.55, 0.35)
	mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	tracer.material_override = mat
	tracer.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	get_tree().current_scene.add_child(tracer)
	tracer.global_position = (start + end) / 2.0
	tracer.look_at(end, Vector3.UP if absf((end - start).normalized().dot(Vector3.UP)) < 0.99 else Vector3.FORWARD)
	get_tree().create_timer(cfg.viewmodel["tracer_s"]).timeout.connect(tracer.queue_free)


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
