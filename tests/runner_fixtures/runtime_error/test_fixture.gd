extends "res://tests/test_case.gd"
func run_tests() -> void:
	ok("前置", true)
	_oob()

func _oob() -> void:
	var a: Array = []
	ok("越界后不应到达", a[3] == null)
