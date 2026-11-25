extends Node3D
## P0-4 原始鼠标输入验证。
## 1) 按「轮」统计 Godot 收到的鼠标位移（relative 与 screen_relative 两路），
##    与独立的 Windows Raw Input 计数器（tools/rawinput_counter.py）逐轮对比；
## 2) 按规格公式驱动第一人称视角，四周每 10° 一根标柱，用来和 CS2 做 360° 对照。
##
## 一轮的边界只由鼠标按键决定，基准计数器会收到同一次点击：
##   鼠标中键 = 开始新一轮（两边清零）；鼠标右键 = 结束本轮并记录（两边各写一行 CSV）。
## Godot 这边不会单方面开新轮。释放鼠标、窗口失焦、按 Z 回正视角，都只会把本轮标为「作废」，
## 因为这些情况下基准仍在计数而 Godot 没有，或者 yaw 基准被改动。作废轮照常记录，但带标记。

const LookMath = preload("res://look_math.gd")

# 场景布置参数（不是手感参数）
const PILLAR_RADIUS_M: float = 20.0
const EYE_HEIGHT_M: float = 1.7
const DEFAULT_LOG_PATH: String = "user://spike_runs.csv"
# 可用启动参数覆盖：godot --path <工程目录> -- --log=<CSV 完整路径>
var log_path: String = DEFAULT_LOG_PATH

var dpi: float = 800.0
var sensitivity: float = 1.0

# 手感参数，来自 data/look_defaults.json
var m_yaw_deg: float = NAN
var m_pitch_deg: float = NAN
var pitch_min_deg: float = NAN
var pitch_max_deg: float = NAN
var base_hfov_4x3_deg: float = NAN

# 本轮计数：一律用标量 float（64 位）。Vector2 是 32 位，不能用来累计。
var round_screen_x: float = 0.0
var round_screen_y: float = 0.0
var round_rel_x: float = 0.0
var round_rel_y: float = 0.0
var round_events: int = 0
var round_fractional_events: int = 0
var round_mismatch_events: int = 0
var round_max_abs_dx: float = 0.0
var round_index: int = 0
var round_yaw_start_deg: float = 0.0
var round_invalid_reason: String = ""  # 空字符串 = 有效

# 视角：yaw 不回绕，向右转为正；pitch 向上为正
var yaw_deg: float = 0.0
var pitch_deg: float = 0.0

var _camera: Camera3D
var _info: Label
var _settings: HBoxContainer
var _note: LineEdit
var _last_log_line: String = "（尚未记录）"


func _ready() -> void:
	Input.use_accumulated_input = false
	for arg: String in OS.get_cmdline_user_args():
		if arg.begins_with("--log="):
			log_path = arg.trim_prefix("--log=")
			DirAccess.make_dir_recursive_absolute(log_path.get_base_dir())
	var d: Dictionary = LookMath.load_defaults()
	if d.is_empty():
		get_tree().quit(1)
		return
	m_yaw_deg = d["m_yaw_deg"]
	m_pitch_deg = d["m_pitch_deg"]
	pitch_min_deg = d["pitch_min_deg"]
	pitch_max_deg = d["pitch_max_deg"]
	base_hfov_4x3_deg = d["base_hfov_4x3_deg"]
	_build_world()
	_build_ui()
	_set_captured(false)


func _input(event: InputEvent) -> void:
	if Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
		return
	var button: InputEventMouseButton = event as InputEventMouseButton
	if button != null and button.pressed:
		if button.button_index == MOUSE_BUTTON_MIDDLE:
			_start_round()
		elif button.button_index == MOUSE_BUTTON_RIGHT:
			_log_round()
		return
	var motion: InputEventMouseMotion = event as InputEventMouseMotion
	if motion == null:
		return
	var rel_x: float = motion.relative.x
	var rel_y: float = motion.relative.y
	var scr_x: float = motion.screen_relative.x
	var scr_y: float = motion.screen_relative.y
	round_screen_x += scr_x
	round_screen_y += scr_y
	round_rel_x += rel_x
	round_rel_y += rel_y
	round_events += 1
	# 诊断项，不是通过/失败判据：小数说明数据经过缩放；两路不一致说明存在视口缩放
	if scr_x != floorf(scr_x) or scr_y != floorf(scr_y):
		round_fractional_events += 1
	if rel_x != scr_x or rel_y != scr_y:
		round_mismatch_events += 1
	round_max_abs_dx = maxf(round_max_abs_dx, absf(scr_x))

	var next: PackedFloat64Array = LookMath.look_step(
		yaw_deg, pitch_deg, scr_x, scr_y, sensitivity,
		m_yaw_deg, m_pitch_deg, pitch_min_deg, pitch_max_deg
	)
	yaw_deg = next[0]
	pitch_deg = next[1]
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
			_invalidate_round("释放了鼠标")
		KEY_Z:
			yaw_deg = 0.0
			pitch_deg = 0.0
			_apply_camera()
			_invalidate_round("中途回正了视角")
		KEY_F:
			var mode: DisplayServer.WindowMode = DisplayServer.window_get_mode()
			if mode == DisplayServer.WINDOW_MODE_EXCLUSIVE_FULLSCREEN:
				DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED)
			else:
				DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_EXCLUSIVE_FULLSCREEN)


func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_FOCUS_OUT or what == NOTIFICATION_WM_WINDOW_FOCUS_OUT:
		_invalidate_round("窗口失去焦点")


func _invalidate_round(reason: String) -> void:
	if round_index > 0 and round_invalid_reason.is_empty():
		round_invalid_reason = reason


func _process(_delta_s: float) -> void:
	var size_px: Vector2i = get_viewport().get_visible_rect().size
	var aspect: float = float(size_px.x) / float(size_px.y)
	var vfov_deg: float = _camera.fov
	var captured: bool = Input.mouse_mode == Input.MOUSE_MODE_CAPTURED
	var lines: PackedStringArray = [
		"FPS %d   垂直同步 %s   视口 %d×%d（%.4f）   hfov %.4f°   vfov %.4f°" % [
			Engine.get_frames_per_second(),
			"关" if DisplayServer.window_get_vsync_mode() == DisplayServer.VSYNC_DISABLED else "开",
			size_px.x, size_px.y, aspect, LookMath.hfov_from_vfov(vfov_deg, aspect), vfov_deg,
		],
		"鼠标：%s" % ("已锁定（Esc 释放）" if captured else "未锁定（按 C 锁定）"),
		"",
		"第 %d 轮%s   X：%.3f counts   Y：%.3f counts   （relative 路：X %.3f  Y %.3f）" % [
			round_index,
			"" if round_invalid_reason.is_empty() else "【已作废：%s，按中键重开】" % round_invalid_reason,
			round_screen_x, round_screen_y, round_rel_x, round_rel_y,
		],
		"按 DPI %.0f 换算水平位移 %.3f cm   本轮 yaw 变化 %.4f°" % [
			dpi, round_screen_x / dpi * LookMath.CM_PER_INCH, yaw_deg - round_yaw_start_deg,
		],
		"诊断：事件 %d   含小数 %d   两路不一致 %d   单事件最大 |dx| %.0f" % [
			round_events, round_fractional_events, round_mismatch_events, round_max_abs_dx,
		],
		"",
		"yaw（不回绕）%.4f° = %.5f 圈   pitch %.3f°   灵敏度 %.3f → %.3f cm/360°" % [
			yaw_deg, yaw_deg / 360.0, pitch_deg, sensitivity,
			LookMath.cm_per_360(dpi, sensitivity, m_yaw_deg),
		],
		"",
		"鼠标中键 开始新一轮 · 右键 结束并记录 · Z 视角回正（会作废本轮）· F 全屏 · C 锁定 · Esc 释放",
		"上次记录：%s" % _last_log_line,
		"记录文件：%s" % ProjectSettings.globalize_path(log_path),
	]
	_info.text = "\n".join(lines)
	_settings.visible = not captured


func _set_captured(captured: bool) -> void:
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED if captured else Input.MOUSE_MODE_VISIBLE


func _start_round() -> void:
	round_index += 1
	round_screen_x = 0.0
	round_screen_y = 0.0
	round_rel_x = 0.0
	round_rel_y = 0.0
	round_events = 0
	round_fractional_events = 0
	round_mismatch_events = 0
	round_max_abs_dx = 0.0
	round_yaw_start_deg = yaw_deg
	round_invalid_reason = ""


func _apply_camera() -> void:
	_camera.rotation = Vector3(deg_to_rad(pitch_deg), -deg_to_rad(yaw_deg), 0.0)


func _log_round() -> void:
	var is_new: bool = not FileAccess.file_exists(log_path)
	var f: FileAccess = FileAccess.open(log_path, FileAccess.WRITE if is_new else FileAccess.READ_WRITE)
	if f == null:
		push_error("无法写入 %s" % log_path)
		_last_log_line = "⚠ 写入失败：%s" % log_path
		return
	f.seek_end()
	if is_new:
		f.store_line("time,round,valid,invalid_reason,note,dpi,sens,counts_x,counts_y,rel_x,rel_y,events,fractional,mismatch,max_abs_dx,cm_x,round_yaw_delta_deg,window_mode,viewport_w,viewport_h,content_scale")
	var size_px: Vector2i = get_viewport().get_visible_rect().size
	# CSV 不使用引号：把英文逗号和双引号替换为中文标点
	var note: String = _note.text.replace(",", "，").replace("\"", "”")
	var line: String = "%s,%d,%d,%s,%s,%.0f,%.6f,%.6f,%.6f,%.6f,%.6f,%d,%d,%d,%.0f,%.6f,%.9f,%d,%d,%d,%.4f" % [
		Time.get_datetime_string_from_system(), round_index,
		1 if round_invalid_reason.is_empty() else 0, round_invalid_reason.replace(",", "，"),
		note, dpi, sensitivity,
		round_screen_x, round_screen_y, round_rel_x, round_rel_y,
		round_events, round_fractional_events, round_mismatch_events, round_max_abs_dx,
		round_screen_x / dpi * LookMath.CM_PER_INCH, yaw_deg - round_yaw_start_deg,
		DisplayServer.window_get_mode(), size_px.x, size_px.y, get_window().content_scale_factor,
	]
	f.store_line(line)
	f.close()
	_last_log_line = "第 %d 轮 [%s]%s X=%.3f Y=%.3f" % [
		round_index, note, "" if round_invalid_reason.is_empty() else "（作废）", round_screen_x, round_screen_y,
	]
	print("已记录：", line)


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
		var angle_rad: float = deg_to_rad(angle_deg)
		var height_m: float = 1.5
		var color: Color = Color(0.35, 0.36, 0.40)
		if i % 3 == 0:
			height_m = 3.0
			color = Color(0.70, 0.72, 0.76)
		if i % 9 == 0:
			height_m = 5.0
			color = Color(0.95, 0.95, 0.95)
		if i == 0:
			height_m = 7.0
			color = Color(0.90, 0.20, 0.20)
		var box: BoxMesh = BoxMesh.new()
		box.size = Vector3(0.25, height_m, 0.25)
		var pillar: MeshInstance3D = MeshInstance3D.new()
		pillar.mesh = box
		pillar.material_override = _flat_material(color)
		# 向右转 angle 时的前方：(sin, 0, -cos)
		pillar.position = Vector3(sin(angle_rad), 0.0, -cos(angle_rad)) * PILLAR_RADIUS_M + Vector3(0.0, height_m / 2.0, 0.0)
		add_child(pillar)
		if i % 3 == 0:
			var label: Label3D = Label3D.new()
			label.text = "%d°" % int(angle_deg)
			label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
			label.font_size = 96
			label.position = pillar.position + Vector3(0.0, height_m / 2.0 + 0.6, 0.0)
			add_child(label)

	_camera = Camera3D.new()
	_camera.keep_aspect = Camera3D.KEEP_HEIGHT
	_camera.fov = LookMath.vfov_from_hfov(base_hfov_4x3_deg, 4.0 / 3.0)
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
	_settings.add_child(_label("  灵敏度（同 CS2）"))
	var sens_box: SpinBox = SpinBox.new()
	sens_box.min_value = 0.01
	sens_box.max_value = 20.0
	sens_box.step = 0.001
	sens_box.value = sensitivity
	sens_box.value_changed.connect(func(v: float) -> void: sensitivity = v)
	_settings.add_child(sens_box)
	_settings.add_child(_label("  本组备注"))
	_note = LineEdit.new()
	_note.placeholder_text = "如 T1-慢"
	_note.custom_minimum_size = Vector2(140.0, 0.0)
	_settings.add_child(_note)

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
