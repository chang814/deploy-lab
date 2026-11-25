extends Node3D
## P0-4 原始鼠标输入验证。
## 1) 统计鼠标原始位移（relative 与 screen_relative 两路），用来检验是否等于物理计数；
## 2) 按规格公式驱动第一人称视角，并在四周每 10° 放一根标柱，用来和 CS2 做 360° 对照。

const LookMath = preload("res://look_math.gd")

const PITCH_MIN_DEG: float = -89.0
const PITCH_MAX_DEG: float = 89.0
const BASE_HFOV_4X3_DEG: float = 90.0
const PILLAR_RADIUS_M: float = 20.0
const EYE_HEIGHT_M: float = 1.7
const LOG_PATH: String = "user://spike_runs.csv"

var dpi: float = 800.0
var sensitivity: float = 1.0

# 计数（float64 累积，不取整）
var sum_rel: Vector2 = Vector2.ZERO
var sum_screen: Vector2 = Vector2.ZERO
var event_count: int = 0
var fractional_event_count: int = 0
var mismatch_event_count: int = 0
var max_abs_dx: float = 0.0

# 视角：yaw 不回绕，向右转为正；pitch 向上为正
var yaw_deg: float = 0.0
var pitch_deg: float = 0.0

var _camera: Camera3D
var _info: Label
var _settings: HBoxContainer


func _ready() -> void:
	Input.use_accumulated_input = false
	_build_world()
	_build_ui()
	_set_captured(false)


func _input(event: InputEvent) -> void:
	if Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
		return
	var motion: InputEventMouseMotion = event as InputEventMouseMotion
	if motion == null:
		return
	var rel: Vector2 = motion.relative
	var scr: Vector2 = motion.screen_relative
	sum_rel += rel
	sum_screen += scr
	event_count += 1
	if not _is_integer(scr.x) or not _is_integer(scr.y):
		fractional_event_count += 1
	if rel != scr:
		mismatch_event_count += 1
	max_abs_dx = maxf(max_abs_dx, absf(scr.x))

	yaw_deg += LookMath.delta_deg(scr.x, sensitivity, LookMath.M_YAW_DEFAULT_DEG)
	pitch_deg = LookMath.apply_pitch(
		pitch_deg,
		-LookMath.delta_deg(scr.y, sensitivity, LookMath.M_PITCH_DEFAULT_DEG),
		PITCH_MIN_DEG,
		PITCH_MAX_DEG
	)
	_apply_camera()


func _unhandled_input(event: InputEvent) -> void:
	var key: InputEventKey = event as InputEventKey
	if key == null or not key.pressed or key.echo:
		return
	match key.keycode:
		KEY_C:
			_set_captured(true)
		KEY_ESCAPE:
			_set_captured(false)
		KEY_R:
			_reset_counters()
		KEY_Z:
			_reset_counters()
			yaw_deg = 0.0
			pitch_deg = 0.0
			_apply_camera()
		KEY_L:
			_log_run()
		KEY_F:
			var mode: DisplayServer.WindowMode = DisplayServer.window_get_mode()
			if mode == DisplayServer.WINDOW_MODE_EXCLUSIVE_FULLSCREEN:
				DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED)
			else:
				DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_EXCLUSIVE_FULLSCREEN)


func _process(_delta: float) -> void:
	var size: Vector2i = get_viewport().get_visible_rect().size
	var aspect: float = float(size.x) / float(size.y)
	var vfov: float = _camera.fov
	var captured: bool = Input.mouse_mode == Input.MOUSE_MODE_CAPTURED
	var lines: PackedStringArray = [
		"FPS %d   垂直同步 %s   视口 %d×%d（%.4f）   hfov %.4f°   vfov %.4f°" % [
			Engine.get_frames_per_second(),
			"关" if DisplayServer.window_get_vsync_mode() == DisplayServer.VSYNC_DISABLED else "开",
			size.x, size.y, aspect, LookMath.hfov_from_vfov(vfov, aspect), vfov,
		],
		"鼠标：%s" % ("已锁定（Esc 释放）" if captured else "未锁定（按 C 锁定开始测试）"),
		"",
		"事件数 %d   非整数事件 %d   relative≠screen_relative 的事件 %d   单事件最大 |dx| %.0f" % [
			event_count, fractional_event_count, mismatch_event_count, max_abs_dx,
		],
		"累计 X：%.3f counts   累计 Y：%.3f counts   （relative 路：X %.3f  Y %.3f）" % [
			sum_screen.x, sum_screen.y, sum_rel.x, sum_rel.y,
		],
		"按 DPI %.0f 换算水平位移：%.3f cm" % [dpi, sum_screen.x / dpi * LookMath.CM_PER_INCH],
		"",
		"yaw（不回绕）%.4f°   = %.5f 圈   pitch %.3f°" % [yaw_deg, yaw_deg / 360.0, pitch_deg],
		"灵敏度 %.3f   理论 %.2f counts/360°   %.3f cm/360°" % [
			sensitivity,
			LookMath.counts_per_360(sensitivity, LookMath.M_YAW_DEFAULT_DEG),
			LookMath.cm_per_360(dpi, sensitivity, LookMath.M_YAW_DEFAULT_DEG),
		],
		"",
		"C 锁定 · Esc 释放 · R 清零计数 · Z 清零计数并回正视角 · L 记录本次到 CSV · F 全屏切换",
		"记录文件：%s" % ProjectSettings.globalize_path(LOG_PATH),
	]
	_info.text = "\n".join(lines)
	_settings.visible = not captured


func _set_captured(captured: bool) -> void:
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if captured else Input.MOUSE_MODE_VISIBLE


func _reset_counters() -> void:
	sum_rel = Vector2.ZERO
	sum_screen = Vector2.ZERO
	event_count = 0
	fractional_event_count = 0
	mismatch_event_count = 0
	max_abs_dx = 0.0


func _apply_camera() -> void:
	_camera.rotation = Vector3(deg_to_rad(pitch_deg), -deg_to_rad(yaw_deg), 0.0)


func _is_integer(v: float) -> bool:
	return v == floorf(v)


func _log_run() -> void:
	var is_new: bool = not FileAccess.file_exists(LOG_PATH)
	var f: FileAccess = FileAccess.open(LOG_PATH, FileAccess.READ_WRITE if not is_new else FileAccess.WRITE)
	if f == null:
		push_error("无法写入 %s" % LOG_PATH)
		return
	f.seek_end()
	if is_new:
		f.store_line("time,dpi,sens,counts_x,counts_y,rel_x,rel_y,events,fractional,mismatch,cm_x,yaw_deg,pitch_deg,window_mode")
	f.store_line("%s,%.0f,%.4f,%.3f,%.3f,%.3f,%.3f,%d,%d,%d,%.4f,%.4f,%.4f,%d" % [
		Time.get_datetime_string_from_system(), dpi, sensitivity,
		sum_screen.x, sum_screen.y, sum_rel.x, sum_rel.y,
		event_count, fractional_event_count, mismatch_event_count,
		sum_screen.x / dpi * LookMath.CM_PER_INCH, yaw_deg, pitch_deg,
		DisplayServer.window_get_mode(),
	])
	f.close()
	print("已记录一次：", ProjectSettings.globalize_path(LOG_PATH))


func _build_world() -> void:
	var env: Environment = Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.10, 0.11, 0.13)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.55, 0.55, 0.58)
	var world_env: WorldEnvironment = WorldEnvironment.new()
	world_env.environment = env
	add_child(world_env)

	var sun: DirectionalLight3D = DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55.0, 35.0, 0.0)
	add_child(sun)

	var floor_mesh: PlaneMesh = PlaneMesh.new()
	floor_mesh.size = Vector2(120.0, 120.0)
	var floor_node: MeshInstance3D = MeshInstance3D.new()
	floor_node.mesh = floor_mesh
	floor_node.material_override = _flat_material(Color(0.22, 0.23, 0.25))
	add_child(floor_node)

	# 每 10° 一根标柱：0° 红色最高，90° 倍数白色，30° 倍数浅灰带角度数字，其余深灰
	for i: int in 36:
		var angle_deg: float = i * 10.0
		var a: float = deg_to_rad(angle_deg)
		var height: float = 1.5
		var color: Color = Color(0.35, 0.36, 0.40)
		if i % 3 == 0:
			height = 3.0
			color = Color(0.70, 0.72, 0.76)
		if i % 9 == 0:
			height = 5.0
			color = Color(0.95, 0.95, 0.95)
		if i == 0:
			height = 7.0
			color = Color(0.90, 0.20, 0.20)
		var box: BoxMesh = BoxMesh.new()
		box.size = Vector3(0.25, height, 0.25)
		var pillar: MeshInstance3D = MeshInstance3D.new()
		pillar.mesh = box
		pillar.material_override = _flat_material(color)
		# 向右转 a 时的前方：(sin a, 0, -cos a)
		pillar.position = Vector3(sin(a), 0.0, -cos(a)) * PILLAR_RADIUS_M + Vector3(0.0, height / 2.0, 0.0)
		add_child(pillar)
		if i % 3 == 0:
			var label: Label3D = Label3D.new()
			label.text = "%d°" % int(angle_deg)
			label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
			label.font_size = 96
			label.position = pillar.position + Vector3(0.0, height / 2.0 + 0.6, 0.0)
			add_child(label)

	_camera = Camera3D.new()
	_camera.keep_aspect = Camera3D.KEEP_HEIGHT
	_camera.fov = LookMath.vfov_from_hfov(BASE_HFOV_4X3_DEG, 4.0 / 3.0)
	_camera.position = Vector3(0.0, EYE_HEIGHT_M, 0.0)
	_camera.rotation_order = EULER_ORDER_YXZ
	add_child(_camera)
	_camera.make_current()
	_apply_camera()


func _build_ui() -> void:
	var layer: CanvasLayer = CanvasLayer.new()
	add_child(layer)

	# 面板放左下角，不遮挡地平线上的标柱
	var panel: PanelContainer = PanelContainer.new()
	layer.add_child(panel)
	panel.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT, Control.PRESET_MODE_MINSIZE, 12)
	panel.grow_vertical = Control.GROW_DIRECTION_BEGIN
	var box: VBoxContainer = VBoxContainer.new()
	panel.add_child(box)

	_info = Label.new()
	box.add_child(_info)

	_settings = HBoxContainer.new()
	box.add_child(_settings)
	_settings.add_child(_label("DPI"))
	var dpi_box: SpinBox = SpinBox.new()
	dpi_box.min_value = 50.0
	dpi_box.max_value = 32000.0
	dpi_box.step = 1.0
	dpi_box.value = dpi
	dpi_box.value_changed.connect(func(v: float) -> void: dpi = v)
	_settings.add_child(dpi_box)
	_settings.add_child(_label("   灵敏度（与 CS2 相同）"))
	var sens_box: SpinBox = SpinBox.new()
	sens_box.min_value = 0.01
	sens_box.max_value = 20.0
	sens_box.step = 0.001
	sens_box.value = sensitivity
	sens_box.value_changed.connect(func(v: float) -> void: sensitivity = v)
	_settings.add_child(sens_box)

	# 屏幕中心准星（2px 十字）
	var center: CenterContainer = CenterContainer.new()
	center.set_anchors_preset(Control.PRESET_FULL_RECT)
	center.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(center)
	var cross: Control = Control.new()
	cross.custom_minimum_size = Vector2(20.0, 20.0)
	cross.mouse_filter = Control.MOUSE_FILTER_IGNORE
	center.add_child(cross)
	var h: ColorRect = ColorRect.new()
	h.color = Color(0.2, 1.0, 0.3)
	h.position = Vector2(0.0, 9.0)
	h.size = Vector2(20.0, 2.0)
	cross.add_child(h)
	var v: ColorRect = ColorRect.new()
	v.color = Color(0.2, 1.0, 0.3)
	v.position = Vector2(9.0, 0.0)
	v.size = Vector2(2.0, 20.0)
	cross.add_child(v)


func _label(text: String) -> Label:
	var l: Label = Label.new()
	l.text = text
	return l


func _flat_material(color: Color) -> StandardMaterial3D:
	var m: StandardMaterial3D = StandardMaterial3D.new()
	m.albedo_color = color
	m.roughness = 1.0
	return m
