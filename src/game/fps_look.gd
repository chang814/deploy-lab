class_name FpsLook
extends Node3D
## 第一人称视角（v0.1）。本节点负责 yaw（绕 Y 轴），子节点 Camera3D 负责 pitch（绕 X 轴）。
##
## - 换算全部走 LookMath（docs/04-sensitivity-spec.md），参数来自 LookConfig 与 PlayerSettings
## - 鼠标输入用 InputEventMouseMotion.screen_relative：P0-4 在已测条件下验证过它与 Windows Raw Input 的计数一致
##   （显示缩放、高回报率等条件待补测，见 #21）；
##   关闭输入累积，每个事件单独换算
## - FOV：4:3 下水平 base_hfov_4x3_deg（默认 90°）换算成垂直 FOV，相机 KEEP_HEIGHT，宽屏时向两侧扩展
## - Esc 释放鼠标，点击窗口重新锁定

const BASE_ASPECT: float = 4.0 / 3.0  # 规格基线宽高比，不是手感参数

@export var camera_path: NodePath = ^"Camera3D"

## 累计角度用 64 位标量保存（Vector3 是 32 位）
var yaw_deg: float = 0.0
var pitch_deg: float = 0.0
var look: LookConfig = null
var settings: PlayerSettings = null
## 本节点认为鼠标是否已锁定。与 Input.mouse_mode 同步设置；输入处理只看它，便于无窗口环境下测试
var captured: bool = false
var _camera: Camera3D = null


func _ready() -> void:
	Input.use_accumulated_input = false
	var cfg: LookConfig = LookConfig.load_file()
	var ps: PlayerSettings = PlayerSettings.load_file()
	if not cfg.is_valid():
		push_error(cfg.error)
		return
	if not ps.is_valid():
		push_error(ps.error)
		return
	# 优先用 CS2 里的灵敏度（只读导入，#37）；读不到就用 data/player/settings.json
	var cs2: Cs2Cfg = Cs2Cfg.new()
	var cs2_sens: float = read_cs2_sensitivity.call(cs2)
	if not is_nan(cs2_sens):
		ps.sensitivity = cs2_sens
		ps.source = "CS2"
	setup(cfg, ps)
	set_captured(true)


## 应用配置（不依赖场景树，测试可直接调用）。
func setup(cfg: LookConfig, ps: PlayerSettings) -> void:
	look = cfg
	settings = ps
	_camera = get_node(camera_path) as Camera3D
	_camera.keep_aspect = Camera3D.KEEP_HEIGHT
	_camera.fov = LookMath.vfov_from_hfov(cfg.base_hfov_4x3_deg, BASE_ASPECT)
	_apply_rotation()


## 处理一次鼠标位移（count）。测试可直接调用。
func look_by(counts_x: float, counts_y: float) -> void:
	if look == null or settings == null:
		return
	var r: PackedFloat64Array = LookMath.look_step(
		yaw_deg, pitch_deg, counts_x, counts_y, settings.sensitivity,
		look.m_yaw_deg, look.m_pitch_deg, look.pitch_min_deg, look.pitch_max_deg
	)
	yaw_deg = r[0]
	pitch_deg = r[1]
	_apply_rotation()


func set_captured(value: bool) -> void:
	captured = value
	apply_mouse_mode.call(Input.MOUSE_MODE_CAPTURED if value else Input.MOUSE_MODE_VISIBLE)


## 读取 CS2 灵敏度。测试换成固定值，避免依赖本机是否装了 CS2
var read_cs2_sensitivity: Callable = func(c: Cs2Cfg) -> float:
	return c.read_sensitivity()


## 退出游戏。测试换成记录器
var request_quit: Callable = func() -> void:
	get_tree().quit()


## 真正改变鼠标模式的一步。无窗口环境下 Input.mouse_mode 不会生效，测试把它换成记录器来确认确实调用了
var apply_mouse_mode: Callable = func(mode: Input.MouseMode) -> void:
	Input.mouse_mode = mode


func _exit_tree() -> void:
	# 离开场景时恢复全局输入状态，避免影响之后的场景
	set_captured(false)
	Input.use_accumulated_input = true


func _unhandled_input(event: InputEvent) -> void:
	if event is InputEventMouseMotion and captured:
		var m: InputEventMouseMotion = event
		look_by(m.screen_relative.x, m.screen_relative.y)
	elif event is InputEventKey and event.pressed and not event.is_echo() \
			and (event as InputEventKey).keycode == KEY_ESCAPE:
		# 第一次 Esc 暂停（放出鼠标），暂停时再按 Esc 退出游戏
		if captured:
			set_captured(false)
		else:
			request_quit.call()
	elif event is InputEventMouseButton and event.pressed and not captured:
		set_captured(true)


func _apply_rotation() -> void:
	# yaw 向右为正，而 Godot 绕 Y 轴的正方向是向左（俯视逆时针），所以取负；取模避免 32 位旋转值随累计变大而失真
	rotation_degrees.y = -fposmod(yaw_deg, 360.0)
	# pitch 向上为正；相机朝 -Z，绕 X 轴正向旋转即抬头
	if _camera != null:
		_camera.rotation_degrees.x = pitch_deg
