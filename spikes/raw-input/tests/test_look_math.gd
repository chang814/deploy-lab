extends SceneTree
## 运行：godot --headless --path spikes/raw-input -s res://tests/test_look_math.gd
## 用例来自 docs/04-sensitivity-spec.md 第 5 节。

const LookMath = preload("res://look_math.gd")
const M: float = 0.022

var _passed: int = 0
var _failed: int = 0


func _init() -> void:
	_test_distance_table()
	_test_fov()
	_test_accumulation()
	_test_pitch()
	_test_custom_m_yaw()
	_test_invalid_inputs()
	print("结果：通过 %d，失败 %d" % [_passed, _failed])
	quit(1 if _failed > 0 else 0)


func _near(label: String, actual: float, expected: float, tol: float) -> void:
	if absf(actual - expected) <= tol:
		_passed += 1
	else:
		_failed += 1
		printerr("失败 %s：实际 %.15f，期望 %.15f，允许误差 %e" % [label, actual, expected, tol])


func _truthy(label: String, ok: bool) -> void:
	if ok:
		_passed += 1
	else:
		_failed += 1
		printerr("失败 %s" % label)


func _test_distance_table() -> void:
	var rows: Array = [
		[800.0, 1.0, 16363.636363636364, 51.954545454545],
		[400.0, 2.0, 8181.818181818182, 51.954545454545],
		[800.0, 2.5, 6545.454545454546, 20.781818181818],
		[1600.0, 0.8, 20454.545454545452, 32.471590909091],
	]
	for row: Array in rows:
		var dpi: float = row[0]
		var sens: float = row[1]
		_near("counts/360 dpi=%d sens=%s" % [dpi, sens], LookMath.counts_per_360(sens, M), row[2], 1e-8)
		_near("cm/360 dpi=%d sens=%s" % [dpi, sens], LookMath.cm_per_360(dpi, sens, M), row[3], 1e-9)


func _test_fov() -> void:
	var vfov: float = LookMath.vfov_from_hfov(90.0, 4.0 / 3.0)
	_near("vfov 90@4:3", vfov, 73.739795291688, 1e-8)
	_near("hfov 16:9", LookMath.hfov_from_vfov(vfov, 16.0 / 9.0), 106.260204708312, 1e-8)
	_near("hfov 16:10", LookMath.hfov_from_vfov(vfov, 16.0 / 10.0), 100.388857815470, 1e-8)
	_near("hfov 4:3", LookMath.hfov_from_vfov(vfov, 4.0 / 3.0), 90.0, 1e-8)
	_near("hfov 1:1", LookMath.hfov_from_vfov(vfov, 1.0), 73.739795291688, 1e-8)


func _test_accumulation() -> void:
	var yaw: float = 0.0
	for i: int in 10000:
		yaw += LookMath.delta_deg(1.0, 1.0, M)
	_near("10000 次 +1 count", yaw, 220.0, 1e-8)
	_near("与单次 +10000 counts 一致", yaw, LookMath.delta_deg(10000.0, 1.0, M), 1e-8)

	var yaw_frac: float = 0.0
	for i: int in 10000:
		yaw_frac += LookMath.delta_deg(0.1, 1.0, M)
	_near("10000 次 +0.1 count", yaw_frac, 22.0, 1e-8)

	for i: int in 10000:
		yaw -= LookMath.delta_deg(1.0, 1.0, M)
	_near("+10000 后 -10000 回到 0", yaw, 0.0, 1e-8)


func _test_pitch() -> void:
	var up: float = LookMath.delta_deg(1.0, 1.0, M)
	_near("88.99 +1 count 截到 89", LookMath.apply_pitch(88.99, up, -89.0, 89.0), 89.0, 1e-10)
	_near("-88.99 -1 count 截到 -89", LookMath.apply_pitch(-88.99, -up, -89.0, 89.0), -89.0, 1e-10)
	var p: float = LookMath.apply_pitch(89.0, LookMath.delta_deg(100.0, 1.0, M), -89.0, 89.0)
	_near("89 +100 counts 保持 89", p, 89.0, 1e-10)
	p = LookMath.apply_pitch(p, -up, -89.0, 89.0)
	_near("越界后 -1 count 立即离开边界", p, 88.978, 1e-10)
	p = LookMath.apply_pitch(-89.0, LookMath.delta_deg(-100.0, 1.0, M), -89.0, 89.0)
	p = LookMath.apply_pitch(p, up, -89.0, 89.0)
	_near("-89 -100 后 +1 count", p, -88.978, 1e-10)


func _test_custom_m_yaw() -> void:
	_near("m_yaw=0.03 +100 counts", LookMath.delta_deg(100.0, 1.0, 0.03), 3.0, 1e-10)
	_near("m_yaw=0.03 counts/360", LookMath.counts_per_360(1.0, 0.03), 12000.0, 1e-8)
	_near("m_yaw=0.03 cm/360 @800", LookMath.cm_per_360(800.0, 1.0, 0.03), 38.1, 1e-9)
	_near("m_pitch=0.01 垂直 +100 counts", LookMath.delta_deg(100.0, 1.0, 0.01), 1.0, 1e-10)


func _test_invalid_inputs() -> void:
	_truthy("sens=0 时 counts/360 为 INF", is_inf(LookMath.counts_per_360(0.0, M)))
	_truthy("m_yaw=0 时 cm/360 为 INF", is_inf(LookMath.cm_per_360(800.0, 1.0, 0.0)))
	_near("sens=0 时增量为 0", LookMath.delta_deg(100.0, 0.0, M), 0.0, 0.0)
	_truthy("DPI<=0 返回 NAN", is_nan(LookMath.cm_per_360(0.0, 1.0, M)))
	_truthy("aspect<=0 返回 NAN", is_nan(LookMath.hfov_from_vfov(73.0, 0.0)))
	_truthy("FOV>=180 返回 NAN", is_nan(LookMath.vfov_from_hfov(180.0, 1.0)))
	_truthy("FOV<=0 返回 NAN", is_nan(LookMath.vfov_from_hfov(0.0, 1.0)))
