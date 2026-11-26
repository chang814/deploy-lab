extends "res://tests/test_case.gd"
## 声明了两条预期错误，实际只触发一条：必须判为失败
func run_tests() -> void:
	expect_error("故意触发")
	expect_error("故意触发")
	ok("前置", true)
	push_error("故意触发的一条错误")
