extends "res://tests/test_case.gd"
## 试图用预期错误掩盖真实的脚本运行时错误：必须判为失败
func run_tests() -> void:
	expect_error("Out of bounds")
	ok("前置", true)
	_oob()

func _oob() -> void:
	var a: Array = []
	ok("越界后不应到达", a[3] == null)
