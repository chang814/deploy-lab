class_name Target
extends StaticBody3D
## 靶子：被命中时闪红并计数；可选左右往返移动（v0.2 最小靶场）。

@export var move_amplitude_m: float = 0.0
@export var move_speed_mps: float = 2.0

var hit_count: int = 0
var _origin: Vector3
var _t_s: float = 0.0
var _flash_s: float = 0.0
var _mesh: MeshInstance3D = null
var _mat: StandardMaterial3D = null


func _ready() -> void:
	_origin = position
	_mesh = get_node_or_null(^"Mesh") as MeshInstance3D
	if _mesh != null:
		_mat = StandardMaterial3D.new()
		_mat.albedo_color = Color(0.9, 0.9, 0.9)
		_mesh.material_override = _mat


func on_hit() -> void:
	hit_count += 1
	_flash_s = 0.12


func _physics_process(dt_s: float) -> void:
	if move_amplitude_m > 0.0:
		_t_s += dt_s
		# 匀速往返（三角波）：便于练跟枪，速度 = move_speed_mps
		var period_s: float = 4.0 * move_amplitude_m / move_speed_mps
		var phase: float = fposmod(_t_s, period_s) / period_s
		var tri: float = 4.0 * absf(phase - 0.5) - 1.0
		position = _origin + transform.basis.x * (tri * move_amplitude_m)
	_flash_s = maxf(_flash_s - dt_s, 0.0)
	if _mat != null:
		_mat.albedo_color = Color(0.95, 0.2, 0.15) if _flash_s > 0.0 else Color(0.9, 0.9, 0.9)
