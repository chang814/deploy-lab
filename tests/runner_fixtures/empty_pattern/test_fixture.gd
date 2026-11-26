extends "res://tests/test_case.gd"
## 空的预期错误内容会匹配任何错误：必须判为失败
func run_tests() -> void:
	expect_error("")
	ok("前置", true)
	push_error("随便一条")
