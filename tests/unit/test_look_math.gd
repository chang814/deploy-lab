extends "res://tests/test_case.gd"
## LookMath 的测试，用例来自 docs/04-sensitivity-spec.md 第 5 节（从 spike 的测试转正）。

const M_DEG: float = 0.022
const P_MIN_DEG: float = -89.0
const P_MAX_DEG: float = 89.0


func run_tests() -> void:
	_test_distance_table()
	_test_fov()
	_test_fov_invalid()
	_test_accumulation()
	_test_frame_batching()
	_test_pitch()
	_test_look_step_pipeline()
	_test_custom_gains()
	_test_zero_and_negative_gain()


func _step(state: PackedFloat64Array, dx: float, dy: float, m_yaw_deg: float = M_DEG, m_pitch_deg: float = M_DEG) -> PackedFloat64Array:
	return LookMath.look_step(state[0], state[1], dx, dy, 1.0, m_yaw_deg, m_pitch_deg, P_MIN_DEG, P_MAX_DEG)


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
		near("counts/360 dpi=%d sens=%s" % [dpi, sens], LookMath.counts_per_360(sens, M_DEG), row[2], 1e-8)
		near("cm/360 dpi=%d sens=%s" % [dpi, sens], LookMath.cm_per_360(dpi, sens, M_DEG), row[3], 1e-9)


func _test_fov() -> void:
	var vfov_deg: float = LookMath.vfov_from_hfov(90.0, 4.0 / 3.0)
	near("vfov 90@4:3", vfov_deg, 73.739795291688, 1e-8)
	near("hfov 16:9", LookMath.hfov_from_vfov(vfov_deg, 16.0 / 9.0), 106.260204708312, 1e-8)
	near("hfov 16:10", LookMath.hfov_from_vfov(vfov_deg, 16.0 / 10.0), 100.388857815470, 1e-8)
	near("hfov 4:3", LookMath.hfov_from_vfov(vfov_deg, 4.0 / 3.0), 90.0, 1e-8)
	near("hfov 1:1", LookMath.hfov_from_vfov(vfov_deg, 1.0), 73.739795291688, 1e-8)


func _test_fov_invalid() -> void:
	for f: Callable in [LookMath.vfov_from_hfov, LookMath.hfov_from_vfov]:
		var n: String = f.get_method()
		ok("%s aspect=0" % n, is_nan(f.call(73.0, 0.0)))
		ok("%s aspect<0" % n, is_nan(f.call(73.0, -1.0)))
		ok("%s fov=0" % n, is_nan(f.call(0.0, 1.0)))
		ok("%s fov<0" % n, is_nan(f.call(-10.0, 1.0)))
		ok("%s fov=180" % n, is_nan(f.call(180.0, 1.0)))
		ok("%s fov>180" % n, is_nan(f.call(200.0, 1.0)))
		ok("%s fov=179.9 有效" % n, not is_nan(f.call(179.9, 1.0)))


func _test_accumulation() -> void:
	var yaw_deg: float = 0.0
	for i: int in 10000:
		yaw_deg += LookMath.delta_deg(1.0, 1.0, M_DEG)
	near("10000 次 +1 count", yaw_deg, 220.0, 1e-8)
	near("与单次 +10000 counts 一致", yaw_deg, LookMath.delta_deg(10000.0, 1.0, M_DEG), 1e-8)
	var yaw_frac_deg: float = 0.0
	for i: int in 10000:
		yaw_frac_deg += LookMath.delta_deg(0.1, 1.0, M_DEG)
	near("10000 次 +0.1 count", yaw_frac_deg, 22.0, 1e-8)
	for i: int in 10000:
		yaw_deg -= LookMath.delta_deg(1.0, 1.0, M_DEG)
	near("+10000 后 -10000 回到 0", yaw_deg, 0.0, 1e-8)


func _test_frame_batching() -> void:
	var rng: RandomNumberGenerator = RandomNumberGenerator.new()
	rng.seed = 20261125
	for batch_max: int in [1, 7, 64, 1000]:
		var state: PackedFloat64Array = PackedFloat64Array([0.0, 0.0])
		var remaining: int = 10000
		while remaining > 0:
			var batch: int = mini(remaining, rng.randi_range(1, batch_max))
			for i: int in batch:
				state = _step(state, 1.0, 0.0)
			remaining -= batch
		near("分批（每帧最多 %d 个事件）总 yaw" % batch_max, state[0], 220.0, 1e-8)


func _test_pitch() -> void:
	var one_deg: float = LookMath.delta_deg(1.0, 1.0, M_DEG)
	near("88.99 +1 count 截到 89", LookMath.apply_pitch(88.99, one_deg, P_MIN_DEG, P_MAX_DEG), 89.0, 1e-10)
	near("-88.99 -1 count 截到 -89", LookMath.apply_pitch(-88.99, -one_deg, P_MIN_DEG, P_MAX_DEG), -89.0, 1e-10)


func _test_look_step_pipeline() -> void:
	var s: PackedFloat64Array = PackedFloat64Array([0.0, 89.0])
	s = _step(s, 0.0, -100.0)
	near("89° 再向上 100 counts 保持 89", s[1], 89.0, 1e-10)
	s = _step(s, 0.0, 1.0)
	near("随后向下 1 count → 88.978", s[1], 88.978, 1e-10)
	s = PackedFloat64Array([0.0, -89.0])
	s = _step(s, 0.0, 100.0)
	near("-89° 再向下 100 counts 保持 -89", s[1], -89.0, 1e-10)
	s = _step(s, 0.0, -1.0)
	near("随后向上 1 count → -88.978", s[1], -88.978, 1e-10)
	s = _step(PackedFloat64Array([0.0, 0.0]), 100.0, 0.0)
	near("鼠标右移 → yaw 为正", s[0], 2.2, 1e-10)
	near("水平移动不影响 pitch", s[1], 0.0, 0.0)


func _test_custom_gains() -> void:
	near("m_yaw=0.03 +100 counts", LookMath.delta_deg(100.0, 1.0, 0.03), 3.0, 1e-10)
	near("m_yaw=0.03 counts/360", LookMath.counts_per_360(1.0, 0.03), 12000.0, 1e-8)
	near("m_yaw=0.03 cm/360 @800", LookMath.cm_per_360(800.0, 1.0, 0.03), 38.1, 1e-9)
	var s: PackedFloat64Array = _step(PackedFloat64Array([0.0, 0.0]), 100.0, -100.0, 0.03, 0.01)
	near("适配层：X 用 m_yaw=0.03", s[0], 3.0, 1e-10)
	near("适配层：Y 用 m_pitch=0.01（向上 100 counts）", s[1], 1.0, 1e-10)


func _test_zero_and_negative_gain() -> void:
	ok("sens=0 时 counts/360 为 INF", is_inf(LookMath.counts_per_360(0.0, M_DEG)))
	ok("m_yaw=0 时 cm/360 为 INF", is_inf(LookMath.cm_per_360(800.0, 1.0, 0.0)))
	near("sens=0 时增量为 0", LookMath.delta_deg(100.0, 0.0, M_DEG), 0.0, 0.0)
	near("m_yaw=0 时增量为 0", LookMath.delta_deg(100.0, 1.0, 0.0), 0.0, 0.0)
	ok("DPI=0 返回 NAN", is_nan(LookMath.cm_per_360(0.0, 1.0, M_DEG)))
	ok("DPI<0 返回 NAN", is_nan(LookMath.cm_per_360(-800.0, 1.0, M_DEG)))
	near("负增益 counts/360 取正值", LookMath.counts_per_360(-1.0, M_DEG), 16363.636363636364, 1e-8)
	near("负增益只改变方向", LookMath.delta_deg(100.0, -1.0, M_DEG), -2.2, 1e-10)
