extends "res://tests/test_case.gd"
## PlayerSettings（玩家设置读取）的测试。


func run_tests() -> void:
	var real: PlayerSettings = PlayerSettings.load_file()
	ok("data/player/settings.json 有效（%s）" % real.error, real.is_valid())
	ok("默认灵敏度为正", real.sensitivity > 0.0)

	var missing: PlayerSettings = PlayerSettings.load_file("res://data/player/不存在.json")
	ok("文件不存在时无效", not missing.is_valid() and missing.error.contains("导出"))

	ok("非 JSON 无效", not PlayerSettings.from_json_text("not json").is_valid())
	ok("JSON 数组无效", not PlayerSettings.from_json_text("[1]").is_valid())
	ok("缺字段无效", not PlayerSettings.from_json_text("{}").is_valid())
	ok("字符串无效", not PlayerSettings.from_json_text('{"sensitivity": "1.2"}').is_valid())
	ok("零无效", not PlayerSettings.from_json_text('{"sensitivity": 0}').is_valid())
	ok("负数无效", not PlayerSettings.from_json_text('{"sensitivity": -1}').is_valid())
	expect_error("Exponent too high")  # Godot 解析超大指数时会打一条引擎警告
	ok("无穷大无效", not PlayerSettings.from_json_text('{"sensitivity": 1e99999}').is_valid())
	var s: PlayerSettings = PlayerSettings.from_json_text('{"sensitivity": 2}')
	ok("整数有效", s.is_valid())
	near("整数读成 2.0", s.sensitivity, 2.0, 0.0)
