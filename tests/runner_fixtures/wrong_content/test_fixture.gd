extends "res://tests/test_case.gd"
## 错误数量与声明相同，但内容对不上：必须判为失败
func run_tests() -> void:
	expect_error("Exponent too high")
	ok("前置", true)
	push_error("完全不同的一条错误")
