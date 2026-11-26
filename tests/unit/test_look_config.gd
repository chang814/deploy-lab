extends "res://tests/test_case.gd"
## LookConfig（视角参数读取）的测试。


func run_tests() -> void:
	_test_real_defaults_file()
	_test_missing_file()
	_test_bad_json()
	_test_missing_or_wrong_type()
	_test_invalid_ranges()
	_test_default_and_non_finite()


func _test_real_defaults_file() -> void:
	var c: LookConfig = LookConfig.load_file()
	ok("data/look/defaults.json 有效（%s）" % c.error, c.is_valid())
	near("m_yaw_deg", c.m_yaw_deg, 0.022, 0.0)
	near("m_pitch_deg", c.m_pitch_deg, 0.022, 0.0)
	near("pitch_min_deg", c.pitch_min_deg, -89.0, 0.0)
	near("pitch_max_deg", c.pitch_max_deg, 89.0, 0.0)
	near("base_hfov_4x3_deg", c.base_hfov_4x3_deg, 90.0, 0.0)


func _test_missing_file() -> void:
	var c: LookConfig = LookConfig.load_file("res://data/look/不存在.json")
	ok("文件不存在时无效", not c.is_valid())
	ok("错误信息提示导出问题", c.error.contains("导出"))


func _test_bad_json() -> void:
	ok("非 JSON 无效", not LookConfig.from_json_text("not json").is_valid())
	ok("JSON 数组无效", not LookConfig.from_json_text("[1, 2]").is_valid())


func _test_missing_or_wrong_type() -> void:
	var c: LookConfig = LookConfig.from_json_text('{"m_yaw_deg": 0.022}')
	ok("缺字段无效", not c.is_valid() and c.error.contains("缺少字段"))
	var t: LookConfig = LookConfig.from_json_text(
		'{"m_yaw_deg": "0.022", "m_pitch_deg": 0.022, "pitch_min_deg": -89, "pitch_max_deg": 89, "base_hfov_4x3_deg": 90}'
	)
	ok("字符串数字无效", not t.is_valid() and t.error.contains("不是数字"))
	var i: LookConfig = LookConfig.from_json_text(
		'{"m_yaw_deg": 0.022, "m_pitch_deg": 0.022, "pitch_min_deg": -89, "pitch_max_deg": 89, "base_hfov_4x3_deg": 90}'
	)
	ok("整数写法有效", i.is_valid())


func _test_default_and_non_finite() -> void:
	ok("新建的对象默认无效", not LookConfig.new().is_valid())
	for key: String in LookConfig.REQUIRED_KEYS:
		# Godot 的 JSON 解析器遇到 1e99999 会记录一条「Exponent too high」引擎错误
		expect_error("Exponent too high")
		var d: Dictionary = {"m_yaw_deg": 0.022, "m_pitch_deg": 0.022, "pitch_min_deg": -89, "pitch_max_deg": 89, "base_hfov_4x3_deg": 90}
		var text: String = JSON.stringify(d).replace('"%s":%s' % [key, JSON.stringify(d[key])], '"%s":1e99999' % key)
		var c: LookConfig = LookConfig.from_json_text(text)
		ok("%s 为无穷大时无效（%s）" % [key, c.error], not c.is_valid() and c.error.contains("有限"))


func _test_invalid_ranges() -> void:
	var p: LookConfig = LookConfig.from_json_text(
		'{"m_yaw_deg": 0.022, "m_pitch_deg": 0.022, "pitch_min_deg": 89, "pitch_max_deg": -89, "base_hfov_4x3_deg": 90}'
	)
	ok("pitch 上下限颠倒无效", not p.is_valid())
	var f: LookConfig = LookConfig.from_json_text(
		'{"m_yaw_deg": 0.022, "m_pitch_deg": 0.022, "pitch_min_deg": -89, "pitch_max_deg": 89, "base_hfov_4x3_deg": 180}'
	)
	ok("FOV=180 无效", not f.is_valid())
