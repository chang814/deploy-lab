class_name Target
extends StaticBody3D
## 靶子：被命中时闪红、计数，并沿子弹方向向后晃一下（弹簧回正）；可选左右往返移动（v0.2 最小靶场）。

@export var move_amplitude_m: float = 0.0
@export var move_speed_mps: float = 2.0

var hit_count: int = 0
var _origin: Vector3
var _t_s: float = 0.0
var _flash_s: float = 0.0
var _mesh: MeshInstance3D = null
var _mat: StandardMaterial3D = null
var _tilt_deg: float = 0.0
var _tilt_vel_dps: float = 0.0
var _tilt_axis: Vector3 = Vector3.RIGHT


func _ready() -> void:
	_origin = position
	_mesh = get_node_or_null(^"Mesh") as MeshInstance3D
	if _mesh != null:
		_mat = StandardMaterial3D.new()
		_mat.albedo_color = Color(0.9, 0.9, 0.9)
		_mesh.material_override = _mat


func on_hit(shot_dir: Vector3 = Vector3.ZERO) -> void:
	hit_count += 1
	_flash_s = 0.12
	# 绕「水平且垂直于子弹方向」的轴向后倒
	var h: Vector3 = Vector3(shot_dir.x, 0.0, shot_dir.z)
	if h.length_squared() > 1e-6:
		_tilt_axis = Vector3.UP.cross(h.normalized()).normalized() * -1.0
	_tilt_vel_dps += 260.0


func _physics_process(dt_s: float) -> void:
	if move_amplitude_m > 0.0:
		_t_s += dt_s
		# 匀速往返（三角波）：便于练跟枪，速度 = move_speed_mps
		var period_s: float = 4.0 * move_amplitude_m / move_speed_mps
		var phase: float = fposmod(_t_s, period_s) / period_s
		var tri: float = 4.0 * absf(phase - 0.5) - 1.0
		position = _origin + transform.basis.x * (tri * move_amplitude_m)
	# 弹簧阻尼回正
	_tilt_vel_dps += (-_tilt_deg * 180.0 - _tilt_vel_dps * 12.0) * dt_s
	_tilt_deg += _tilt_vel_dps * dt_s
	if _mesh != null:
		_mesh.basis = Basis(_tilt_axis, deg_to_rad(_tilt_deg))
		_mesh.position = Vector3(0, -0.8, 0) + Basis(_tilt_axis, deg_to_rad(_tilt_deg)) * Vector3(0, 0.8, 0)
	_flash_s = maxf(_flash_s - dt_s, 0.0)
	if _mat != null:
		_mat.albedo_color = Color(0.95, 0.2, 0.15) if _flash_s > 0.0 else Color(0.9, 0.9, 0.9)
